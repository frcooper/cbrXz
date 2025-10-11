from pathlib import Path
import sys
from typing import Callable


def test_zip_and_7z_renamed_on_copy(
    tmp_path, run_cli, zip_with_file: Callable
):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    # .zip -> .cbz rename
    zip_with_file(src / "sample.zip")
    # fake 7z (just bytes); should be copied and renamed to .cb7
    (src / "sample.7z").write_bytes(b"dummy")

    proc = run_cli([src, dst])
    assert proc.returncode == 0, proc.stderr or proc.stdout

    assert (dst / "sample.cbz").exists()
    assert (dst / "sample.cb7").exists()
