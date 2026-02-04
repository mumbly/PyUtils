import unittest
import os
import shutil
import tempfile
from FileDupeFinder import FileDupes

class TestFileDupes(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.files = []

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def create_file(self, filename, content, size=None):
        path = os.path.join(self.test_dir, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            if size:
                f.write(os.urandom(size))
            else:
                f.write(content)
        return path

    def test_find_dupes(self):
        # Create unique files
        self.create_file("file1.txt", b"content1")
        self.create_file("file2.txt", b"content2")
        
        # Create duplicates (size > 0 to match default behavior if we lower threshold)
        content = b"duplicate_content" * 100
        self.create_file("dupe1.txt", content)
        self.create_file("subdir/dupe2.txt", content)
        
        # Create file with same size but different content
        self.create_file("same_size.txt", b"different_content" * 100)[:len(content)]

        # Run finder with small size threshold
        finder = FileDupes(self.test_dir, size=10, outfilename=os.path.join(self.test_dir, "dupes.out"))
        finder.run()
        
        # Check results
        self.assertEqual(len(finder.dupes), 2)
        
        # Verify the duplicates are the ones we expect
        filenames = sorted([os.path.basename(f.path) for f in finder.dupes])
        self.assertEqual(filenames, ["dupe1.txt", "dupe2.txt"])

if __name__ == '__main__':
    unittest.main()
