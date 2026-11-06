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

`master` is protected: changes land through squash-merged PRs that pass CI, and the PR title becomes the commit subject on `master`. Commitlint (`@commitlint/config-conventional`) checks PR commits and pushes to `master`.

Merging never releases anything. `python-semantic-release` reads the commit subjects on `master` since the last tag to choose the next version and write `CHANGELOG.md`, but only when a release is prepared on purpose:

1. On an up-to-date `master` checkout, run `semantic-release version --no-commit --no-tag --no-push --no-vcs-release` (pinned `python-semantic-release==10.6.2`). It updates `project.version` in `pyproject.toml` and `CHANGELOG.md` without committing.
2. Move those changes to a branch and open a PR titled `chore(release): X.Y.Z`. Squash-merge it once CI passes.
3. Run the **Release** workflow on `master` with version `vX.Y.Z`. It checks the version, changelog and history, retests that exact commit, then tags it and publishes the GitHub release with that version's changelog section.

`v*` tags can't be moved or deleted once published.

- Subject: `type(scope): summary`, e.g. `fix(zip): skip __MACOSX entries`. Scopes in use include `cli`, `zip`, `comicinfo`, `inplace` and `readme`.
- `feat` gives a minor bump. `fix` and `perf` give a patch bump. `docs`, `test`, `refactor`, `ci`, `chore` and `build` don't bump the version.
- A breaking change (`feat!:` or a `BREAKING CHANGE:` footer) gives a major bump.
- PRs are squash-merged, so the PR title is the changelog line. Write it as one; keep one change per PR.
- Don't edit `project.version` in `pyproject.toml` or `CHANGELOG.md` by hand. Let `semantic-release` write both in the release PR.
