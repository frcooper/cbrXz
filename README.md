# cbrXz

A small command‑line utility to normalize comic archives:

- Converts .cbr/.rar and .cb7/.7z to .cbz
- Copies other supported book types unchanged
- Mirrors the source folder structure into a destination folder

Supported types: .cbr, .rar, .cbz, .zip, .cb7, .7z, .pdf, .epub

## Requirements

- Python 3.8+
- Python packages: see `requirements.txt` (pytest, rarfile, click, Pillow, py7zr)
- 7z extraction is built in (py7zr); no external tool needed.
- RAR extraction:
  - Windows: UnRAR.exe on PATH, or bsdtar/libarchive
  - macOS/Linux: unrar or bsdtar/libarchive on PATH

## Install

### Windows (PowerShell)

```pwsh
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
winget install RARLab.WinRAR
```

### Linux/macOS (bash)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

Debian/Ubuntu:     sudo apt-get update && sudo apt-get install unrar || sudo apt-get install libarchive-tools
Fedora/RHEL:       sudo dnf install unrar || sudo dnf install bsdtar
macOS (Homebrew):  brew install unrar || brew install libarchive
```

## Usage

```pwsh
python cbrXz.py SRC DST [options]
python cbrXz.py SRC --in-place [options]
```

- `SRC`: source file or directory
- `DST`: destination directory (created if missing); not given with `--in-place`

### Options

- `-F, --replace`             Overwrite existing destination files
- `-N, --dry-run`             Log actions but do not write outputs
- `-i, --in-place`            Process SRC where it lies instead of writing to DST (see below)
- `--trash PATH`              Where `--in-place` moves unreadable books (default: `SRC/_trash`)
- `--journal PATH`            Record of books `--in-place` has finished (default: `SRC/_cbrXz_journal.jsonl`)
- `--root PATH`               Treat PATH as the source root when computing relative paths
- `--log-level {ERROR,WARNING,INFO,DEBUG}`  Set logging verbosity (default: INFO)
- `-V, --version`             Print release tag (vX.Y.Z) and exit

### Behavior

- Extensions are matched case‑insensitively.
- Other types are copied with metadata preserved (via `shutil.copy2`).
- .cbr/.rar and .cb7/.7z are extracted to a temp dir and re‑packed as `.cbz`; output goes under `DST/<relative subpath>/`.
  - A .cbr/.cb7 that is really a zip is copied to `.cbz` (with the page data handling below).
  - A .cb7/.7z that can't be extracted (encrypted, unsupported compression method, or not actually a 7z) is copied unchanged as `.cb7`, with a warning.
- Repacked `.cbz` archives use stored (uncompressed) ZIP entries. Most comic pages are already compressed image formats (JPEG/PNG/WebP), so deflation adds CPU time with negligible size savings; the remaining text/XML is a tiny fraction of total size.
- Repacked `.cbz` archives get page data in `ComicInfo.xml`. If the archive has no `ComicInfo.xml`, one is created; if it has one, only missing `PageCount`, `<Pages>`, `<Page>` entries and attributes are added, and other existing values are kept. The exception is stale image data: if `<Page>` entries exist for every page and are corroborated (see below), any size, dimension, format, depth or DPI value that differs from its image is corrected (and `DoublePage` follows corrected dimensions), e.g. when pages were resized after `ComicInfo.xml` was written. Each correction is logged. Each page (image files, in archive order) gets:
  - `ImageSize`, `ImageWidth`, `ImageHeight`, and `DoublePage="true"` for landscape pages (ComicInfo schema attributes)
  - `ImageFormat` (e.g. `JPEG`, `PNG`), `ImageBitDepth` (bits per pixel), `ImageDpi` (`300`, or `300x72` when axes differ, when the image records it) — extensions outside the ComicInfo schema
  - Page data is only written when it is guaranteed to describe the right pages. Otherwise the archive is written without it and a warning is logged. Writing is skipped when:
    - page file names sort differently in plain, case‑insensitive and natural order (e.g. `p1, p2, p10`), or two names have the same page number (`p1`, `p01`)
    - the archive contains images some readers skip (`.tif`, `.avif`, `.jxl`, `.heic`, `.jp2`)
    - any page image cannot be read
    - an existing `PageCount` differs from the number of images, or an existing `<Page>` value (size, dimensions, format, depth, DPI) differs from the image at that index and the `<Page>` entries don't cover every page
    - existing `<Page>` entries are out of range or duplicated, or cannot be corroborated by a matching `PageCount` or a matching value
- Copied `.cbz`/`.zip` archives finish with a `ComicInfo.xml` holding page data whenever it can be written correctly (same checks as above):
  - No `ComicInfo.xml`, or one missing page data or with stale page data: the copy is *patched*. The new `ComicInfo.xml` (stored) is written where the archive's central directory was, followed by a new central directory, so page entries are never rewritten or recompressed and only image headers are read. This costs the copy plus a few KB, whatever the size of the book. A replaced `ComicInfo.xml` keeps its name and timestamp; its old bytes stay in the file, unreferenced (a reader that ignores the central directory and scans the file front to back may still see the old one).
  - Page data already complete, or it can't be verified, or the archive can't be read or patched (e.g. an encrypted `ComicInfo.xml`): copied byte‑for‑byte.
- PDF and EPUB are copied byte‑for‑byte.
- Relative paths use `os.path.relpath` for robustness; zip arcnames use forward slashes.
- Dry‑run skips file system writes but will still walk the tree and plan actions.

### In‑place mode

`--in-place` brings an existing tree up to the same state a copy would have, without a second copy of it:

- `.cbz` books whose `ComicInfo.xml` is missing page data, or has stale page data, are patched in place (see above), keeping their modification time. Books already up to date are only read, never written.
- `.zip` books are renamed to `.cbz`.
- `.cbr/.rar/.cb7/.7z` books are repacked as `.cbz` next to the original, and the original is deleted once the `.cbz` is in place.
- A book's real type is detected from its contents, not its name, so a `.cbz` that is really a RAR is repacked rather than treated as broken.
- Unreadable books — not a zip, RAR or 7z at all (including empty and truncated files), or a corrupt RAR/7z — are moved to the trash folder, keeping their path relative to SRC. Nothing is deleted outright; a name already in the trash gets a ` (1)` suffix. The trash folder is skipped when walking SRC.
- A 7z that is encrypted or uses an unsupported compression method is left as it is.
- When the `.cbz` name is already taken by another file, the book is left alone with a warning, unless `--replace` is given.
- PDF and EPUB books are left as they are.
- Repacked books are built as a `.part` file next to the book and renamed over it. Before a book is patched, the bytes the patch will overwrite (its central directory, usually a few KB) are saved beside the journal: a patch that fails is undone at once, and one cut short by a crash or power loss is undone at the start of the next run.
- A book that fails (I/O error, permissions, ...) is logged and the run carries on; the exit code is 1 if any book failed.
- The run ends with a count of books that were current, updated, converted, trashed, kept, skipped, failed and journaled.

#### Resume journal

In‑place runs keep a journal (`--journal PATH`, default `SRC/_cbrXz_journal.jsonl`): one JSON line per finished book with its size and modification time. A rerun skips a book whose size and mtime still match without opening it, so an interrupted run picks up where it stopped and later runs only look at new or changed books. Paths are stored relative to SRC with forward slashes, so one journal works whether the tree is reached through a share or on the server itself. Delete the journal to have every book checked again (e.g. after upgrading cbrXz). `--dry-run` reads the journal but never writes it.

```pwsh
python cbrXz.py "D:\Comics\Library" --in-place --dry-run   # see what would change
python cbrXz.py "D:\Comics\Library" --in-place --trash "D:\Comics\_trash"
```

## Examples

Convert a tree and overwrite any existing outputs:

```pwsh
python cbrXz.py "C:\Comics\Inbox" "D:\Comics\Library" --replace --log-level INFO
```

Process a single file:

```pwsh
python cbrXz.py .\issue01.cbr .\out
```

Constrain relative paths to a specific root (useful when SRC is nested):

```pwsh
python cbrXz.py .\nested\series .\out --root .\nested
```

Print the current release tag:

```pwsh
python cbrXz.py --version
# or
python cbrXz.py -V
```

## Tests and fixtures

- Test runner: `pytest`
- Real binary fixtures live in `tests/fixtures/` and are used by tests in `tests/test_extensions.py`.
  - Copied fixtures are verified byte‑for‑byte; the `.cb7` fixture is checked as a repacked `.cbz`.
  - RAR fixtures: if a fixture is a real RAR and an extractor is available, output is validated as a real zip (`.cbz`). If not a real RAR, the test expects an unchanged byte copy to `.cbz`.

Run all tests:

```pwsh
pytest -q
```

## Enforcing Conventional Commits

Commit messages drive the release: `semantic-release` parses them to pick the
next version, so the format is enforced in CI.

- Commitlint (commit messages, on push and PR): `.github/workflows/commitlint.yml`
- Tests and release: `.github/workflows/ci.yml`

Merge commits are ignored by commitlint's defaults.

Conventional Commit examples:

- `feat(reader): add natural sort of pages`
- `fix(zip): skip __MACOSX and Thumbs.db`
- `docs(readme): add install notes`
- Breaking: `feat!: change default compression to stored`

## License and Warranty

- No license is provided.
- This software is provided “as is,” without warranty of any kind, express or implied. Use at your own risk.
