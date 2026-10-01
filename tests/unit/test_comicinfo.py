from pathlib import Path
import sys
import zipfile
import xml.etree.ElementTree as ET

import pytest
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


def entries_for(tmp_path, names):
    """Create a PNG per name and return [(arcname, path)]."""
    out = []
    for n in names:
        p = tmp_path / n
        p.parent.mkdir(parents=True, exist_ok=True)
        make_png(p)
        out.append(cbrXz.fileEntry(n, str(p)))
    return out


def pages_of(xml: bytes):
    root = ET.fromstring(xml)
    return root, root.find('Pages').findall('Page')


def test_pageinfo_reports_image_data(tmp_path):
    p = make_png(tmp_path / 'p01.png')
    info = cbrXz.pageInfo(cbrXz.fileEntry('p01.png', str(p)))
    assert info['ImageSize'] == str(p.stat().st_size)
    assert info['ImageWidth'] == '40'
    assert info['ImageHeight'] == '60'
    assert info['ImageFormat'] == 'PNG'
    assert info['ImageBitDepth'] == '24'
    assert info['ImageDpi'] == '300'
    assert 'DoublePage' not in info


def test_pageinfo_flags_landscape_as_double_page(tmp_path):
    p = make_jpeg(tmp_path / 'spread.jpg')
    info = cbrXz.pageInfo(cbrXz.fileEntry('spread.jpg', str(p)))
    assert info['DoublePage'] == 'true'
    assert info['ImageFormat'] == 'JPEG'
    assert info['ImageBitDepth'] == '8'


def test_unreadable_image_blocks_page_data(tmp_path):
    p = tmp_path / 'broken.jpg'
    p.write_bytes(b'not an image')
    with pytest.raises(cbrXz.PageDataError):
        cbrXz.updateComicInfo(None, [cbrXz.fileEntry('broken.jpg', str(p))])


def test_creates_comicinfo_when_missing(tmp_path):
    entries = entries_for(tmp_path, ['p02.png', 'p00.png', 'p01.png'])
    xml = cbrXz.updateComicInfo(None, entries)
    root, els = pages_of(xml)
    assert root.tag == 'ComicInfo'
    assert root.findtext('PageCount') == '3'
    assert [el.get('Image') for el in els] == ['0', '1', '2']
    sizes = [str((tmp_path / f'p0{i}.png').stat().st_size) for i in range(3)]
    assert [el.get('ImageSize') for el in els] == sizes
    assert all(el.get('ImageHash') is None for el in els)


def test_ignores_non_image_files(tmp_path):
    entries = entries_for(tmp_path, ['p00.png'])
    (tmp_path / 'ComicInfo.xml').write_text('<ComicInfo/>')
    entries.append(cbrXz.fileEntry('ComicInfo.xml', str(tmp_path / 'ComicInfo.xml')))
    root, els = pages_of(cbrXz.updateComicInfo(None, entries))
    assert root.findtext('PageCount') == '1'


def test_fills_missing_attributes_without_overwriting(tmp_path):
    entries = entries_for(tmp_path, ['p00.png', 'p01.png'])
    size = (tmp_path / 'p00.png').stat().st_size
    existing = f"""<?xml version="1.0"?>
<ComicInfo xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Title>T</Title>
  <Pages>
    <Page Image="0" ImageSize="{size}" Type="FrontCover" />
  </Pages>
</ComicInfo>""".encode()
    xml = cbrXz.updateComicInfo(existing, entries)
    root, els = pages_of(xml)
    assert root.findtext('Title') == 'T'
    assert root.findtext('PageCount') == '2'
    assert els[0].get('Type') == 'FrontCover'
    assert els[0].get('ImageWidth') == '40'
    assert els[1].get('Image') == '1'
    assert els[1].get('ImageFormat') == 'PNG'


def test_adds_pages_before_trailing_elements(tmp_path):
    entries = entries_for(tmp_path, ['p00.png'])
    existing = b"<ComicInfo><Series>S</Series><CommunityRating>4</CommunityRating></ComicInfo>"
    root, _ = pages_of(cbrXz.updateComicInfo(existing, entries))
    assert [el.tag for el in root] == ['Series', 'PageCount', 'Pages', 'CommunityRating']


