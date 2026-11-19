from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tame.core.service import TaskService
from tame.i18n import set_language
from tame.storage.repo import DB_FILENAME, TaskRepo

FROZEN_NOW = datetime(2026, 11, 19, 9, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
def tame_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point TAME_HOME to a fresh temp dir for every test."""
    home = tmp_path / "tame_home"
    monkeypatch.setenv("TAME_HOME", str(home))
    return home


@pytest.fixture
def repo(tame_home: Path) -> Iterator[TaskRepo]:
    with TaskRepo(tame_home / DB_FILENAME) as repo:
        yield repo


@pytest.fixture
def frozen_now() -> datetime:
    return FROZEN_NOW


@pytest.fixture
def service(repo: TaskRepo, frozen_now: datetime) -> TaskService:
    return TaskService(repo, clock=lambda: frozen_now)


@pytest.fixture(autouse=True)
def english_ui() -> Iterator[None]:
    """Reset the UI language: it is process-wide state set by main()."""
    set_language("en")
    yield
    set_language("en")
