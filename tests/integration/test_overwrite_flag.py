from pathlib import Path
from typing import Callable

import pytest


@pytest.mark.integration
def test_overwrite_flag_controls_replacement(tmp_path, run_cli, zip_with_file: Callable):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    zip_with_file(src / "a.cbz")

    # Precreate destination with different content
    dst.mkdir()
    out = dst / "a.cbz"
    out.write_bytes(b"OLD")

    # Without --replace, keep OLD
    proc = run_cli([src, dst])
    assert proc.returncode == 0
    assert out.read_bytes() == b"OLD"

    # With --replace, replaced
    proc = run_cli([src, dst, "--replace"])
    assert proc.returncode == 0
    assert out.read_bytes() != b"OLD"
