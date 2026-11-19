import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "release_notes.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("release_notes", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHANGELOG = """# Changelog

## [Unreleased]

- next

## [0.2.0] - 2027-01-02

### Added

- B

## [0.1.0] - 2026-12-01

- A
"""


def test_section_extracts_one_version() -> None:
    notes = load()
    assert notes.section("0.2.0", CHANGELOG) == "### Added\n\n- B"
    assert notes.section("0.1.0", CHANGELOG) == "- A"


def test_missing_version_is_an_error() -> None:
    with pytest.raises(ValueError):
        load().section("9.9.9", CHANGELOG)


def test_notes_start_with_install(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    notes = load()
    monkeypatch.setattr(notes, "section", lambda version, text: f"changes of {version}")
    monkeypatch.setattr("sys.argv", ["release_notes.py", "v0.1.0"])
    notes.main()
    out = capsys.readouterr().out
    assert out.startswith("## Install")
    assert "uv tool install tame-tasks" in out
    assert out.rstrip().endswith("changes of 0.1.0")
