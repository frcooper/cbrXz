from pathlib import Path
import sys

import pytest

# Skip these tests if the Python module isn't available (e.g., go-rewrite branch)
pytest.importorskip("cbrXz")

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
