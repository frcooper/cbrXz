from pathlib import Path
import sys
from typing import Callable

import pytest


def test_cli_help_shows_when_missing_args(run_cli):
    proc = run_cli([])
    assert proc.returncode != 0
    assert "Usage:" in (proc.stderr or proc.stdout)


def test_cli_rejects_file_dest(tmp_path: Path, run_cli, zip_with_file: Callable):
    src = zip_with_file(tmp_path / "book.cbz")
    dst = tmp_path / "out.txt"
    dst.write_text("x")
    proc = run_cli([src, dst])
    assert proc.returncode != 0
    assert "Destination must be a directory" in (proc.stderr + proc.stdout)


def test_version_flag(run_cli):
    proc = run_cli(["--version"])
    assert proc.returncode == 0
    assert proc.stdout.strip().startswith("cbrXz, version v") or proc.stdout.strip().startswith("v")
