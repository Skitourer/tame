import uuid
from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from tame.core.dates import utc_now
from tame.core.filters import Filter
from tame.core.models import NONE, Annotation, Changes, Priority, Status, Task
from tame.core.service import TaskService
from tame.errors import NoMatchError, ValidationError
from tame.storage.repo import TaskRepo


def test_add_sets_fields(service: TaskService, repo: TaskRepo, frozen_now: datetime) -> None:
    task = service.add(" Call bank ", project="home", tags=["phone"], priority="h")

    assert task.id == 1
    assert uuid.UUID(task.uuid).version == 4
    assert task.description == "Call bank"
    assert task.status is Status.PENDING
    assert task.project == "home"
    assert task.tags == frozenset({"phone"})
    assert task.priority is Priority.H
    assert task.entry == task.modified == frozen_now
    assert task.due is None
    assert task.end is None
    assert repo.get(task.uuid) == task


def test_add_assigns_next_id(service: TaskService) -> None:
    ids = [service.add(f"task {n}").id for n in range(3)]
    assert ids == [1, 2, 3]


def test_add_minimal(service: TaskService) -> None:
    task = service.add("Buy milk")
    assert (task.project, task.tags, task.priority) == (None, frozenset(), None)


@pytest.mark.parametrize(
    ("kwargs", "key"),
    [
        ({"description": " "}, "error.empty_description"),
        ({"description": "x", "tags": ["+bad"]}, "error.invalid_tag"),
        ({"description": "x", "tags": ["OVERDUE"]}, "error.virtual_tag"),
        ({"description": "x", "project": "a..b"}, "error.invalid_project"),
        ({"description": "x", "priority": "Z"}, "error.invalid_priority"),
    ],
)
def test_add_rejects_invalid(service: TaskService, kwargs: dict[str, object], key: str) -> None:
    with pytest.raises(ValidationError) as exc:
        service.add(**kwargs)  # type: ignore[arg-type]
    assert exc.value.key == key
    assert service.query() == []


def test_query_returns_pending_by_id(service: TaskService) -> None:
    first = service.add("first")
    second = service.add("second")
    assert service.query() == [first, second]


def test_query_with_filter(service: TaskService) -> None:
    service.add("Call bank", tags=["phone"])
    report = service.add("Write report", tags=["phone"], project="work")
    assert service.query(Filter(tags_in=frozenset({"phone"}), project="work")) == [report]
    assert service.query(Filter(status=Status.COMPLETED)) == []


def test_utc_now_is_aware_and_second_precision() -> None:
    now = utc_now()
    assert now.tzinfo is not None
    assert now.microsecond == 0


@pytest.fixture
def later(frozen_now: datetime) -> datetime:
    return frozen_now + timedelta(hours=1)


@pytest.fixture
def later_service(repo: TaskRepo, later: datetime) -> TaskService:
    """A second service on the same repo whose clock is one hour later."""
    return TaskService(repo, clock=lambda: later)


def test_complete_sets_status_end_and_renumbers(
    service: TaskService, later_service: TaskService, repo: TaskRepo, later: datetime
) -> None:
    _, second, _ = (service.add(name) for name in ("one", "two", "three"))
    (done,) = later_service.complete([second])

    assert (done.status, done.id, done.end, done.modified) == (
        Status.COMPLETED,
        None,
        later,
        later,
    )
    assert repo.get(second.uuid) == done
    assert [(t.description, t.id) for t in service.query()] == [("one", 1), ("three", 2)]
    assert service.query(Filter(status=Status.COMPLETED)) == [done]


def test_delete_is_soft(
    service: TaskService, later_service: TaskService, repo: TaskRepo, later: datetime
) -> None:
    task = service.add("one")
    (deleted,) = later_service.delete([task])
    assert (deleted.status, deleted.end) == (Status.DELETED, later)
    assert repo.get(task.uuid) == deleted
    assert service.query() == []


