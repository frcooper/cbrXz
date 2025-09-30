import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import rarfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "cbrXz.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Import BOOK_TYPES from the module to avoid drift
sys.path.insert(0, str(ROOT))
import cbrXz  # noqa: E402

RAR_EXTS = [".cbr", ".rar"]
NON_RAR_EXTS = [ext for ext in cbrXz.BOOK_TYPES if ext.lower() not in RAR_EXTS]


def run(args):
    cmd = [sys.executable, str(SCRIPT), *args]
    env = os.environ.copy()
    return subprocess.run(cmd, env=env, capture_output=True, text=True)


def fixtures_with_ext(ext: str):
    return sorted(FIXTURES.glob(f"*{ext}"))


def copy_to_dir(files, dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for f in files:
        target = dest / f.name
        target.write_bytes(f.read_bytes())
        out.append(target)
    return out


def expected_non_rar_name(p: Path) -> str:
    ext = p.suffix.lower()
    stem = p.stem
    if ext == ".zip":
        return f"{stem}.cbz"
    if ext == ".7z":
        return f"{stem}.cb7"
    return p.name


@pytest.mark.parametrize("ext", NON_RAR_EXTS)
def test_fixture_non_rar_are_copied_verbatim(tmp_path: Path, ext: str):
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    files = fixtures_with_ext(ext)
    if not files:
        pytest.skip(f"No fixtures for {ext}")
    copied = copy_to_dir(files, src_dir)

    proc = run([str(src_dir), str(dst_dir)])
    assert proc.returncode == 0, proc.stderr or proc.stdout

    for f in copied:
        out_name = expected_non_rar_name(f)
        out = dst_dir / out_name
        assert out.exists(), f"Expected copy of {out_name}"
        assert out.read_bytes() == f.read_bytes(), f"Content mismatch for {out_name}"


@pytest.mark.parametrize("ext", RAR_EXTS)
def test_fixture_rar_like_results(tmp_path: Path, ext: str):
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    files = fixtures_with_ext(ext)
    if not files:
        pytest.skip(f"No fixtures for {ext}")

    # Test each file independently to avoid name collisions (.cbz output)
    for rar_path in files:
        src_dir.mkdir(exist_ok=True, parents=True)
        for p in src_dir.iterdir():
            p.unlink()
        local = src_dir / rar_path.name
        local.write_bytes(rar_path.read_bytes())

        proc = run([str(src_dir), str(dst_dir)])
        assert proc.returncode == 0, proc.stderr or proc.stdout

        out = dst_dir / (rar_path.stem + ".cbz")
        assert out.exists(), f"Expected output {out.name} for {rar_path.name}"

        is_real_rar = False
        try:
            is_real_rar = rarfile.is_rarfile(str(local))
        except Exception:
            is_real_rar = False

        if is_real_rar:
            # If it's a real RAR, output should be a valid ZIP when extractor available
            try:
                assert zipfile.is_zipfile(out), f"Output not a zip for {rar_path.name}"
            except AssertionError:
                # If extractor is not available, behavior may differ; surface details
                pytest.fail(f"Expected zip output for real RAR fixture {rar_path.name}")
        else:
            # Not a real RAR: script copies bytes into .cbz unchanged via NotRarFile path
            assert out.read_bytes() == local.read_bytes(), f"Expected raw copy for {rar_path.name}"
