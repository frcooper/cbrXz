from pathlib import Path
from typing import Callable

import pytest


@pytest.mark.integration
def test_root_option_flattens_correctly(tmp_path, run_cli, zip_with_file: Callable):
    src = tmp_path / "src"
    inner = src / "a" / "b"
    dst = tmp_path / "dst"

    zip_with_file(inner / "book.cbz")

    # According to CLI rules, --root must be an ancestor of source. To flatten to 'b/',
    # use inner parent as the source and root the same as source.
    proc = run_cli([inner.parent, dst, "--root", inner.parent])
    assert proc.returncode == 0, proc.stderr or proc.stdout

    assert (dst / "b" / "book.cbz").exists()
