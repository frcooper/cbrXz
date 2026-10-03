import os
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import py7zr
import pytest
from PIL import Image


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
    assert (src / "_trash" / "a" / "broken.cbz").read_bytes() == b"not an archive at all"
    assert pdf.read_bytes() == pdf_bytes
    assert not list(src.rglob("*.part"))


@pytest.mark.integration
def test_in_place_leaves_current_books_untouched(tmp_path, run_cli):
    src = tmp_path / "src"
    book = make_book(src / "book.cbz", tmp_path)
    assert run_cli([src, "--in-place"]).returncode == 0
    before = (book.read_bytes(), os.stat(book).st_mtime_ns)

    proc = run_cli([src, "--in-place"])
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert (book.read_bytes(), os.stat(book).st_mtime_ns) == before
    assert "1 current" in proc.stderr


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
    assert (src / "_trash" / "book.cbz").read_bytes() == b"keep me"


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
    assert (trash / "broken.cbr").read_bytes() == b"junk"
    assert page_heights(stale) == ["45", "45"]


@pytest.mark.parametrize("args, message", [
    (["--in-place", "DST"], "DST cannot be given"),
    ([], "Missing argument 'DST'"),
    (["DST", "--trash", "bin"], "--trash is only used"),
])
def test_in_place_argument_errors(tmp_path, run_cli, args, message):
    src = tmp_path / "src"
    src.mkdir()
    proc = run_cli([src, *[tmp_path / a if a in ("DST", "bin") else a for a in args]])
    assert proc.returncode != 0
    assert message in proc.stderr + proc.stdout
