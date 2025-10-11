package main

import (
	"archive/zip"
	"errors"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
)

var (
	version    = "v0.0.0"
	bookTypes  = map[string]bool{`.cbr`: true, `.rar`: true, `.cbz`: true, `.zip`: true, `.cb7`: true, `.7z`: true, `.pdf`: true, `.epub`: true}
	junkFiles  = map[string]bool{"Thumbs.db": true, ".DS_Store": true}
)

func main() {
	var (
		root     string
		replace  bool
		dryRun   bool
		logLevel string
		showVer  bool
	)
	flag.StringVar(&root, "root", "", "Override root for relative paths")
	flag.BoolVar(&replace, "replace", false, "Overwrite existing destination files")
	flag.BoolVar(&replace, "F", false, "Overwrite existing destination files (short)")
	flag.BoolVar(&dryRun, "dry-run", false, "Plan actions but do not write outputs")
	flag.BoolVar(&dryRun, "N", false, "Plan actions but do not write outputs (short)")
	flag.StringVar(&logLevel, "log-level", "INFO", "Logging verbosity: DEBUG, INFO, WARNING, ERROR")
	flag.BoolVar(&showVer, "version", false, "Print version and exit")
	flag.Parse()

	if showVer {
		fmt.Println(version)
		return
	}

	args := flag.Args()
	if len(args) != 2 {
		fmt.Fprintf(os.Stderr, "Usage: cbrxz [options] SRC DST\n")
		flag.PrintDefaults()
		os.Exit(2)
	}
	src := abs(args[0])
	dst := abs(args[1])

	lvl := strings.ToUpper(logLevel)
	enableDebug := lvl == "DEBUG"
	logger := log.New(os.Stderr, "", log.LstdFlags)

	if !exists(src) {
		fatalf("Source not found: %s", src)
	}
	if isFile(dst) {
		fatalf("Destination must be a directory (not a file): %s", dst)
	}
	if err := os.MkdirAll(dst, 0o755); err != nil {
		fatalf("Cannot create destination directory: %s (%v)", dst, err)
	}

	relBase := src
	if isFile(src) {
		// single-file mode
		relBase = filepath.Dir(src)
	}
	if root != "" {
		rootAbs := abs(root)
		rel, err := filepath.Rel(rootAbs, src)
		if err != nil || strings.HasPrefix(rel, "..") {
			fatalf("%s is not the child of %s", src, rootAbs)
		}
		relBase = rootAbs
	}

	if enableDebug {
		logger.Printf("source: %s", src)
		logger.Printf("destination: %s", dst)
	}

	var files []string
	if isFile(src) {
		files = []string{src}
	} else {
		filepath.WalkDir(src, func(path string, d fs.DirEntry, err error) error {
			if err != nil {
				return err
			}
			if d.IsDir() {
				return nil
			}
			ext := strings.ToLower(filepath.Ext(d.Name()))
			if bookTypes[ext] {
				files = append(files, path)
			}
			return nil
		})
	}
	sort.Strings(files)

	logger.Printf("beginning - %d books of %d files.", len(files), len(files))
	for _, book := range files {
		if enableDebug {
			logger.Printf("processing %s", book)
		}
		rel, _ := filepath.Rel(relBase, book)
		rel = filepath.ToSlash(rel)
		dir, base := filepath.Split(rel)
		name := strings.TrimSuffix(base, filepath.Ext(base))
		ext := strings.ToLower(filepath.Ext(base))

		bookDstDir := filepath.Join(dst, filepath.FromSlash(dir))
		if !dryRun {
			_ = os.MkdirAll(bookDstDir, 0o755)
		}

		if ext == ".cbr" || ext == ".rar" {
			outName := name + ".cbz"
			outPath := filepath.Join(bookDstDir, outName)
			if !exists(outPath) || replace {
				if dryRun {
					logger.Printf("EVENT: would convert %s -> %s", book, outPath)
					continue
				}
				if err := convertRarToCbz(book, outPath, enableDebug, logger); err != nil {
					// Fallback: treat as NotRarFile -> copy bytes into .cbz
					if enableDebug {
						logger.Printf("RAR convert failed (%v), copying to %s", err, outPath)
					}
					copyFile(book, outPath, replace)
				}
			}
			continue
		}

		// non-RAR copy with rename rules
		destName := base
		if ext == ".zip" {
			destName = name + ".cbz"
		} else if ext == ".7z" {
			destName = name + ".cb7"
		}
		destPath := filepath.Join(bookDstDir, destName)
		if !exists(destPath) || replace {
			if dryRun {
				logger.Printf("EVENT: would copy %s -> %s", book, destPath)
				continue
			}
			copyFile(book, destPath, replace)
		}
	}
	logger.Printf("completed")
}

