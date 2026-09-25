"""The built wheel must carry every runtime data file.

The Kazaross XG2 match equity table once lived only in PyInstaller builds
(whose spec copies the whole package): `pip install ankigammon` and the
browser version, which installs the same wheel into Pyodide, got a package
with no `data/` directory, so MET lookups failed.
"""

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def wheel_names(tmp_path_factory):
    # Built from a clean copy: setuptools reuses the repo's build/lib, where a
    # data file from an earlier build would mask a missing package-data rule.
    src = tmp_path_factory.mktemp("src")
    for name in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copy2(REPO / name, src / name)
    shutil.copytree(REPO / "ankigammon", src / "ankigammon",
                    ignore=shutil.ignore_patterns("__pycache__"))
    out = tmp_path_factory.mktemp("wheel")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", str(src), "--no-deps", "-q",
         "-w", str(out)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr.strip()[-1500:]
    wheel = next(out.glob("ankigammon-*.whl"))
    with zipfile.ZipFile(wheel) as zf:
        return set(zf.namelist())


def test_match_equity_table_is_in_the_wheel(wheel_names):
    assert "ankigammon/data/Kazaross XG2.met" in wheel_names


def test_every_data_file_is_in_the_wheel(wheel_names):
    data_dir = REPO / "ankigammon" / "data"
    expected = {f"ankigammon/data/{p.name}" for p in data_dir.iterdir() if p.is_file()}
    assert expected, "ankigammon/data should not be empty"
    assert expected <= wheel_names


def test_browser_entry_point_is_in_the_wheel(wheel_names):
    assert "ankigammon/web.py" in wheel_names
