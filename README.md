# cbrXz

A small command‑line utility to normalize comic archives:

- Converts .cbr/.rar to .cbz
- Copies other supported book types unchanged
- Mirrors the source folder structure into a destination folder

Supported types: .cbr, .rar, .cbz, .zip, .cb7, .7z, .pdf, .epub

## Requirements

- Python 3.8+
- Python packages: see `requirements.txt` (pytest, rarfile)
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

This repo includes CI checks for semantic commit messages and PR titles.

Checks added:

- Commitlint (commit messages): `.github/workflows/commitlint.yml`
- Semantic PR Title (PR title): `.github/workflows/semantic-pr.yml`


Conventional Commit examples:

- `feat(reader): add natural sort of pages`
- `fix(zip): skip __MACOSX and Thumbs.db`
- `docs(readme): add install notes`
- Breaking: `feat!: change default compression to stored`

## Go rewrite (experimental)

An experimental Go implementation lives on the `go-rewrite` branch under `cmd/cbrxz`.

Build and run:

- pwsh:
  - go build -o .\.bin\cbrxz .\cmd\cbrxz
  - .\.bin\cbrxz --version



## License and Warranty

- No license is provided.
- This software is provided “as is,” without warranty of any kind, express or implied. Use at your own risk.
