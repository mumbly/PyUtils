#!/usr/bin/python
"""Find duplicate files from a given root in the directory hierarchy of a given size
"""
import os
import glob
import sys
import hashlib
import optparse
import timeit

class FileDupes(object):
  """Container for the list of dupe files"""

  def __init__(self, path, size=20000):
    # PARAMETERS
    self.path = path
    self.size = size
    self.excludeList = ["Backups.backupdb"]
    self.cross_mount_points = False

    # List of files that meet the filesize filter and exclude list filter that we will check
    self.fileList = []
    # List of files with identical file sizes
    self.dupeSizeList = []
    # List of duplicate files (as checked by identical md5s)
    self.dupeList = []
    # Number of directories checked
    self.dirCount = 0

  def __md5_for_file(self, filename, num_chunks=None):
    md5 = hashlib.md5()
    with open(filename, 'rb') as f:
      chunk_count = 0
      for chunk in iter(lambda: f.read(8192), ''):
        if (num_chunks is not None) and (num_chunks < chunk_count):
          break
        md5.update(chunk)
        chunk_count += 1
    return md5.hexdigest()

  def walk_tree(self):
    for root, dirnames, files in os.walk(self.path, topdown=True):
      self.dirCount += 1
      files = [
      (os.lstat(os.path.join(root, fi)).st_size, os.path.join(root, fi), os.lstat(os.path.join(root, fi)).st_ino) for fi
      in files if (os.lstat(os.path.join(root, fi)).st_size > self.size)]
      self.fileList.extend(files)
      if len(self.excludeList) > 0:
        dirnames[:] = [dir for dir in dirnames if dir not in self.excludeList]
      if not self.cross_mount_points:
        dirnames[:] = [dir for dir in dirnames if not os.path.ismount(os.path.join(root, dir))]

      for (size, name, ino) in files:
      #        print("3 - File %s size %s" % (name, size))
        pass

  def find_dupe_size(self):
    sortedList = sorted(self.fileList, key=lambda file: file[0])
    lastSizeCaptured = 0
    file_count = 0
    total_count = len(sortedList)
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

  def find_dupe(self):
    """
    From a list of (filesize,md5sum,filename) tuples, find all files that have matching md5sums and
    are thus identical. This list is saveed out to self.dupeList
    """
    sortedList = sorted(self.dupeSizeList, key=lambda file: file[1])
    print("First ten: ", sortedList[:10])
    lastSizeCaptured = ""
    (curSize, curMd5, curFilename, curIno) = sortedList[0]
    for size, md5, filename, ino in sortedList[1:]:
      if (curMd5 == md5) and (curIno != ino):
        if (lastSizeCaptured != curMd5):
          self.dupeList.append((curSize, curMd5, curFilename, curIno))
        self.dupeList.append((size, md5, filename, ino))
        lastSizeCaptured = curMd5
      (curSize, curMd5, curFilename, curIno) = (size, md5, filename, ino)

  def print_dupe_size(self):
    for size, md5, filename in self.dupeSizeList:
      print("Dupe file size: %s %s %s" % (size, md5, filename))

  def print_dupe(self, filename):
    sortedList = sorted(self.dupeList, key=lambda file: file[0])
    with open(filename, mode='w') as outfile:
      for size, md5, filename, ino in sortedList:
        outfile.write("Dupe file: %s %s %s %s\n" % (size, md5, ino, filename))

def get_options():
  parser = optparse.OptionParser()
  parser.add_option("-f", "--filename", dest="filename", default="dupes.txt", help="save dupe list to FILE",
                    metavar="FILE")
  parser.add_option("-d", "--dir", dest="dir", default=".", help="directory to use FILE", metavar="DIRECTORY")
  parser.add_option("-s", "--size", type="int", dest="size", default="250000", help="min size of file to check FILE",
                    metavar="SIZE")
  return parser.parse_args()

def main():
  (options, args) = get_options()
  print("file: %s dir: %s size: %s" % (options.filename, options.dir, options.size))
  dupes = FileDupes(options.dir, size=options.size)
  print("gathering files")
  dupes.walk_tree()
  print("Found %d files" % (len(dupes.fileList)))
  dupes.find_dupe_size()
  print("Found %d potential dupes" % (len(dupes.dupeSizeList)))
  dupes.find_dupe()
  dupes.print_dupe(options.filename)
  print("num of dirs: %d" % (dupes.dirCount))
  print("size of list: %d" % (len(dupes.fileList)))

if __name__ == '__main__':
  main()
