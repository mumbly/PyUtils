#!/usr/bin/python
"""
Find duplicate files from a given root in the directory hierarchy of a given size
"""
import os
import glob
import sys
import hashlib
import optparse
import timeit

class FileDupes(object):
  """Container for the list of dupe files"""

  def __init__(self, path, size=20000, outfilename="dupes.out"):
    # PARAMETERS - not all settable yet
    self.path = path
    self.size = size
    self.excludeList = ["Backups.backupdb"]
    self.cross_mount_points = False
    self.output_filename = outfilename

    # List of files that meet the filesize filter and exclude list filter that we will check
    self.fileList = []
    # List of files with identical file sizes
    self.dupeSizeList = []
    # List of duplicate files (as checked by identical md5s)
    self.dupeList = []
    # Number of directories checked
    self.dirCount = 0

    self.__walk_tree()
    print("Found %d files to be processed" % (len(self.fileList)))
    self.__find_dupe_size()
    self.__find_dupe()
    self.__write_dupe_file(self.output_filename)
    print("Found %d files that appear to be duplicates" % (len(self.dupeList)))

  def __md5_for_file(self, filename, num_chunks=None):
    """
    Determine the md5 checksum for a given file or a given portion of a file.

    By default, you'll get the full checksum, but if you want to only generate
    an md5 for a portion of the file, you can pass in the number of 8k chunks
    you use. This won't give you an accurate fingerprint, but if used consistently
    for two files, you may be able to short circuit having to do the full md5
    sum. Basically, if two files have different md5s for the same number of chunks,
    they will be different. If they are the same, the files may or may not be the
    same and we'll need to do the full calculation.
    """
    md5 = hashlib.md5()
    with open(filename, 'rb') as f:
      chunk_count = 0
      for chunk in iter(lambda: f.read(8192), ''):
        if (num_chunks is not None) and (num_chunks < chunk_count):
          break
        md5.update(chunk)
        chunk_count += 1
    return md5.hexdigest()

  def __walk_tree(self):
    """
    Walk the directory given by self.path, filtering as directed, creating a file list in self.fileList.

    We'll do a walk of the filesystem starting at the given root directory. We will filter out directories
    listed in self.excludeList, files that are smaller than self.size and if self.cross_mount_points is
    True, directories that are on another filesystem.
    """
    for root, dirnames, files in os.walk(self.path, topdown=True):
      self.dirCount += 1
      # Create a tuple with the file size, the file name and the files inode (for tracking hard links).
      files = [
      (os.lstat(os.path.join(root, fi)).st_size, os.path.join(root, fi), os.lstat(os.path.join(root, fi)).st_ino) for fi
      in files if (os.lstat(os.path.join(root, fi)).st_size > self.size)]
      self.fileList.extend(files)
      if len(self.excludeList) > 0:
        dirnames[:] = [dir for dir in dirnames if dir not in self.excludeList]
      if not self.cross_mount_points:
        dirnames[:] = [dir for dir in dirnames if not os.path.ismount(os.path.join(root, dir))]


  def __find_dupe_size(self):
    """
    Generate a list of files with identical sizes.

    These files are candidates for duplicate files. If two files have different sizes, we assume
    they are not the same. We'll still need to confirm with an md5 fingerprint, but this will be
    much faster. Track the progress of the method, updating every 100 files. If we do the full
    md5 here, this progress will slow as we get further into the list, because we'll have larger
    files. We should to the partial md5 here and then compute the full md5 for those that have a
    match.

    Return a tuple with the size, the md5 of the file, the filename and the inode of the file.
    """
    sortedList = sorted(self.fileList, key=lambda file: file[0])
    lastSizeCaptured = 0
    file_count = 0
    total_count = len(sortedList)
    if total_count > 0:
      (curSize, curFilename, curIno) = sortedList[0]
    for size, filename, ino in sortedList[1:]:
      if (curSize == size):
        if (lastSizeCaptured != curSize):
          self.dupeSizeList.append((curSize, self.__md5_for_file(curFilename,10), curFilename, curIno))
        self.dupeSizeList.append((size, self.__md5_for_file(filename,10), filename, ino))
        lastSizeCaptured = curSize
      (curSize, curFilename, curIno) = (size, filename, ino)
      file_count += 1
      if (file_count % 100) == 0:
        print("Processed %s of %s files" % (file_count, total_count))

  def __find_dupe(self):
    """
    From a list of (filesize,md5sum,filename,ino) tuples, find all files that have matching md5sums and
    are thus identical, saving this list to self.dupeList.

    """
    sortedList = sorted(self.dupeSizeList, key=lambda file: file[1])
    lastMd5Captured = ""
    if len(sortedList) > 0:
      (curSize, curMd5, curFilename, curIno) = sortedList[0]
    for size, md5, filename, ino in sortedList[1:]:
      if (curMd5 == md5) and (curIno != ino):
        # Since we did only a partial md5, we need to do a full md5
        curMd5 = self.__md5_for_file(curFilename)
        md5 = self.__md5_for_file(filename)
        if curMd5 == md5:
          if (lastMd5Captured != curMd5):
            self.dupeList.append((curSize, curMd5, curFilename, curIno))
          self.dupeList.append((size, md5, filename, ino))
          lastMd5Captured = curMd5
      (curSize, curMd5, curFilename, curIno) = (size, md5, filename, ino)

  def __write_dupe_file(self, filename):
    """
    Write out file sorted by filesize.

    We're outputing the md5 checksum, file inode and the filenames as well. This is mainly for
    troubleshooting, as this hasn't been tested extensively enough yet to be sure.
    """
    sortedList = sorted(self.dupeList, key=lambda file: file[0])
    with open(filename, mode='w') as outfile:
      for size, md5, filename, ino in sortedList:
        outfile.write("%s %s %s %s\n" % (size, md5, ino, filename))

def get_options():
  parser = optparse.OptionParser()
  parser.add_option("-f", "--filename", dest="filename", default="dupes.out", help="save dupe list to FILE",
                    metavar="FILE")
  parser.add_option("-d", "--dir", dest="dir", default=".", help="directory to use FILE", metavar="DIRECTORY")
  parser.add_option("-s", "--size", type="int", dest="size", default="250000", help="min size of file to check FILE",
                    metavar="SIZE")
  return parser.parse_args()

def main():
  (options, args) = get_options()
  print("file: %s dir: %s size: %s" % (options.filename, options.dir, options.size))
  dupes = FileDupes(options.dir, size=options.size, outfilename=options.filename)

if __name__ == '__main__':
  main()