func convertRarToCbz(rarPath, outPath string, debug bool, logger *log.Logger) error {
	// temp dir for extraction
	tmpDir, err := os.MkdirTemp("", "cbrxz-")
	if err != nil {
		return err
	}
	defer os.RemoveAll(tmpDir)

	// Try unrar, then bsdtar
	if err := runExtract("unrar", []string{"x", "-o+", "-inul", "-y", rarPath, tmpDir}); err != nil {
		if debug {
			logger.Printf("unrar failed: %v", err)
		}
		if err2 := runExtract("bsdtar", []string{"-xf", rarPath, "-C", tmpDir}); err2 != nil {
			if debug {
				logger.Printf("bsdtar failed: %v", err2)
			}
			return errors.New("no extractor available or invalid RAR")
		}
	}

	// Build cbz as stored
	// write to temp file then move
	tmpZip := outPath + ".tmp"
	zf, err := os.Create(tmpZip)
	if err != nil {
		return err
	}
	zw := zip.NewWriter(zf)
	defer func() {
		zw.Close()
		zf.Close()
	}()

	// walk and add files (skip junk and __MACOSX)
	err = filepath.WalkDir(tmpDir, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			// skip __MACOSX dir
			if d.Name() == "__MACOSX" {
				return filepath.SkipDir
			}
			return nil
		}
		rel, _ := filepath.Rel(tmpDir, path)
		rel = filepath.ToSlash(rel)
		base := filepath.Base(rel)
		if junkFiles[base] || strings.HasPrefix(rel, "__MACOSX/") {
			return nil
		}
		// natural-ish order is ensured by outer walk order + final sort below
		return nil
	})
	if err != nil {
		return err
	}
	// Collect files again for deterministic order
	var entries []string
	filepath.WalkDir(tmpDir, func(path string, d fs.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			return nil
		}
		rel, _ := filepath.Rel(tmpDir, path)
		rel = filepath.ToSlash(rel)
		base := filepath.Base(rel)
		if junkFiles[base] || strings.HasPrefix(rel, "__MACOSX/") {
			return nil
		}
		entries = append(entries, rel)
		return nil
	})
	sort.Strings(entries)
	for _, rel := range entries {
		path := filepath.Join(tmpDir, filepath.FromSlash(rel))
		fh := &zip.FileHeader{Name: rel, Method: zip.Store}
		w, err := zw.CreateHeader(fh)
		if err != nil {
			return err
		}
		f, err := os.Open(path)
		if err != nil {
			return err
		}
		if _, err := io.Copy(w, f); err != nil {
			f.Close()
			return err
		}
		f.Close()
	}

	// move into place
	if exists(outPath) {
		_ = os.Remove(outPath)
	}
	zw.Close()
	zf.Close()
	return os.Rename(tmpZip, outPath)
}

func runExtract(cmd string, args []string) error {
	c := exec.Command(cmd, args...)
	c.Stdout = nil
	c.Stderr = nil
	return c.Run()
}

func copyFile(src, dst string, replace bool) {
	if exists(dst) && replace {
		_ = os.Remove(dst)
	}
	in, err := os.Open(src)
	if err != nil {
		fatalf("copy open src: %v", err)
	}
	defer in.Close()
	out, err := os.Create(dst)
	if err != nil {
		fatalf("copy create dst: %v", err)
	}
	if _, err := io.Copy(out, in); err != nil {
		out.Close()
		fatalf("copy: %v", err)
	}
	out.Close()
}

func exists(p string) bool { _, err := os.Stat(p); return err == nil }
func isFile(p string) bool {
	fi, err := os.Stat(p)
	return err == nil && !fi.IsDir()
}
func abs(p string) string {
	ap, _ := filepath.Abs(p)
	return ap
}
func fatalf(format string, a ...any) {
	fmt.Fprintf(os.Stderr, format+"\n", a...)
	os.Exit(2)
}
