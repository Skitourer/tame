import subprocess
import sys

import pytest

from tame import __version__
from tame.__main__ import main


def test_version_prints_app_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["version"]) == 0
    out, err = capsys.readouterr()
    assert out == f"tame {__version__}\n"
    assert err == ""


def test_unknown_command_is_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["frobnicate"]) == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert "frobnicate" in err


def test_module_entry_point() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "tame", "version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == f"tame {__version__}"
