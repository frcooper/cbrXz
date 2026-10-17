# AGENTS.md

Notes for anyone (human or agent) changing this repo. User-facing docs live in `README.md`.

## Layout

- `cbrXz.py` is the whole tool: a single module with a click CLI (`main`). Function names are camelCase; keep to that.
- `tests/unit/` and `tests/integration/` hold most tests. `tests/test_extensions.py` runs against the real archives in `tests/fixtures/`.
- `tests/fixtures/*` and the images in `tests/src_files/` are Git LFS objects. Run `git lfs pull` first, or the archive tests compare ~130-byte pointer files and skip the real RAR path without failing.

## Tests

```bash
pytest -q
```

The RAR tests need an extractor on PATH: UnRAR, bsdtar/libarchive, or 7-Zip. CI runs Ubuntu and Windows on Python 3.12 and 3.14. Path separators, `os.replace` and temp-dir placement differ between those OSes, so be careful with path handling.

## Commit messages and releases

Every push to `master` runs `python-semantic-release`. It reads the commit messages since the last tag to choose the next version, writes `CHANGELOG.md`, tags `vX.Y.Z` and creates the GitHub release. Commitlint (`@commitlint/config-conventional`) checks messages on PRs and on pushes to `master`.

- Subject: `type(scope): summary`, e.g. `fix(zip): skip __MACOSX entries`. Scopes in use include `cli`, `zip`, `comicinfo`, `inplace` and `readme`.
- `feat` gives a minor bump. `fix` and `perf` give a patch bump. `docs`, `test`, `refactor`, `ci`, `chore` and `build` don't release anything.
- A breaking change (`feat!:` or a `BREAKING CHANGE:` footer) gives a major bump.
- PRs are merged with merge commits, so each commit on the branch ends up in the changelog. Write each one as a changelog line.
- Don't edit `project.version` in `pyproject.toml` or `CHANGELOG.md` by hand. The release job writes both, then commits them as a bare `X.Y.Z` subject with `[skip ci]`.
