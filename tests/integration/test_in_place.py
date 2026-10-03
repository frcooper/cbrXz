import json
import os
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import py7zr
import pytest
from PIL import Image


@pytest.fixture
def run_cli(run_cli, tmp_path):
    """run_cli that never lets an in-place test reach the real default trash."""
    def _run(args, cwd=None):
        args = list(args)
        if "--in-place" in args and "--trash" not in args and "--dry-run" not in args:
            args += ["--trash", tmp_path / "trash"]
        return run_cli(args, cwd)
    return _run


def make_book(path: Path, tmp_path: Path, comicinfo: bytes = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for i in range(2):
            img = tmp_path / f"p0{i}.png"
            Image.new("RGB", (30, 45)).save(img)
            zf.write(img, f"p0{i}.png")
        if comicinfo is not None:
            zf.writestr("ComicInfo.xml", comicinfo)
    return path


def make_7z(path: Path, tmp_path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = tmp_path / "p00.png"
    Image.new("RGB", (30, 45)).save(img)
    with py7zr.SevenZipFile(path, "w") as sz:
        sz.write(img, "p00.png")
    return path


def page_heights(book: Path) -> list:
    with zipfile.ZipFile(book) as zf:
        assert zf.testzip() is None
        pages = ET.fromstring(zf.read("ComicInfo.xml")).find("Pages").findall("Page")
    return [p.get("ImageHeight") for p in pages]


@pytest.mark.integration
def test_in_place_updates_books_and_trashes_unreadable(tmp_path, run_cli):
    src = tmp_path / "src"
    stale = make_book(src / "a" / "stale.cbz", tmp_path, b"<ComicInfo><Title>T</Title></ComicInfo>")
    renamed = make_book(src / "a" / "renamed.zip", tmp_path)
    broken = src / "a" / "broken.cbz"
    broken.write_bytes(b"not an archive at all")
    pdf = src / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 not checked")
    pdf_bytes = pdf.read_bytes()

    proc = run_cli([src, "--in-place"])
    assert proc.returncode == 0, proc.stderr or proc.stdout

    assert page_heights(stale) == ["45", "45"]
    assert ET.fromstring(zipfile.ZipFile(stale).read("ComicInfo.xml")).findtext("Title") == "T"
    assert not renamed.exists()
    assert page_heights(src / "a" / "renamed.cbz") == ["45", "45"]
    assert not broken.exists()
    # keeps its path below the folder the trash and the tree share
    assert (tmp_path / "trash" / "src" / "a" / "broken.cbz").read_bytes() == b"not an archive at all"
    assert pdf.read_bytes() == pdf_bytes
    assert not list(src.rglob("*.part"))


@pytest.mark.integration
def test_in_place_leaves_current_books_untouched(tmp_path, run_cli):
    src = tmp_path / "src"
    book = make_book(src / "book.cbz", tmp_path)
    assert run_cli([src, "--in-place"]).returncode == 0
    before = (book.read_bytes(), os.stat(book).st_mtime_ns)

    for args in (["--journal", tmp_path / "other.jsonl"], []):
        proc = run_cli([src, "--in-place", *args])
        assert proc.returncode == 0, proc.stderr or proc.stdout
        assert (book.read_bytes(), os.stat(book).st_mtime_ns) == before
    # checked and found current with a fresh journal, skipped unopened with the old one
    assert "1 journaled" in proc.stderr


@pytest.mark.integration
def test_in_place_converts_7z_and_removes_original(tmp_path, run_cli):
    src = tmp_path / "src"
    make_7z(src / "book.cb7", tmp_path)

    proc = run_cli([src, "--in-place"])
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert not (src / "book.cb7").exists()
    assert page_heights(src / "book.cbz") == ["45"]


@pytest.mark.integration
def test_in_place_does_not_overwrite_existing_cbz(tmp_path, run_cli):
    src = tmp_path / "src"
    make_7z(src / "book.cb7", tmp_path)
    (src / "book.cbz").write_bytes(b"keep me")

    proc = run_cli([src, "--in-place"])
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert (src / "book.cb7").exists()
    # the existing (unreadable) book.cbz is trashed, the .cb7 left for a rerun
    assert (tmp_path / "trash" / "src" / "book.cbz").read_bytes() == b"keep me"


@pytest.mark.integration
def test_in_place_custom_trash_and_dry_run(tmp_path, run_cli):
    src = tmp_path / "src"
    stale = make_book(src / "stale.cbz", tmp_path, b"<ComicInfo/>")
    broken = src / "broken.cbr"
    broken.write_bytes(b"junk")
    trash = tmp_path / "bin"
    before = stale.read_bytes()

    proc = run_cli([src, "--in-place", "--trash", trash, "--dry-run"])
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert stale.read_bytes() == before and broken.exists() and not trash.exists()

    proc = run_cli([src, "--in-place", "--trash", trash])
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert (trash / "src" / "broken.cbr").read_bytes() == b"junk"
    assert page_heights(stale) == ["45", "45"]


@pytest.mark.parametrize("args, message", [
    (["--in-place", "DST"], "DST cannot be given"),
    ([], "Missing argument 'DST'"),
    (["DST", "--trash", "bin"], "only used with --in-place"),
    (["DST", "--journal", "bin"], "only used with --in-place"),
])
def test_in_place_argument_errors(tmp_path, run_cli, args, message):
    src = tmp_path / "src"
    src.mkdir()
    proc = run_cli([src, *[tmp_path / a if a in ("DST", "bin") else a for a in args]])
    assert proc.returncode != 0
    assert message in proc.stderr + proc.stdout


@pytest.mark.integration
def test_in_place_journal_skips_finished_books(tmp_path, run_cli):
    src = tmp_path / "src"
    a = make_book(src / "a.cbz", tmp_path, b"<ComicInfo/>")
    b = make_book(src / "b.cbz", tmp_path)
    assert run_cli([src, "--in-place"]).returncode == 0
    journal = src / "_cbrXz_journal.jsonl"
    recs = [json.loads(l) for l in journal.read_text().splitlines()]
    assert {r["book"]: r["outcome"] for r in recs if "book" in r} == {"a.cbz": "updated", "b.cbz": "updated"}
    assert not (src / "_cbrXz_journal.jsonl.tail").exists()

    # a changed book is looked at again, an unchanged one is not even opened
    make_book(b, tmp_path)
    proc = run_cli([src, "--in-place"])
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "1 journaled, 1 updated" in proc.stderr
    assert page_heights(b) == ["45", "45"]


@pytest.mark.integration
def test_in_place_undoes_an_interrupted_patch(tmp_path, run_cli):
    import cbrXz

    src = tmp_path / "src"
    book = make_book(src / "book.cbz", tmp_path, b"<ComicInfo/>")
    original = book.read_bytes()
    st = os.stat(book)
    journal = cbrXz.Journal(str(src / "_cbrXz_journal.jsonl"), False)
    with zipfile.ZipFile(book) as zf:
        start = zf.start_dir
    journal.beginPatch(str(book), start, original[start:], st)
    journal.close()
    # the run died half way through writing the patch
    with open(book, "r+b") as f:
        f.seek(start)
        f.write(b"half a patch")
        f.truncate()

    proc = run_cli([src, "--in-place", "--dry-run"])
    assert "Would undo the interrupted patch" in proc.stderr
    assert book.read_bytes() != original

    proc = run_cli([src, "--in-place"])
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "undoing the interrupted patch" in proc.stderr
    assert page_heights(book) == ["45", "45"]
    assert not (src / "_cbrXz_journal.jsonl.tail").exists()


def test_failed_patch_is_undone(tmp_path, monkeypatch):
    import cbrXz

    book = make_book(tmp_path / "book.cbz", tmp_path, b"<ComicInfo/>")
    original = book.read_bytes()
    real = zipfile.ZipFile.writestr

    def broken(self, info, data, *a, **k):
        self.fp.write(b"some of the new entry")
        raise OSError("disk went away")
    monkeypatch.setattr(zipfile.ZipFile, "writestr", broken)
    with pytest.raises(OSError):
        cbrXz.patchInPlace(str(book), "ComicInfo.xml", b"<ComicInfo/>", None, "book.cbz")
    monkeypatch.setattr(zipfile.ZipFile, "writestr", real)
    assert book.read_bytes() == original


@pytest.mark.integration
def test_in_place_carries_on_past_a_failing_book(tmp_path, run_cli):
    src = tmp_path / "src"
    make_book(src / "a.cbz", tmp_path)
    make_book(src / "b.cbz", tmp_path)
    (src / "a.cbz").chmod(0o444)  # read-only: patching it fails
    try:
        proc = run_cli([src, "--in-place"])
    finally:
        (src / "a.cbz").chmod(0o644)
    assert proc.returncode == 1
    assert "cannot process" in proc.stderr
    assert page_heights(src / "b.cbz") == ["45", "45"]


def test_in_place_default_trash(tmp_path, run_cli):
    import cbrXz

    src = tmp_path / "src"
    make_book(src / "book.cbz", tmp_path)
    proc = run_cli([src, "--in-place", "--dry-run"])  # a dry run, so the real trash is never touched
    if os.name == "nt":
        assert proc.returncode == 0, proc.stderr or proc.stdout
        assert "trash: " + cbrXz.DEFAULT_TRASH in proc.stderr
    else:
        assert proc.returncode != 0
        assert "needs --trash" in proc.stderr + proc.stdout