def test_close_skips_tasks_already_in_status(service: TaskService) -> None:
    (done,) = service.complete([service.add("one")])
    assert service.complete([done]) == []
    assert len(service.delete([done])) == 1


def test_add_after_done_uses_next_id(service: TaskService) -> None:
    first, _ = service.add("one"), service.add("two")
    service.complete([first])
    assert service.add("three").id == 2


def test_modify_applies_changes(
    service: TaskService, later_service: TaskService, repo: TaskRepo, later: datetime
) -> None:
    task = service.add("Call bank", project="home", tags=["phone", "x"], priority="H")
    changes = Changes(
        description="Call the bank",
        project="work",
        priority=Priority.L,
        tags_add=frozenset({"urgent"}),
        tags_remove=frozenset({"x", "absent"}),
    )
    (changed,) = later_service.modify([task], changes)

    assert changed.description == "Call the bank"
    assert (changed.project, changed.priority) == ("work", Priority.L)
    assert changed.tags == frozenset({"phone", "urgent"})
    assert (changed.modified, changed.entry, changed.id) == (later, task.entry, 1)
    assert repo.get(task.uuid) == changed


def test_modify_clears_attributes(service: TaskService) -> None:
    task = service.add("x", project="home", priority="H")
    (changed,) = service.modify([task], Changes(project=NONE, priority=NONE))
    assert (changed.project, changed.priority) == (None, None)


def test_modify_skips_unchanged_tasks(service: TaskService) -> None:
    tagged = service.add("a", tags=["phone"])
    plain = service.add("b")
    changed = service.modify([tagged, plain], Changes(tags_add=frozenset({"phone"})))
    assert [task.uuid for task in changed] == [plain.uuid]
    assert service.query()[0] == tagged


def test_changes_truthiness() -> None:
    assert not Changes()
    assert Changes(project=NONE)
    assert Changes(tags_remove=frozenset({"x"}))


def test_add_with_due(service: TaskService, repo: TaskRepo, later: datetime) -> None:
    task = service.add("x", due=later)
    assert task.due == later
    assert repo.get(task.uuid) == task


def test_modify_sets_and_clears_due(service: TaskService, later: datetime) -> None:
    task = service.add("x")
    (with_due,) = service.modify([task], Changes(due=later))
    assert with_due.due == later
    (cleared,) = service.modify([with_due], Changes(due=NONE))
    assert cleared.due is None


def test_changes_with_due_is_truthy(later: datetime) -> None:
    assert Changes(due=later)


# --- undo ---------------------------------------------------------------------------


def test_undo_nothing(service: TaskService) -> None:
    with pytest.raises(NoMatchError) as exc:
        service.undo()
    assert exc.value.key == "error.nothing_to_undo"


def test_undo_add_removes_task(service: TaskService, repo: TaskRepo) -> None:
    kept = service.add("kept")
    added = service.add("added", tags=["x"])
    result = service.undo()
    assert (result.cmd, result.restored, result.removed) == ("add", (), (added,))
    assert repo.get(added.uuid) is None
    assert service.query() == [kept]


def test_undo_done_restores_task_and_ids(service: TaskService, repo: TaskRepo) -> None:
    one, two, three = (service.add(name) for name in ("one", "two", "three"))
    service.complete([two])
    result = service.undo()
    assert (result.cmd, result.restored, result.removed) == ("done", (two,), ())
    assert service.query() == [one, two, three]
    assert repo.get(two.uuid) == two


def test_undo_restores_original_ids_not_renumbered_ones(
    service: TaskService, repo: TaskRepo
) -> None:
    # Ids out of entry order (as after an import) must come back exactly.
    one, two = service.add("one"), service.add("two")
    with repo.transaction():
        repo.set_ids({one.uuid: 2, two.uuid: 1})
    service.delete([service.query()[0]])
    service.undo()
    assert repo.pending_ids() == {one.uuid: 2, two.uuid: 1}


