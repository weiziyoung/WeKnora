import hashlib
import unittest
import tempfile
import os

def calculate_file_hash(file_path: str) -> str:
    """
    Calculates the MD5 hash of the file at the given path.
    Matches the Go implementation: io.Copy(md5.New(), file) -> hex.EncodeToString
    
    Args:
        file_path: Path to the file to hash
        
    Returns:
        Hex string of the MD5 hash
    """
    md5_hash = hashlib.md5()
    with open(file_path, "rb") as f:
        # Read in chunks to handle large files efficiently
        # 4096 is a common buffer size, though larger like 64k is fine too
        for chunk in iter(lambda: f.read(4096), b""):
            md5_hash.update(chunk)
    return md5_hash.hexdigest()

class TestFileHash(unittest.TestCase):
    def setUp(self):
        # Create a temporary file
        self.test_file = tempfile.NamedTemporaryFile(delete=False)
        self.test_file.write(b"hello world") # MD5: 5eb63bbbe01eeed093cb22bb8f5acdc3
        self.test_file.close()
        self.test_file_path = self.test_file.name

    def tearDown(self):
        if os.path.exists(self.test_file_path):
            os.remove(self.test_file_path)

    def test_calculate_file_hash(self):
        # "hello world" md5 is 5eb63bbbe01eeed093cb22bb8f5acdc3
        expected_hash = "5eb63bbbe01eeed093cb22bb8f5acdc3"
        result_hash = calculate_file_hash(self.test_file_path)
        self.assertEqual(result_hash, expected_hash)
        
    def test_calculate_file_hash_empty(self):
        # Empty file md5 is d41d8cd98f00b204e9800998ecf8427e
        empty_file = tempfile.NamedTemporaryFile(delete=False)
        empty_file.close()
        try:
            expected_hash = "d41d8cd98f00b204e9800998ecf8427e"
            result_hash = calculate_file_hash(empty_file.name)
            self.assertEqual(result_hash, expected_hash)
        finally:
            os.remove(empty_file.name)

if __name__ == "__main__":
    unittest.main()
