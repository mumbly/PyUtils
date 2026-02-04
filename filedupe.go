package main

import (
	"bufio"
	"crypto/md5"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"sync"
	"syscall"
)

type fileInfo struct {
	size       int64
	path       string
	inode      uint64
	partialMD5 string
	fullMD5    string
}

type FileDupes struct {
	rootPath         string
	minSize          int64
	excludeList      []string
	crossMountPoints bool
	outputFilename   string
	fileList         []fileInfo
	dupeCandidates   []fileInfo
	dupes            []fileInfo
	dirCount         int
}

func newFileDupes(path string, size int64, outfilename string) *FileDupes {
	return &FileDupes{
		rootPath:         path,
		minSize:          size,
		excludeList:      []string{"Backups.backupdb"},
		crossMountPoints: false,
		outputFilename:   outfilename,
	}
}

func (fd *FileDupes) run() {
	fd.walkTree()
	fmt.Printf("Found %d files to be processed\n", len(fd.fileList))
	fd.findPotentialDupes()
	fd.confirmDupes()
	fd.writeDupeFile()
	fmt.Printf("Found %d files that appear to be duplicates\n", len(fd.dupes))
}

func (fd *FileDupes) walkTree() {
	err := filepath.Walk(fd.rootPath, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			// Handle permission errors or other issues by logging and skipping
			fmt.Fprintf(os.Stderr, "Error accessing path %q: %v\n", path, err)
			return filepath.SkipDir
		}
		if info.IsDir() {
			fd.dirCount++
			for _, exclude := range fd.excludeList {
				if info.Name() == exclude {
					return filepath.SkipDir
				}
			}
			if !fd.crossMountPoints && isMount(path) {
				return filepath.SkipDir
			}
		} else if info.Size() > fd.minSize {
			fd.fileList = append(fd.fileList, fileInfo{
				size:  info.Size(),
				path:  path,
				inode: getInode(info),
			})
		}
		return nil
	})
	if err != nil {
		fmt.Printf("Error walking the path %v: %v\n", fd.rootPath, err)
	}
}

func (fd *FileDupes) findPotentialDupes() {
	sizeMap := make(map[int64][]fileInfo)
	for _, file := range fd.fileList {
		sizeMap[file.size] = append(sizeMap[file.size], file)
	}

	var wg sync.WaitGroup
	semaphore := make(chan struct{}, 8) // Limit concurrent goroutines
	var mu sync.Mutex

	for _, files := range sizeMap {
		if len(files) > 1 {
			for i := range files {
				wg.Add(1)
				semaphore <- struct{}{}
				go func(f *fileInfo) {
					defer wg.Done()
					defer func() { <-semaphore }()
					
					// Partial MD5
					pMD5 := calculateMD5(f.path, 10)
					if pMD5 != "" {
						f.partialMD5 = pMD5
						mu.Lock()
						fd.dupeCandidates = append(fd.dupeCandidates, *f)
						mu.Unlock()
					}
				}(&files[i])
			}
		}
	}
	wg.Wait()
	fmt.Printf("Processed %d files\n", len(fd.fileList))
}



// Redefining confirmDupes for the actual implementation
// Redefining confirmDupes for the actual implementation
func (fd *FileDupes) confirmDupes() {
	partialMD5Map := make(map[string][]fileInfo)
	for _, file := range fd.dupeCandidates {
		partialMD5Map[file.partialMD5] = append(partialMD5Map[file.partialMD5], file)
	}

	var wg sync.WaitGroup
	semaphore := make(chan struct{}, 8)
	var mu sync.Mutex
	var fullyHashedFiles []fileInfo

	for _, files := range partialMD5Map {
		if len(files) > 1 {
			for _, f := range files {
				wg.Add(1)
				semaphore <- struct{}{}
				go func(info fileInfo) {
					defer wg.Done()
					defer func() { <-semaphore }()
					
					info.fullMD5 = calculateMD5(info.path, 0)
					if info.fullMD5 != "" {
						mu.Lock()
						fullyHashedFiles = append(fullyHashedFiles, info)
						mu.Unlock()
					}
				}(f)
			}
		}
	}
	wg.Wait()

	// Now group by full MD5
	fullMD5Map := make(map[string][]fileInfo)
	for _, file := range fullyHashedFiles {
		fullMD5Map[file.fullMD5] = append(fullMD5Map[file.fullMD5], file)
	}

	for _, files := range fullMD5Map {
		if len(files) > 1 {
			fd.dupes = append(fd.dupes, files...)
		}
	}
}

func (fd *FileDupes) writeDupeFile() {
	file, err := os.Create(fd.outputFilename)
	if err != nil {
		fmt.Printf("Error creating output file: %v\n", err)
		return
	}
	defer file.Close()

	writer := bufio.NewWriter(file)
	defer writer.Flush()

	sort.Slice(fd.dupes, func(i, j int) bool {
		return fd.dupes[i].size < fd.dupes[j].size
	})

	for _, file := range fd.dupes {
		_, err := fmt.Fprintf(writer, "%d %s %d %s\n", file.size, file.fullMD5, file.inode, file.path)
		if err != nil {
			fmt.Printf("Error writing to output file: %v\n", err)
			return
		}
	}
}

func calculateMD5(filename string, numChunks int) string {
	file, err := os.Open(filename)
	if err != nil {
		return ""
	}
	defer file.Close()

	hash := md5.New()
	buf := make([]byte, 8192)
	
	// If numChunks is set, read that many chunks.
	// If numChunks is 0 (or negative), read until EOF.
	
	for i := 0; numChunks <= 0 || i < numChunks; i++ {
		n, err := file.Read(buf)
		if err != nil {
			if err == io.EOF {
				break
			}
			return ""
		}
		hash.Write(buf[:n])
	}
	return fmt.Sprintf("%x", hash.Sum(nil))
}

func isMount(path string) bool {
	// This is a simplified check and may not work for all cases
	parent := filepath.Dir(path)
	pathStat, err := os.Stat(path)
	if err != nil {
		return false
	}
	parentStat, err := os.Stat(parent)
	if err != nil {
		return false
	}
	
	pathSys := pathStat.Sys().(*syscall.Stat_t)
	parentSys := parentStat.Sys().(*syscall.Stat_t)
	
	return pathSys.Dev != parentSys.Dev
}

func getInode(info os.FileInfo) uint64 {
	return info.Sys().(*syscall.Stat_t).Ino
}

func main() {
	filename := flag.String("f", "dupes.out", "save dupe list to FILE")
	dir := flag.String("d", ".", "directory to use")
	size := flag.Int64("s", 250000, "min size of file to check")
	// Handling exclude list is a bit tricky with standard flag, 
	// usually requires a custom Value type for repeated flags.
	// For simplicity, let's stick to the default exclude list or add a simple comma-separated string if needed.
	// The Python script used action="append".
	// We can implement a string slice flag.
	var excludes stringSlice
	flag.Var(&excludes, "e", "directories to exclude (can be repeated)")
	
	flag.Parse()

	fmt.Printf("file: %s dir: %s size: %d\n", *filename, *dir, *size)
	fd := newFileDupes(*dir, *size, *filename)
	if len(excludes) > 0 {
		fd.excludeList = excludes
	}
	fd.run()
}

// stringSlice handles repeated string flags
type stringSlice []string

func (s *stringSlice) String() string {
	return fmt.Sprintf("%v", *s)
}

func (s *stringSlice) Set(value string) error {
	*s = append(*s, value)
	return nil
}