def test_undo_modify_restores_fields(service: TaskService, repo: TaskRepo) -> None:
    task = service.add("Call bank", project="home", tags=["phone"], priority="H")
    service.modify([task], Changes(description="x", project=NONE, tags_remove=frozenset({"phone"})))
    result = service.undo()
    assert (result.cmd, result.restored) == ("modify", (task,))
    assert repo.get(task.uuid) == task


def test_undo_is_multi_level(service: TaskService) -> None:
    task = service.add("one")
    service.modify([task], Changes(description="two"))
    service.complete(service.query())
    assert [service.undo().cmd for _ in range(3)] == ["done", "modify", "add"]
    assert service.query() == []
    with pytest.raises(NoMatchError):
        service.undo()


def test_no_op_commands_are_not_logged(service: TaskService) -> None:
    task = service.add("one", tags=["a"])
    (done,) = service.complete([task])
    assert service.complete([done]) == []
    assert service.modify([done], Changes(tags_add=frozenset({"a"}))) == []
    assert service.undo().cmd == "done"


def test_writes_purge_undo_history_past_retention(repo: TaskRepo, frozen_now: datetime) -> None:
    old = TaskService(repo, clock=lambda: frozen_now - timedelta(days=91))
    old.add("old")
    recent = TaskService(repo, clock=lambda: frozen_now, undo_retention=timedelta(days=90))
    recent.add("recent")
    assert recent.undo().removed[0].description == "recent"
    with pytest.raises(NoMatchError):
        recent.undo()  # "old" was purged by the second add


def test_no_retention_keeps_everything(repo: TaskRepo, frozen_now: datetime) -> None:
    TaskService(repo, clock=lambda: frozen_now - timedelta(days=4000)).add("old")
    service = TaskService(repo, clock=lambda: frozen_now)
    service.add("recent")
    assert [service.undo().cmd for _ in range(2)] == ["add", "add"]


# --- import (roadmap step 8a) --------------------------------------------------------


def imported(description: str, entry: datetime, **fields: object) -> Task:
    """A task as read from Taskwarrior JSON: no short id."""
    base: dict[str, object] = {
        "uuid": str(uuid.uuid4()),
        "description": description,
        "entry": entry,
        "modified": entry,
    }
    return Task(**(base | fields))  # type: ignore[arg-type]


def test_import_adds_with_next_ids_in_entry_order(
    service: TaskService, frozen_now: datetime
) -> None:
    mine = service.add("mine")
    late = imported("late", frozen_now - timedelta(days=1))
    early = imported("early", frozen_now - timedelta(days=9))
    done = imported("done", frozen_now, status=Status.COMPLETED, end=frozen_now)
    result = service.import_tasks([late, early, done])
    assert [t.description for t in result.added] == ["late", "early", "done"]
    assert (result.updated, result.skipped) == ((), ())
    assert [(t.id, t.description) for t in service.query()] == [
        (mine.id, "mine"),
        (2, "early"),
        (3, "late"),
    ]
    assert service.query(Filter(status=Status.COMPLETED))[0].id is None


def test_import_updates_only_newer(service: TaskService, frozen_now: datetime) -> None:
    task = service.add("old text")
    newer = replace(task, id=None, description="new text", modified=frozen_now + timedelta(1))
    older = replace(task, id=None, description="stale", modified=frozen_now - timedelta(1))
    same = replace(task, id=None, description="same time")
    result = service.import_tasks([older, same])
    assert (result.added, result.updated, len(result.skipped)) == ((), (), 2)
    result = service.import_tasks([newer])
    assert [(t.id, t.description) for t in result.updated] == [(1, "new text")]
    assert service.query()[0].description == "new text"


def test_import_status_change_renumbers(service: TaskService, frozen_now: datetime) -> None:
    one, two = service.add("one"), service.add("two")
    closed = replace(
        one, id=None, status=Status.COMPLETED, end=frozen_now, modified=frozen_now + timedelta(1)
    )
    service.import_tasks([closed])
    assert [(t.id, t.description) for t in service.query()] == [(1, "two")]
    assert two.id == 2


