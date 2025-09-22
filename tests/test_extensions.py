import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "cbrXz.py"

# Import BOOK_TYPES from the module to avoid test drift
sys.path.insert(0, str(ROOT))
import cbrXz  # noqa: E402

RAR_EXTS = [".cbr", ".rar"]
NON_RAR_EXTS = [ext for ext in cbrXz.BOOK_TYPES if ext.lower() not in RAR_EXTS]


def run(args):
    cmd = [sys.executable, str(SCRIPT), *args]
    env = os.environ.copy()
    return subprocess.run(cmd, env=env, capture_output=True, text=True)


def test_non_rar_extensions_are_copied(tmp_path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    for ext in NON_RAR_EXTS:
        (src / f"sample{ext}").write_bytes(b"test-bytes")
    proc = run([str(src), str(dst)])
    assert proc.returncode == 0, proc.stderr or proc.stdout
    for ext in NON_RAR_EXTS:
        assert (dst / f"sample{ext}").exists(), f"Expected copy of sample{ext}"


def test_uppercase_extensions_are_handled(tmp_path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    # create both rar and non-rar uppercase variants
    for ext in NON_RAR_EXTS + RAR_EXTS:
        (src / f"UpCase{ext.upper()}").write_bytes(b"content")
    proc = run([str(src), str(dst), "--dry-run"])  # dry-run to avoid extraction/copy cost
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_rar_like_files_convert_to_cbz_when_not_rar(tmp_path):
    # Create fake .cbr/.rar (not real RAR) so rarfile raises NotRarFile and code treats as zip
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    # Use single base to match code behavior (second input may be skipped if output exists)
    for ext in RAR_EXTS:
        (src / f"book{ext}").write_bytes(b"not-a-rar")
    proc = run([str(src), str(dst)])
    assert proc.returncode == 0, proc.stderr or proc.stdout
    # Expect .cbz output for the base name
    assert (dst / "book.cbz").exists(), "Expected book.cbz to be written"


def test_rar_only_skips_non_rar(tmp_path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    (src / "x.cbz").write_bytes(b"data")
    proc = run([str(src), str(dst), "--rar-only"])  # only rar/cbr should be processed
    assert proc.returncode == 0, proc.stderr or proc.stdout
    # Non-rar should not be copied when --rar-only is set
    assert not (dst / "x.cbz").exists()
