import os
from pathlib import Path
from typing import Callable

import pytest


@pytest.mark.integration
def test_copy_tree_mirrors_structure_and_renames(tmp_path, run_cli, zip_with_file: Callable):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    # Build source tree
    zip_with_file(src / "Series" / "Issue01.cbz")
    zip_with_file(src / "Series" / "sub" / "packed.zip")
    (src / "Series" / "sub" / "doc.pdf").write_bytes(b"pdf")
    (src / "ignore.txt").write_text("x")

    proc = run_cli([src, dst])
    assert proc.returncode == 0, proc.stderr or proc.stdout

    # Expected files
    assert (dst / "Series" / "Issue01.cbz").exists()
    assert (dst / "Series" / "sub" / "packed.cbz").exists()  # renamed
    assert (dst / "Series" / "sub" / "doc.pdf").exists()
    # Unsupported not copied
    assert not (dst / "ignore.txt").exists()