def test_import_nothing_new_logs_nothing(service: TaskService) -> None:
    task = service.add("x")
    service.import_tasks([replace(task, id=None)])
    assert service.undo().cmd == "add"


def test_undo_import(service: TaskService, repo: TaskRepo, frozen_now: datetime) -> None:
    one = service.add("one")
    service.complete([one])
    reopened = replace(
        repo.get(one.uuid),  # type: ignore[type-var]
        id=None,
        status=Status.PENDING,
        end=None,
        modified=frozen_now + timedelta(1),
    )
    new = imported("new", frozen_now)
    service.import_tasks([reopened, new])
    assert len(service.query()) == 2
    result = service.undo()
    assert result.cmd == "import"
    assert [t.description for t in result.removed] == ["new"]
    assert service.query() == []
    assert repo.get(one.uuid).status is Status.COMPLETED  # type: ignore[union-attr]


def test_modify_rejects_virtual_tag(service: TaskService) -> None:
    task = service.add("x")
    with pytest.raises(ValidationError) as exc:
        service.modify([task], Changes(tags_add=frozenset({"TAGGED"})))
    assert exc.value.key == "error.virtual_tag"


def test_query_with_virtual_tags(service: TaskService, frozen_now: datetime) -> None:
    late = service.add("late", due=frozen_now - timedelta(days=1))
    free = service.add("free")
    blocked = replace(free, uuid=str(uuid.uuid4()), id=None, depends=frozenset({free.uuid}))
    service.import_tasks([blocked])
    assert service.query(Filter(virtual_in=frozenset({"OVERDUE"}))) == [late]
    assert [t.description for t in service.query(Filter(virtual_in=frozenset({"BLOCKED"})))] == [
        "free"
    ]
    assert service.query(Filter(virtual_out=frozenset({"OVERDUE", "BLOCKED"}))) == [free]


# --- annotate / denotate ------------------------------------------------------------


def notes(task: Task) -> list[str]:
    return [note.description for note in task.annotations]


def test_annotate_adds_note_and_is_undoable(service: TaskService, frozen_now: datetime) -> None:
    task = service.add("x")
    (changed,) = service.annotate([task], "  first  ")
    assert changed.annotations == (Annotation(frozen_now, "first"),)
    assert changed.modified == frozen_now
    assert service.query() == [changed]
    assert service.undo().cmd == "annotate"
    assert service.query()[0].annotations == ()


def test_annotate_rejects_blank(service: TaskService) -> None:
    with pytest.raises(ValidationError) as exc:
        service.annotate([service.add("x")], " ")
    assert exc.value.key == "error.empty_annotation"


def annotated(service: TaskService, *texts: str) -> Task:
    task = service.add("x")
    for text in texts:
        (task,) = service.annotate([task], text)
    return task


@pytest.mark.parametrize(
    ("text", "left"),
    [
        ("call back", ["Call bank", "mail sent"]),  # exact, any case, wins over partial
        ("mail", ["Call back", "Call bank"]),  # the only one containing it
        ("", ["Call back", "Call bank"]),  # the most recent
    ],
)
def test_denotate_picks_one_note(service: TaskService, text: str, left: list[str]) -> None:
    task = annotated(service, "Call back", "Call bank", "mail sent")
    (changed,) = service.denotate([task], text)
    assert notes(changed) == left


def test_denotate_ambiguous_changes_nothing(service: TaskService) -> None:
    task = annotated(service, "Call back", "Call bank")
    with pytest.raises(ValidationError) as exc:
        service.denotate([task], "call")
    assert exc.value.key == "error.ambiguous_annotation"
    assert exc.value.params["candidates"] == "'Call back', 'Call bank'"
    assert notes(service.query()[0]) == ["Call back", "Call bank"]


def test_denotate_skips_tasks_without_match(service: TaskService) -> None:
    plain = service.add("plain")
    task = annotated(service, "note")
    assert service.denotate([plain, task], "other") == []
    assert service.denotate([plain], "") == []
    assert [t.description for t in service.denotate([plain, task], "note")] == ["x"]


