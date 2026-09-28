from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import cbrXz  # noqa: E402


def test_filterpage_skips_junk_files():
    assert cbrXz.filterPage('Thumbs.db') is True
    assert cbrXz.filterPage('.DS_Store') is True


def test_filterpage_skips_mac_resource_paths():
    assert cbrXz.filterPage('__MACOSX/foo.txt') is True
    assert cbrXz.filterPage('sub/__MACOSX/foo.txt') is True


def test_filterpage_allows_normal_files():
    assert cbrXz.filterPage('pages/001.jpg') is False
    assert cbrXz.filterPage('ComicInfo.xml') is False


def test_filterbook_skips_portuguese_tags():
    assert cbrXz.filterBook('Book [POR].cbz') is True
    assert cbrXz.filterBook('Book [por].cbz') is True
    assert cbrXz.filterBook('Book (Portuguese).cbr') is True
    assert cbrXz.filterBook('dir/Book (2020) (PORTUGUESE).zip') is True


def test_filterbook_allows_untagged_portuguese_in_title():
    assert cbrXz.filterBook('Portuguese Man.cbz') is False
