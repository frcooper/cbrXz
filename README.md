# cbrXz

A small command‑line utility to normalize comic archives:

- Converts .cbr/.rar to .cbz
- Copies other supported book types unchanged
- Mirrors the source folder structure into a destination folder

Supported types: .cbr, .rar, .cbz, .zip, .cb7, .7z, .pdf, .epub

## Requirements

- Python 3.8+
- Python packages: see `requirements.txt` (pytest, rarfile, click, Pillow)
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
```

- `SRC`: source file or directory
- `DST`: destination directory (created if missing)

### Options

- `-F, --replace`             Overwrite existing destination files
- `-N, --dry-run`             Log actions but do not write outputs
- `--root PATH`               Treat PATH as the source root when computing relative paths
- `--log-level {ERROR,WARNING,INFO,DEBUG}`  Set logging verbosity (default: INFO)
- `-V, --version`             Print release tag (vX.Y.Z) and exit

### Behavior

- Extensions are matched case‑insensitively.
- Non‑RAR types are copied with metadata preserved (via `shutil.copy2`).
- .cbr/.rar are extracted to a temp dir and re‑packed as `.cbz`; output goes under `DST/<relative subpath>/`.
- Repacked `.cbz` archives use stored (uncompressed) ZIP entries. Most comic pages are already compressed image formats (JPEG/PNG/WebP), so deflation adds CPU time with negligible size savings; the remaining text/XML is a tiny fraction of total size.
- Repacked `.cbz` archives get page data in `ComicInfo.xml`. If the archive has no `ComicInfo.xml`, one is created; if it has one, only missing `PageCount`, `<Pages>`, `<Page>` entries and attributes are added — existing values are never overwritten. Each page (image files, in archive order) gets:
  - `ImageSize`, `ImageWidth`, `ImageHeight`, and `DoublePage="true"` for landscape pages (ComicInfo schema attributes)
  - `ImageFormat` (e.g. `JPEG`, `PNG`), `ImageBitDepth` (bits per pixel), `ImageDpi` (`300`, or `300x72` when axes differ, when the image records it) — extensions outside the ComicInfo schema
  - Page data is only written when it is guaranteed to describe the right pages. Otherwise the archive is written without it and a warning is logged. Writing is skipped when:
    - page file names sort differently in plain, case‑insensitive and natural order (e.g. `p1, p2, p10`), or two names have the same page number (`p1`, `p01`)
    - the archive contains images some readers skip (`.tif`, `.avif`, `.jxl`, `.heic`, `.jp2`)
    - any page image cannot be read
    - an existing `PageCount` differs from the number of images, or an existing `<Page>` value (size, dimensions, format, depth, DPI) differs from the image at that index
    - existing `<Page>` entries are out of range or duplicated, or cannot be corroborated by a matching `PageCount` or a matching value
- Copied `.cbz`/`.zip` archives without a `ComicInfo.xml` get one with page data appended (subject to the same checks). The existing entries are not rewritten, and only image headers are read, so this costs little more than the copy. Archives that already have a `ComicInfo.xml` are copied byte‑for‑byte, as are all other non‑RAR types.
- Relative paths use `os.path.relpath` for robustness; zip arcnames use forward slashes.
- Dry‑run skips file system writes but will still walk the tree and plan actions.

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
  - Non‑RAR fixtures are verified byte‑for‑byte copies.
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