# --- wait ---------------------------------------------------------------------------


def test_waiting_tasks_are_hidden_until_their_date(
    repo: TaskRepo, service: TaskService, frozen_now: datetime
) -> None:
    waiting = service.add("later", wait=frozen_now + timedelta(days=2))
    free = service.add("now")
    assert service.query() == [free]
    assert service.query_hidden() == ([free], 1)
    assert service.query(include_waiting=True) == [waiting, free]
    assert service.query(Filter(ids=frozenset({1}))) == [waiting]
    assert service.query(Filter(virtual_in=frozenset({"WAITING"}))) == [waiting]
    in_three_days = TaskService(repo, clock=lambda: frozen_now + timedelta(days=3))
    assert in_three_days.query() == [waiting, free]


def test_modify_sets_and_clears_wait(service: TaskService, frozen_now: datetime) -> None:
    task = service.add("x")
    (task,) = service.modify([task], Changes(wait=frozen_now + timedelta(days=1)))
    assert task.wait == frozen_now + timedelta(days=1)
    (task,) = service.modify([task], Changes(wait=NONE))
    assert task.wait is None


# --- purge (0.4) ----------------------------------------------------------------------------


def _deleted(service: TaskService, description: str) -> Task:
    task = service.add(description)
    return service.delete([task])[0]


def test_purge_removes_deleted_tasks_with_links_and_backs_up_first(
    service: TaskService, repo: TaskRepo
) -> None:
    gone = _deleted(service, "old")
    service.annotate([gone], "note")
    kept = service.add("kept")
    repo.update(replace(kept, depends=frozenset({gone.uuid})))
    service.purge([gone, kept])  # kept is pending: skipped
    assert repo.get(gone.uuid) is None
    assert repo.get(kept.uuid) is not None
    assert repo.get(kept.uuid).depends == frozenset()  # type: ignore[union-attr]


def test_purge_backup_holds_the_tasks_before(service: TaskService, repo: TaskRepo) -> None:
    gone = _deleted(service, "old")
    result = service.purge([gone])
    assert result.purged == (gone,)
    assert result.backup.parent == repo.path.parent
    assert result.backup.name.startswith("tame-")
    assert result.backup.name.endswith(".db.bak")
    with TaskRepo(result.backup) as copy:
        assert copy.get(gone.uuid) == gone


def test_purge_backup_name_is_local_time_and_unique(
    service: TaskService, frozen_now: datetime
) -> None:
    stamp = f"tame-{frozen_now.astimezone():%Y%m%d-%H%M%S}"
    first = service.purge([_deleted(service, "a")]).backup
    second = service.purge([_deleted(service, "b")]).backup
    assert first.name == f"{stamp}.db.bak"
    assert second.name == f"{stamp}-2.db.bak"


def test_purge_clears_undo(service: TaskService) -> None:
    service.purge([_deleted(service, "old")])
    with pytest.raises(NoMatchError):
        service.undo()


def test_purge_nothing_deleted_writes_nothing(service: TaskService, repo: TaskRepo) -> None:
    task = service.add("pending")
    with pytest.raises(NoMatchError):
        service.purge([task])
    assert list(repo.path.parent.glob("*.bak")) == []
    assert service.undo().cmd == "add"


def test_purge_all_keeps_meta(service: TaskService, repo: TaskRepo) -> None:
    service.add("a")
    service.complete([service.add("b")])
    _deleted(service, "c")
    service.set_state("kindness_last", "x")
    result = service.purge_all()
    assert len(result.purged) == 3
    assert service.query(Filter(status="all")) == []
    assert service.state("kindness_last") == "x"
    with pytest.raises(NoMatchError):
        service.undo()


def test_purge_all_empty_database(service: TaskService) -> None:
    with pytest.raises(NoMatchError):
        service.purge_all()