def test_adds_pagecount_in_schema_order(tmp_path):
    entries = entries_for(tmp_path, ['p00.png'])
    existing = b"<ComicInfo><Web>w</Web><Format>f</Format><AgeRating>a</AgeRating></ComicInfo>"
    root, _ = pages_of(cbrXz.updateComicInfo(existing, entries))
    assert [el.tag for el in root] == ['Web', 'PageCount', 'Format', 'AgeRating', 'Pages']


def test_returns_none_when_complete(tmp_path):
    entries = entries_for(tmp_path, ['p00.png'])
    xml = cbrXz.updateComicInfo(None, entries)
    assert cbrXz.updateComicInfo(xml, entries) is None


@pytest.mark.parametrize('names', [
    ['p1.png', 'p2.png', 'p10.png'],        # unpadded: plain order puts p10 before p2
    ['B.png', 'a.png'],                     # case: plain order puts B before a
    ['p1.png', 'p01.png'],                  # same page number twice
])
def test_ambiguous_page_order_blocks_page_data(tmp_path, names):
    with pytest.raises(cbrXz.PageDataError):
        cbrXz.updateComicInfo(None, entries_for(tmp_path, names))


def test_padded_names_are_unambiguous(tmp_path):
    entries = entries_for(tmp_path, ['ch1/p01.png', 'ch1/p02.png', 'ch2/p01.png'])
    _, els = pages_of(cbrXz.updateComicInfo(None, entries))
    assert len(els) == 3


def test_uncertain_image_type_blocks_page_data(tmp_path):
    entries = entries_for(tmp_path, ['p00.png'])
    (tmp_path / 'p01.avif').write_bytes(b'x')
    entries.append(cbrXz.fileEntry('p01.avif', str(tmp_path / 'p01.avif')))
    with pytest.raises(cbrXz.PageDataError):
        cbrXz.updateComicInfo(None, entries)


@pytest.mark.parametrize('body', [
    '<PageCount>5</PageCount>',                                          # wrong count
    '<PageCount>2</PageCount><Pages><Page Image="0" ImageSize="1" /></Pages>',   # wrong size
    '<Pages><Page Image="0" Type="FrontCover" /></Pages>',              # nothing to corroborate
    '<PageCount>2</PageCount><Pages><Page Image="2" /></Pages>',        # out of range
    '<PageCount>2</PageCount><Pages><Page Image="0" /><Page Image="0" /></Pages>',  # duplicate
    '<PageCount>2</PageCount><Pages><Page Image="0" ImageFormat="JPEG" /></Pages>',  # wrong format
])
def test_contradicting_comicinfo_blocks_page_data(tmp_path, body):
    entries = entries_for(tmp_path, ['p00.png', 'p01.png'])
    with pytest.raises(cbrXz.PageDataError):
        cbrXz.updateComicInfo(f'<ComicInfo>{body}</ComicInfo>'.encode(), entries)


def test_matching_pagecount_corroborates_bare_entries(tmp_path):
    entries = entries_for(tmp_path, ['p00.png', 'p01.png'])
    existing = b'<ComicInfo><PageCount>2</PageCount><Pages><Page Image="0" Type="FrontCover" /></Pages></ComicInfo>'
    _, els = pages_of(cbrXz.updateComicInfo(existing, entries))
    assert els[0].get('Type') == 'FrontCover'
    assert els[0].get('ImageWidth') == '40'


def test_findcomicinfo_prefers_shallowest(tmp_path):
    a = str(tmp_path / 'sub' / 'ComicInfo.xml')
    b = str(tmp_path / 'comicinfo.XML')
    assert cbrXz.findComicInfo([a, b], str(tmp_path)) == b
    assert cbrXz.findComicInfo([str(tmp_path / 'p.png')], str(tmp_path)) is None


