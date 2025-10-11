import os
import subprocess
import sys
from pathlib import Path
import shutil
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "cbrXz.py"


@pytest.fixture
def run_cli():
    def _run(args, cwd=None):
        cmd = [sys.executable, str(SCRIPT), *map(str, args)]
        env = os.environ.copy()
        return subprocess.run(cmd, env=env, cwd=cwd, capture_output=True, text=True)
    return _run


@pytest.fixture
def tmp_tree(tmp_path):
    """Factory to quickly create directory trees.
    Usage: files = tmp_tree({"a/b.txt": b"data", "c/d/e.cbz": b"bytes"})
    Returns dict of relative path -> absolute Path created.
    """
    def _mk(mapping):
        created = {}
        for rel, content in mapping.items():
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                p.write_bytes(content)
            else:
                p.write_text(str(content))
            created[rel] = p
        return created
    return _mk


@pytest.fixture
def zip_with_file():
    def _zip(path: Path, arcname: str = "a.txt", data: bytes = b"hello") -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr(arcname, data)
        return path
    return _zip
