import xml.etree.ElementTree as ET
import zipfile

import py7zr
import pytest
from PIL import Image


def make_pages(tmp_path, names):
    pages = tmp_path / "pages"
    pages.mkdir(exist_ok=True)
    for n in names:
        Image.new("RGB", (30, 45)).save(pages / n)
    return pages


def make_7z(path, pages, password=None):
    with py7zr.SevenZipFile(path, "w", password=password) as sz:
        for p in sorted(pages.iterdir()):
            sz.write(p, p.name)
    return path


@pytest.mark.integration
@pytest.mark.parametrize("ext", [".cb7", ".7z"])
def test_7z_repacked_to_cbz_with_page_data(tmp_path, run_cli, ext):
    pages = make_pages(tmp_path, ["p00.png", "p01.png"])
    (tmp_path / "src").mkdir()
    make_7z(tmp_path / "src" / f"book{ext}", pages)

    proc = run_cli([tmp_path / "src", tmp_path / "dst"])
    assert proc.returncode == 0, proc.stderr or proc.stdout

    assert not (tmp_path / "dst" / "book.cb7").exists()
    with zipfile.ZipFile(tmp_path / "dst" / "book.cbz") as zf:
        assert zf.testzip() is None
        assert zf.read("p00.png") == (pages / "p00.png").read_bytes()
        assert all(i.compress_type == zipfile.ZIP_STORED for i in zf.infolist())
        els = ET.fromstring(zf.read("ComicInfo.xml")).find("Pages").findall("Page")
    assert [e.get("ImageHeight") for e in els] == ["45", "45"]


@pytest.mark.integration
def test_encrypted_7z_kept_as_cb7(tmp_path, run_cli):
    pages = make_pages(tmp_path, ["p00.png"])
    (tmp_path / "src").mkdir()
    book = make_7z(tmp_path / "src" / "book.7z", pages, password="secret")

    proc = run_cli([tmp_path / "src", tmp_path / "dst"])
    assert proc.returncode == 0, proc.stderr or proc.stdout

    assert (tmp_path / "dst" / "book.cb7").read_bytes() == book.read_bytes()
    assert not (tmp_path / "dst" / "book.cbz").exists()


@pytest.mark.integration
def test_zip_named_cb7_becomes_cbz(tmp_path, run_cli):
    (tmp_path / "src").mkdir()
    book = tmp_path / "src" / "book.cb7"
    with zipfile.ZipFile(book, "w") as zf:
        zf.writestr("a.txt", b"hello")

    proc = run_cli([tmp_path / "src", tmp_path / "dst"])
    assert proc.returncode == 0, proc.stderr or proc.stdout

    assert (tmp_path / "dst" / "book.cbz").read_bytes() == book.read_bytes()
    assert not (tmp_path / "dst" / "book.cb7").exists()
