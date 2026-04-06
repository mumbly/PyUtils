#!/usr/bin/env python3
"""Find duplicate files from a given root in the directory hierarchy of a given size."""

import hashlib
import argparse
import sys
from collections import defaultdict
from typing import List, Dict, Optional, NamedTuple
from pathlib import Path

class FileInfo(NamedTuple):
    size: int
    path: Path
    ino: int

class DupeInfo(NamedTuple):
    size: int
    md5: str
    path: Path
    ino: int

class FileDupes:
    """Find duplicate files in a directory tree."""

    def __init__(self, path: str, size: int = 250000, outfilename: str = "dupes.out", exclude_list: List[str] = None):
        self.root_path = Path(path)
        self.min_size = size
        self.output_filename = outfilename
        self.exclude_list = set(exclude_list) if exclude_list else {"Backups.backupdb"}
        self.cross_mount_points = False

        self.file_list: List[FileInfo] = []
        self.dupe_candidates: List[DupeInfo] = []
        self.dupes: List[DupeInfo] = []
        self.dir_count = 0  # TODO: dir_count is tracked but never printed or returned; use it in a summary or remove it.

    def run(self):
        """Execute the duplicate finding process."""
        # TODO: Add a --verbose flag that prints progress counts after each stage
        #       (files found, candidates, confirmed dupes) so large scans give feedback.
        self._walk_tree()
        print(f"Found {len(self.file_list)} files to be processed")
        
        self._find_potential_dupes()
        self._confirm_dupes()
        self._write_dupe_file()
        
        print(f"Found {len(self.dupes)} files that appear to be duplicates")

    @staticmethod
    def _md5_for_file(path: Path, num_chunks: Optional[int] = None) -> str:
        """Calculate MD5 hash for a file."""
        # TODO: Switch from MD5 to SHA-256; MD5 is cryptographically broken and
        #       collision resistance is not guaranteed, even if accidental collisions are rare.
        md5 = hashlib.md5()
        try:
            with path.open('rb') as f:
                for chunk_count, chunk in enumerate(iter(lambda: f.read(8192), b'')):
                    if num_chunks is not None and chunk_count >= num_chunks:
                        break
                    md5.update(chunk)
            return md5.hexdigest()
        except OSError as e:
            print(f"Error reading {path}: {e}", file=sys.stderr)
            # TODO: Returning "" on error causes unreadable files to match each other as
            #       "duplicates". Use a sentinel value (e.g. None) and skip those entries.
            return ""

    def _walk_tree(self):
        """Walk the directory tree and collect file information."""
        # TODO: pathlib.Path.walk() requires Python 3.12+. Document this requirement
        #       explicitly, or replace with os.walk() for broader compatibility.
        # TODO: The entire file list is accumulated in memory before hashing begins.
        #       On filesystems with millions of files this can exhaust memory; consider
        #       a streaming/generator approach that feeds files directly into hashing.
        for root, dirs, files in self.root_path.walk(top_down=True):
            self.dir_count += 1
            
            # Filter directories in place
            if self.exclude_list:
                dirs[:] = [d for d in dirs if d not in self.exclude_list]
            
            # TODO: Implement cross_mount_points check with pathlib if needed
            # Currently pathlib.walk doesn't support cross_mount_points directly in the same way os.walk does?
            # Actually pathlib.walk is new in 3.12, let's stick to os.walk or use rglob but os.walk is better for modifying dirs
            # Wait, pathlib.Path.walk is 3.12+. Let's use os.walk for compatibility or assume 3.12? 
            # The user environment might not be 3.12. Let's use os.walk but wrap in Path.
            pass

        # Re-implementing with os.walk for broader compatibility and control
        import os
        for root, dirnames, filenames in os.walk(self.root_path, topdown=True):
            root_path = Path(root)
            
            if self.exclude_list:
                dirnames[:] = [d for d in dirnames if d not in self.exclude_list]
            
            if not self.cross_mount_points:
                dirnames[:] = [d for d in dirnames if not os.path.ismount(os.path.join(root, d))]

            for filename in filenames:
                file_path = root_path / filename
                try:
                    stat = file_path.lstat()
                    if stat.st_size > self.min_size:
                        self.file_list.append(FileInfo(stat.st_size, file_path, stat.st_ino))
                except OSError as e:
                    print(f"Error accessing {file_path}: {e}", file=sys.stderr)

    def _find_potential_dupes(self):
        """Group files by size and check partial MD5 for candidates."""
        size_dict: Dict[int, List[FileInfo]] = defaultdict(list)
        for info in self.file_list:
            size_dict[info.size].append(info)

        for size, files in size_dict.items():
            if len(files) > 1:
                for info in files:
                    # TODO: The 10-chunk (80KB) partial hash assumes file differences appear
                    #       early. Files sharing identical headers (ISO images, video containers,
                    #       database dumps) will always pass this check and trigger expensive full
                    #       reads. Consider sampling from multiple offsets or increasing coverage.
                    md5 = self._md5_for_file(info.path, 10)
                    if md5:
                        self.dupe_candidates.append(DupeInfo(size, md5, info.path, info.ino))

        print(f"Processed {len(self.file_list)} files")

    def _confirm_dupes(self):
        """Confirm duplicates by checking full MD5 hash."""
        # Group by partial MD5
        partial_md5_dict: Dict[str, List[DupeInfo]] = defaultdict(list)
        for info in self.dupe_candidates:
            partial_md5_dict[info.md5].append(info)

        for partial_md5, candidates in partial_md5_dict.items():
            if len(candidates) > 1:
                # Calculate full MD5 for these candidates
                full_md5_dict: Dict[str, List[DupeInfo]] = defaultdict(list)
                for info in candidates:
                    full_md5 = self._md5_for_file(info.path)
                    if full_md5:
                        full_md5_dict[full_md5].append(info)

                for full_md5, confirmed_dupes in full_md5_dict.items():
                    if len(confirmed_dupes) > 1:
                        # TODO: Hard links (files sharing the same inode) are reported as
                        #       duplicates even though they occupy no extra disk space. Filter
                        #       groups where all entries share the same inode before appending.
                        for info in confirmed_dupes:
                            self.dupes.append(DupeInfo(info.size, full_md5, info.path, info.ino))

    def _write_dupe_file(self):
        """Write the list of duplicates to a file."""
        try:
            with open(self.output_filename, mode='w') as outfile:
                for info in sorted(self.dupes, key=lambda x: x.size):
                    outfile.write(f"{info.size} {info.md5} {info.ino} {info.path}\n")
        except OSError as e:
            print(f"Error writing to {self.output_filename}: {e}", file=sys.stderr)

def main():
    parser = argparse.ArgumentParser(description="Find duplicate files in a directory.")
    parser.add_argument("-f", "--filename", default="dupes.out", help="save dupe list to FILE")
    parser.add_argument("-d", "--dir", default=".", help="directory to use")
    parser.add_argument("-s", "--size", type=int, default=250000, help="min size of file to check")
    parser.add_argument("-e", "--exclude", action="append", help="directories to exclude")
    args = parser.parse_args()

    print(f"file: {args.filename} dir: {args.dir} size: {args.size}")
    finder = FileDupes(args.dir, size=args.size, outfilename=args.filename, exclude_list=args.exclude)
    finder.run()

if __name__ == '__main__':
    main()
