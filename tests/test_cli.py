import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "cbrXz.py"


def run(args):
    cmd = [sys.executable, str(SCRIPT), *args]
    env = os.environ.copy()
    # avoid invoking rar extraction during basic tests
    return subprocess.run(cmd, env=env, capture_output=True, text=True)


def test_cli_help_shows_when_missing_args():
    # Running without required args should exit non-zero
    proc = run([])
    assert proc.returncode != 0
    assert "usage:" in proc.stderr.lower() or "usage:" in proc.stdout.lower()


def test_cli_rejects_file_dest(tmp_path):
    src = tmp_path / "book.cbz"
    src.write_bytes(b"PK\x03\x04fake")
    dst = tmp_path / "out.txt"
    dst.write_text("x")
    proc = run([str(src), str(dst)])
    assert proc.returncode != 0
    assert "Destination must be a directory" in (proc.stderr + proc.stdout)


def test_cli_creates_destination_dir(tmp_path):
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    (src_dir / "book.cbz").write_bytes(b"PK\x03\x04fake")
    proc = run([str(src_dir), str(dst_dir), "--dry-run"])  # dry-run to avoid copying
    # Should succeed even if dry-run
    assert proc.returncode == 0
