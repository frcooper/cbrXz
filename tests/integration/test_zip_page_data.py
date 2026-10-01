import xml.etree.ElementTree as ET
import zipfile

import pytest
from PIL import Image


@pytest.mark.integration
@pytest.mark.parametrize("ext", [".cbz", ".zip"])
def test_copied_zip_gains_page_data(tmp_path, run_cli, ext):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    book = src / f"book{ext}"
    with zipfile.ZipFile(book, "w") as zf:
        for i in range(2):
            img = tmp_path / f"p0{i}.png"
            Image.new("RGB", (30, 45)).save(img)
            zf.write(img, f"p0{i}.png")

    proc = run_cli([src, dst])
    assert proc.returncode == 0, proc.stderr or proc.stdout

    out = dst / "book.cbz"
    with zipfile.ZipFile(book) as zin, zipfile.ZipFile(out) as zout:
        assert zout.testzip() is None
        for name in zin.namelist():
            assert zout.read(name) == zin.read(name)
        pages = ET.fromstring(zout.read("ComicInfo.xml")).find("Pages").findall("Page")
    assert [p.get("ImageHeight") for p in pages] == ["45", "45"]
