package main

import (
	"crypto/md5"
	"fmt"
	"os"
	"path/filepath"
	"testing"
)

func createTestFile(t *testing.T, path string, content []byte) {
	err := os.MkdirAll(filepath.Dir(path), 0755)
	if err != nil {
		t.Fatalf("Failed to create directory: %v", err)
	}
	err = os.WriteFile(path, content, 0644)
	if err != nil {
		t.Fatalf("Failed to write file: %v", err)
	}
}

func TestFileDupes(t *testing.T) {
	tempDir, err := os.MkdirTemp("", "filedupe_test")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tempDir)

	// Create unique files
	createTestFile(t, filepath.Join(tempDir, "file1.txt"), []byte("content1"))
	createTestFile(t, filepath.Join(tempDir, "file2.txt"), []byte("content2"))

	// Create duplicates
	content := []byte("duplicate_content_duplicate_content")
	createTestFile(t, filepath.Join(tempDir, "dupe1.txt"), content)
	createTestFile(t, filepath.Join(tempDir, "subdir", "dupe2.txt"), content)

	// Create file with same size but different content
	// Ensure it's the same length as content
	diffContent := []byte("different_content_different_conte")
	if len(diffContent) != len(content) {
		// Pad or truncate to match size
		if len(diffContent) < len(content) {
			diffContent = append(diffContent, make([]byte, len(content)-len(diffContent))...)
		} else {
			diffContent = diffContent[:len(content)]
		}
	}
	createTestFile(t, filepath.Join(tempDir, "same_size.txt"), diffContent)

	outputFile := filepath.Join(tempDir, "dupes.out")
	
	// Initialize FileDupes
	fd := newFileDupes(tempDir, 10, outputFile)
	
	// Run
	fd.run()

	// Check results
	if len(fd.dupes) != 2 {
		t.Errorf("Expected 2 duplicates, got %d", len(fd.dupes))
	}

	// Verify filenames
	foundFiles := make(map[string]bool)
	for _, d := range fd.dupes {
		foundFiles[filepath.Base(d.path)] = true
	}

	if !foundFiles["dupe1.txt"] {
		t.Error("dupe1.txt not found in duplicates")
	}
	if !foundFiles["dupe2.txt"] {
		t.Error("dupe2.txt not found in duplicates")
	}
	if foundFiles["same_size.txt"] {
		t.Error("same_size.txt incorrectly identified as duplicate")
	}
}

func TestCalculateMD5(t *testing.T) {
	tempDir, err := os.MkdirTemp("", "md5_test")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tempDir)

	content := []byte("hello world")
	path := filepath.Join(tempDir, "test.txt")
	createTestFile(t, path, content)

	// Expected MD5
	hasher := md5.New()
	hasher.Write(content)
	expected := fmt.Sprintf("%x", hasher.Sum(nil))

	// Full MD5
	result := calculateMD5(path, 0)
	if result != expected {
		t.Errorf("Expected full MD5 %s, got %s", expected, result)
	}

	// Partial MD5 (should be same for small file)
	resultPartial := calculateMD5(path, 1)
	if resultPartial != expected {
		t.Errorf("Expected partial MD5 %s, got %s", expected, resultPartial)
	}
}
