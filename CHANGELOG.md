# CHANGELOG

<!-- version list -->

## v1.4.0 (2026-10-01)

### Bug Fixes

- **comicinfo**: Insert PageCount in schema order
  ([`f9a6de5`](https://github.com/frcooper/cbrXz/commit/f9a6de535b3139c6bacaf7f549eaebee8a2782b1))

- **comicinfo**: Only write page data that is guaranteed correct
  ([`f8b038a`](https://github.com/frcooper/cbrXz/commit/f8b038aa3739b70673b855372391da81c2d012c2))

### Features

- **7z**: Repack .cb7/.7z books as .cbz
  ([`ae9683b`](https://github.com/frcooper/cbrXz/commit/ae9683b73169a04fcd66df4c4487aac9256f6671))

- **comicinfo**: Append page data to copied zips without ComicInfo.xml
  ([`bfe0597`](https://github.com/frcooper/cbrXz/commit/bfe059762317f7d1e34f7c172c97777f0bb0a83a))

- **comicinfo**: Fill page data into existing ComicInfo.xml in copied zips
  ([`6c9e401`](https://github.com/frcooper/cbrXz/commit/6c9e4014ac5014bb4185795db6469052822d2ad3))

- **comicinfo**: Write full page data into ComicInfo.xml on repack
  ([`2802bc4`](https://github.com/frcooper/cbrXz/commit/2802bc4929ced54d69cee895d138a2cc35132acd))


## v1.3.2 (2026-09-28)

### Bug Fixes

- **filters**: Skip books tagged (portuguese)
  ([`588a7ab`](https://github.com/frcooper/cbrXz/commit/588a7ab341395654a8e4af26c1b25bbf9c6054f2))

### Testing

- **filters**: Cover Portuguese tags in filterBook
  ([`5dd842e`](https://github.com/frcooper/cbrXz/commit/5dd842e4897c406b91151de8f360f9c3d1b71cd7))


## v1.3.1 (2026-09-06)

### Bug Fixes

- Add conditional to skip CI based on PR titles and commit messages
  ([`6400246`](https://github.com/frcooper/cbrXz/commit/640024619019ce05f53894b36dc8a26f46dd7f78))

- Add dry-run logging for extraction events in main function
  ([`f88332a`](https://github.com/frcooper/cbrXz/commit/f88332a8187ab0310ca80c84db4435efb5871ec3))

- Adjust semantic-release configuration
  ([`517fe52`](https://github.com/frcooper/cbrXz/commit/517fe52dbdcccede0378d48772fafc0b62b7e368))

- Correct Python version classifier and update semantic-release configuration
  ([`807b8e4`](https://github.com/frcooper/cbrXz/commit/807b8e43953683de10b4039e4a1f78a2c466d4ff))

- Enhance filterBook function to correctly identify and filter out specific book paths
  ([`7642fdd`](https://github.com/frcooper/cbrXz/commit/7642fddee37d557f61603f8472f510493229ca64))

- Remove redundant zip.close() call in main function
  ([`bf6bc94`](https://github.com/frcooper/cbrXz/commit/bf6bc94792d07ee4da44129da8b0ec05139095a6))

- Remove unnecessary blank line in README.md
  ([`b12d3dc`](https://github.com/frcooper/cbrXz/commit/b12d3dc68ed2d382d0b15d454a5f993d675ce353))

- Simplify version retrieval in get_version function
  ([`a351ea3`](https://github.com/frcooper/cbrXz/commit/a351ea3f81d2d271c7b59d7fc6c977e61c477000))

- **filters**: Skip books tagged (german)
  ([`6ae1c5f`](https://github.com/frcooper/cbrXz/commit/6ae1c5fa1bf0308bba33bce918429a6e28ff2992))

- **repack**: Finalize cbz before publishing it
  ([`62382dc`](https://github.com/frcooper/cbrXz/commit/62382dcfc3f098a7d7682d793b8e54c5f6198785))

### Build System

- **release**: Add [skip ci] to the release commit message
  ([`e0e40ea`](https://github.com/frcooper/cbrXz/commit/e0e40ea634c9324603f7ae4713bfe2a6aa4d1089))

- **release**: Repair semantic-release config and resume from 1.3.0
  ([`ff05937`](https://github.com/frcooper/cbrXz/commit/ff059372a2fa7b530c243291e3ddaff75346f288))

### Continuous Integration

- Check out lfs fixtures and install a rar extractor
  ([`d10f7d2`](https://github.com/frcooper/cbrXz/commit/d10f7d2238432e85336c1bbb686a8e3ee0782781))

- Prune dead workflows and deduplicate the test matrix
  ([`a37d500`](https://github.com/frcooper/cbrXz/commit/a37d500262fa498cadb1831943159a7e017d0255))

### Documentation

- **readme**: Drop reference to the removed semantic-pr workflow
  ([`7489aef`](https://github.com/frcooper/cbrXz/commit/7489aefc92d16cb2492b81be8caf5dc7ca85907e))

### Refactoring

- **repack**: Collapse duplicate rar error handlers
  ([`757fcea`](https://github.com/frcooper/cbrXz/commit/757fcea6091f938b1d673fa194e364a245b140ff))


## v1.3.0 (2025-10-11)


## v1.2.0 (2025-10-11)

### Features

- Add CI checks for enforcing conventional commits and PR titles
  ([`62fb12a`](https://github.com/frcooper/cbrXz/commit/62fb12a2caef17a17d3262086b2867c00b6b45f2))


## v1.1.3 (2025-10-11)


## v1.1.2 (2025-10-11)


## v1.1.1 (2025-10-11)


## v1.1.0 (2025-10-11)


## v1.0.1 (2025-10-11)


## v1.0.0 (2025-10-11)

- Initial Release
