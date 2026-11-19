from importlib.metadata import PackageNotFoundError

import pytest

from tame import about


def test_license_text_is_mit() -> None:
    text = about.license_text()
    assert text is not None
    assert text.startswith("MIT License")
    assert "Skitourer" in text


def test_libraries_cover_direct_and_indirect_dependencies() -> None:
    libraries = {library.name.lower(): library for library in about.libraries()}
    assert {"rich", "python-dateutil", "tomlkit"} <= set(libraries)
    assert "pygments" in libraries  # needed by rich
    assert "tame-tasks" not in libraries
    assert libraries["rich"].license == "MIT"
    assert all(library.version for library in libraries.values())


def test_without_installed_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(name: str) -> None:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(about, "distribution", missing)
    assert about.license_text() is None
    assert about.libraries() == []
