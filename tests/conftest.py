import os
import subprocess
import sys
from pathlib import Path
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "cbrXz.py"
GIT_DIR = ROOT / ".git"


def _current_branch() -> str:
    head = (GIT_DIR / "HEAD")
    try:
        data = head.read_text(encoding="utf-8").strip()
        if data.startswith("ref:"):
            # ref: refs/heads/<branch>
            return Path(data.split(":", 1)[1].strip()).name
    except Exception:
        pass
    return "master"


@pytest.fixture
def run_cli():
    def _resolve_cmd():
        # Explicit override via environment
        env_cmd = os.environ.get("CBRXZ_CMD")
        if env_cmd:
            return env_cmd

        branch = _current_branch()
        if branch == "go-rewrite":
            # Explicitly target Go binary for go-rewrite branch
            candidates = [
                str(ROOT / ".bin" / "cbrxz.exe"),
                str(ROOT / ".bin" / "cbrxz"),
                "cbrxz",
            ]
            for c in candidates:
                try:
                    proc = subprocess.run([c, "--version"], capture_output=True, text=True)
                    if proc.returncode == 0:
                        return c
                except Exception:
                    continue
            raise RuntimeError("Expected Go binary for go-rewrite branch. Build it (go build -o .bin/cbrxz ./cmd/cbrxz) or set CBRXZ_CMD.")
        else:
            # Default: master and others use Python script
            return [sys.executable, str(SCRIPT)]

    def _run(args, cwd=None):
        cmd = _resolve_cmd()
        if isinstance(cmd, list):
            full = [*cmd, *map(str, args)]
        else:
            full = [cmd, *map(str, args)]
        env = os.environ.copy()
        return subprocess.run(full, env=env, cwd=cwd, capture_output=True, text=True)

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
