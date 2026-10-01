from pathlib import Path
import hashlib
import sys
import xml.etree.ElementTree as ET

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import cbrXz  # noqa: E402


def make_png(path: Path, size=(40, 60), mode='RGB', dpi=(300, 300)) -> Path:
    Image.new(mode, size).save(path, format='PNG', dpi=dpi)
    return path


def make_jpeg(path: Path, size=(80, 50), mode='L') -> Path:
    Image.new(mode, size).save(path, format='JPEG')
    return path


def pages_of(xml: bytes):
    root = ET.fromstring(xml)
    return root, root.find('Pages').findall('Page')


def test_pageinfo_reports_image_data(tmp_path):
    p = make_png(tmp_path / 'p01.png')
    info = cbrXz.pageInfo(str(p))
    assert info['ImageSize'] == str(p.stat().st_size)
    assert info['ImageWidth'] == '40'
    assert info['ImageHeight'] == '60'
    assert info['ImageFormat'] == 'PNG'
    assert info['ImageBitDepth'] == '24'
    assert info['ImageDpi'] == '300'
    assert info['ImageHash'] == hashlib.sha256(p.read_bytes()).hexdigest()
    assert 'DoublePage' not in info


def test_pageinfo_flags_landscape_as_double_page(tmp_path):
    p = make_jpeg(tmp_path / 'spread.jpg')
    info = cbrXz.pageInfo(str(p))
    assert info['DoublePage'] == 'true'
    assert info['ImageFormat'] == 'JPEG'
    assert info['ImageBitDepth'] == '8'


def test_pageinfo_survives_unreadable_image(tmp_path):
    p = tmp_path / 'broken.jpg'
    p.write_bytes(b'not an image')
    info = cbrXz.pageInfo(str(p))
    assert info['ImageSize'] == '12'
    assert info['ImageHash'] == hashlib.sha256(b'not an image').hexdigest()
    assert 'ImageWidth' not in info


def test_creates_comicinfo_when_missing(tmp_path):
    pages = [str(make_png(tmp_path / f'p0{i}.png')) for i in range(3)]
    xml = cbrXz.updateComicInfo(None, pages)
    root, els = pages_of(xml)
    assert root.tag == 'ComicInfo'
    assert root.findtext('PageCount') == '3'
    assert [el.get('Image') for el in els] == ['0', '1', '2']
    assert all(el.get('ImageHash') for el in els)


def test_fills_missing_attributes_without_overwriting(tmp_path):
    pages = [str(make_png(tmp_path / f'p0{i}.png')) for i in range(2)]
    existing = b"""<?xml version="1.0"?>
<ComicInfo xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Title>T</Title>
  <PageCount>2</PageCount>
  <Pages>
    <Page Image="0" ImageSize="999" Type="FrontCover" />
  </Pages>
</ComicInfo>"""
    xml = cbrXz.updateComicInfo(existing, pages)
    root, els = pages_of(xml)
    assert root.findtext('Title') == 'T'
    assert root.findtext('PageCount') == '2'
    assert els[0].get('ImageSize') == '999'
    assert els[0].get('Type') == 'FrontCover'
    assert els[0].get('ImageWidth') == '40'
    assert els[1].get('Image') == '1'
    assert els[1].get('ImageFormat') == 'PNG'


def test_adds_pages_before_trailing_elements(tmp_path):
    pages = [str(make_png(tmp_path / 'p00.png'))]
    existing = b"<ComicInfo><Series>S</Series><CommunityRating>4</CommunityRating></ComicInfo>"
    root, _ = pages_of(cbrXz.updateComicInfo(existing, pages))
    assert [el.tag for el in root] == ['Series', 'PageCount', 'Pages', 'CommunityRating']


def test_returns_none_when_complete(tmp_path):
    pages = [str(make_png(tmp_path / 'p00.png'))]
    xml = cbrXz.updateComicInfo(None, pages)
    assert cbrXz.updateComicInfo(xml, pages) is None


def test_findcomicinfo_prefers_shallowest(tmp_path):
    a = str(tmp_path / 'sub' / 'ComicInfo.xml')
    b = str(tmp_path / 'comicinfo.XML')
    assert cbrXz.findComicInfo([a, b], str(tmp_path)) == b
    assert cbrXz.findComicInfo([str(tmp_path / 'p.png')], str(tmp_path)) is None
