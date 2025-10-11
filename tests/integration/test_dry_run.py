from pathlib import Path
from typing import Callable

import pytest


@pytest.mark.integration
def test_dry_run_creates_no_outputs(tmp_path, run_cli, zip_with_file: Callable):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    zip_with_file(src / "sample.cbz")

    proc = run_cli([src, dst, "--dry-run"])
    assert proc.returncode == 0, proc.stderr or proc.stdout

    # Destination directory may be created; assert no files
    if dst.exists():
        assert list(dst.rglob("*")) == []
