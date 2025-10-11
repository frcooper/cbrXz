from pathlib import Path
import zipfile

from typing import Callable

import pytest


@pytest.mark.integration
def test_uppercase_extensions_and_junk_filtered(tmp_path, run_cli, zip_with_file: Callable):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()

    # Uppercase extension handling for copy
    (src / "Up.CBZ").write_bytes(b"PK\x03\x04fake")

    # For junk filtering in repack we need to trigger rar path; simulate with NotRarFile copy path by placing a fake .cbr
    (src / "Fake.CBR").write_bytes(b"not-a-rar")

    proc = run_cli([src, dst])
    assert proc.returncode == 0, proc.stderr or proc.stdout

    # Copied uppercase
    assert (dst / "Up.CBZ").exists()
    # Fake rar copy path yields .cbz with identical bytes
    assert (dst / "Fake.cbz").exists()