def test_copy_appends_comicinfo_to_zip_without_one(tmp_path):
    entries_for(tmp_path, ['p00.png', 'p01.png'])
    z = tmp_path / 'book.cbz'
    with zipfile.ZipFile(z, 'w') as zf:
        zf.write(tmp_path / 'p00.png', 'p00.png')
        zf.write(tmp_path / 'p01.png', 'p01.png')
        zf.writestr('Thumbs.db', b'junk')
    before = {i.filename: (i.CRC, i.header_offset) for i in zipfile.ZipFile(z).infolist()}
    out = tmp_path / 'out.cbz'
    cbrXz.copyZipBook(str(z), str(out), 'book.cbz')
    with zipfile.ZipFile(out) as zf:
        assert zf.testzip() is None
        after = {i.filename: (i.CRC, i.header_offset) for i in zf.infolist()}
        root, els = pages_of(zf.read('ComicInfo.xml'))
    # Existing entries were left where they were - only ComicInfo.xml was added
    assert {k: v for k, v in after.items() if k != 'ComicInfo.xml'} == before
    assert root.findtext('PageCount') == '2'
    assert [el.get('ImageWidth') for el in els] == ['40', '40']
    assert out.stat().st_mtime == z.stat().st_mtime


@pytest.mark.parametrize('compression', [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED])
def test_copy_rewrites_zip_with_incomplete_comicinfo(tmp_path, compression):
    z = tmp_path / 'book.cbz'
    with zipfile.ZipFile(z, 'w', compression=compression) as zf:
        zf.write(make_png(tmp_path / 'p00.png'), 'p00.png')
        zf.write(make_png(tmp_path / 'p01.png'), 'p01.png')
        zf.writestr('sub/ComicInfo.xml', '<ComicInfo><Title>T</Title></ComicInfo>')
        zf.comment = b'kept'
    out = tmp_path / 'out.cbz'
    cbrXz.copyZipBook(str(z), str(out), 'book.cbz')
    with zipfile.ZipFile(z) as zin, zipfile.ZipFile(out) as zout:
        assert zout.testzip() is None
        assert zout.comment == b'kept'
        assert zout.namelist() == zin.namelist()
        for a, b in zip(zin.infolist(), zout.infolist()):
            assert a.date_time == b.date_time
            assert b.compress_type == zipfile.ZIP_STORED
            if a.filename != 'sub/ComicInfo.xml':
                assert zout.read(b) == zin.read(a)
        root, els = pages_of(zout.read('sub/ComicInfo.xml'))
    assert root.findtext('Title') == 'T'
    assert root.findtext('PageCount') == '2'
    assert len(els) == 2
    assert out.stat().st_mtime == z.stat().st_mtime


def test_copy_leaves_zip_with_complete_comicinfo_alone(tmp_path):
    pages = entries_for(tmp_path, ['p00.png'])
    z = tmp_path / 'book.cbz'
    with zipfile.ZipFile(z, 'w') as zf:
        zf.write(tmp_path / 'p00.png', 'p00.png')
        zf.writestr('ComicInfo.xml', cbrXz.updateComicInfo(None, pages))
    out = tmp_path / 'out.cbz'
    cbrXz.copyZipBook(str(z), str(out), 'book.cbz')
    assert out.read_bytes() == z.read_bytes()


@pytest.mark.parametrize('names, comicinfo', [
    (['p1.png', 'p2.png', 'p10.png'], None),               # ambiguous order
    (['p00.png', 'p01.png'], '<ComicInfo><PageCount>9</PageCount></ComicInfo>'),  # contradicts
    (['p00.png'], '<ComicInfo>'),                            # unparseable
])
def test_copy_leaves_unverifiable_zip_alone(tmp_path, names, comicinfo):
    z = tmp_path / 'book.cbz'
    with zipfile.ZipFile(z, 'w') as zf:
        for n in names:
            zf.write(make_png(tmp_path / n), n)
        if comicinfo:
            zf.writestr('ComicInfo.xml', comicinfo)
    out = tmp_path / 'out.cbz'
    cbrXz.copyZipBook(str(z), str(out), 'book.cbz')
    assert out.read_bytes() == z.read_bytes()


def test_copy_falls_back_when_not_a_zip(tmp_path):
    z = tmp_path / 'book.cbz'
    z.write_bytes(b'not a zip')
    out = tmp_path / 'out.cbz'
    cbrXz.copyZipBook(str(z), str(out), 'book.cbz')
    assert out.read_bytes() == b'not a zip'
    assert not (tmp_path / 'out.cbz.part').exists()
