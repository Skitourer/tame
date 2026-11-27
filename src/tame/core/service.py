"""Task use cases. Returns objects and raises ``TameError``; never prints."""

import uuid as uuid_lib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path

from tame.core.dates import utc_now
from tame.core.filters import ALL, Condition, Filter, VirtualTagger, is_waiting
from tame.core.models import (
    NO_REFS,
    Annotation,
    Changes,
    DependsChange,
    Links,
    Session,
    Status,
    Task,
    TaskRefs,
    check_description,
    check_new_tag,
    check_project,
    parse_priority,
)
from tame.core.recurrence import ANCHOR, anchored, check_recur, next_due
from tame.errors import NoMatchError, ValidationError
from tame.storage.repo import TaskRepo

Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class UndoResult:
    """What :meth:`TaskService.undo` reverted.

    Attributes:
        cmd: Name of the undone command.
        restored: Tasks put back in their previous state, as now stored.
        removed: Tasks the undone command had created, as they were before removal.
    """

    cmd: str
    restored: tuple[Task, ...]
    removed: tuple[Task, ...]


@dataclass(frozen=True, slots=True)
class ImportResult:
    """What :meth:`TaskService.import_tasks` did.

    Attributes:
        added: Tasks with a new uuid, as stored.
        updated: Existing tasks replaced by a more recently modified version, as stored.
        skipped: Incoming tasks not newer than the stored version.
    """

    added: tuple[Task, ...]
    updated: tuple[Task, ...]
    skipped: tuple[Task, ...]


@dataclass(frozen=True, slots=True)
class DoneResult:
    """What :meth:`TaskService.done` did.

    Attributes:
        done: The completed tasks, as stored.
        next: For each recurring task completed, its next occurrence, as stored.
        last: Recurring tasks completed whose next due fell after ``until``: series over.
        unknown: Recurring tasks completed with no next occurrence: a period TAME does
            not know, or no due date (imported).
    """

    done: tuple[Task, ...] = ()
    next: tuple[tuple[Task, Task], ...] = ()
    last: tuple[Task, ...] = ()
    unknown: tuple[Task, ...] = ()


@dataclass(frozen=True, slots=True)
class PurgeResult:
    """What :meth:`TaskService.purge` or :meth:`TaskService.purge_all` removed.

    Attributes:
        backup: Copy of the database written just before.
        purged: The tasks removed for good.
    """

    backup: Path
    purged: tuple[Task, ...]


@dataclass(frozen=True, slots=True)
class StartResult:
    """What :meth:`TaskService.start` did.

    Attributes:
        started: The tasks started, as stored.
        stopped: Other tasks stopped to keep one active, with the session just ended.
        already: Tasks that were active already, left as they were.
    """

    started: tuple[Task, ...] = ()
    stopped: tuple[tuple[Task, Session], ...] = ()
    already: tuple[Task, ...] = ()


class TaskService:
    """Entry point for task operations, shared by the CLI and a future TUI.

    Args:
        repo: Open task repository.
        clock: Returns the current aware datetime; injected for tests.
        undo_retention: Undo history older than this is purged on each write; None keeps all.
    """

    def __init__(
        self, repo: TaskRepo, clock: Clock = utc_now, undo_retention: timedelta | None = None
    ) -> None:
        self._repo = repo
        self._clock = clock
        self._undo_retention = undo_retention

    def add(
        self,
        description: str,
        *,
        project: str | None = None,
        tags: Iterable[str] = (),
        priority: str | None = None,
        due: datetime | None = None,
        wait: datetime | None = None,
        depends: TaskRefs = NO_REFS,
        recur: str | None = None,
        until: datetime | None = None,
    ) -> Task:
        """Create a pending task with the next free short id.

        Args:
            description: Task text; surrounding whitespace is stripped.
            project: Dotted project name.
            tags: Tag names, without leading ``+``.
            priority: H, M or L (any case).
            due: Due date (aware).
            wait: Hidden from filters until then (aware).
            depends: Tasks the new one waits for.
            recur: Recurrence period (SPEC §4 Recurrence); needs ``due``.
            until: End of the recurrence; needs ``recur``.

        Returns:
            The stored task.

        Raises:
            ValidationError: If a value is invalid, ``depends`` names no task, or the
                recurrence rules are broken.
        """
        now = self._clock()
        task = Task(
            uuid=str(uuid_lib.uuid4()),
            description=check_description(description),
            entry=now,
            modified=now,
            project=check_project(project) if project is not None else None,
            tags=frozenset(check_new_tag(tag) for tag in tags),
            priority=parse_priority(priority) if priority is not None else None,
            due=due,
            wait=wait,
            depends=self._resolve(depends),
            recur=check_recur(recur) if recur is not None else None,
            until=until,
        )
        task = anchored(_check_recurrence(task))
        with self._repo.transaction():
            task = replace(task, id=self._repo.max_pending_id() + 1)
            self._repo.insert(task)
            self._log(now, "add", [(task.uuid, None)])
        return task

    def complete(self, tasks: Iterable[Task]) -> list[Task]:
        """Mark ``tasks`` completed; see :meth:`done`.

        Returns:
            The changed tasks, as stored.
        """
        return list(self.done(tasks).done)

    def done(self, tasks: Iterable[Task]) -> DoneResult:
        """Mark ``tasks`` completed (``end`` = now), then renumber pending tasks.

        Tasks already completed are skipped. Each pending recurring task gets its next
        occurrence in the same undo step (SPEC §4 Recurrence).
        """
        now = self._clock()
        tasks = [task for task in tasks if task.status is not Status.COMPLETED]
        nexts: list[tuple[Task, Task]] = []
        last: list[Task] = []
        unknown: list[Task] = []
        for task in tasks:
            if task.status is not Status.PENDING or task.recur is None:
                continue
            if (due := next_due(task, now)) is None:
                unknown.append(task)
            elif task.until is not None and due > task.until:
                last.append(task)
            else:
                nexts.append((task, _next_occurrence(task, due, now)))
        changed = self._close(tasks, Status.COMPLETED, "done", [new for _, new in nexts])
        stored = [(old, self._repo.get(new.uuid) or new) for old, new in nexts]
        return DoneResult(tuple(changed), tuple(stored), tuple(last), tuple(unknown))

    def delete(self, tasks: Iterable[Task]) -> list[Task]:
        """Soft-delete ``tasks`` (``end`` = now), then renumber pending tasks.

        Tasks already deleted are skipped.

        Returns:
            The changed tasks, as stored.
        """
        return self._close(tasks, Status.DELETED, "delete")

    def _close(
        self, tasks: Iterable[Task], status: Status, cmd: str, created: Sequence[Task] = ()
    ) -> list[Task]:
        """Give ``tasks`` the closing ``status`` and store ``created``, in one undo step."""
        now = self._clock()
        changed = [
            replace(_stopped(task, now)[0], status=status, id=None, end=now, modified=now)
            for task in tasks
            if task.status is not status
        ]
        if not changed:
            return []
        with self._repo.transaction():
            ids = self._repo.pending_ids()
            before = self._snapshot(changed) + [(task.uuid, None) for task in created]
            self._log(now, cmd, before, ids)
            for task in changed:
                self._repo.update(task)
            last_id = self._repo.max_pending_id()  # Last ids: after older tasks of the same second.
            for number, task in enumerate(created, start=last_id + 1):
                self._repo.insert(replace(task, id=number))
            self._repo.renumber()
        return changed

    def start(self, tasks: Iterable[Task], *, multiple_active: bool = False) -> StartResult:
        """Start work on the pending ones of ``tasks`` (``start`` = now).

        Unless ``multiple_active``, the other active tasks are stopped first, each
        recording its session.

        Raises:
            ValidationError: If several tasks would start while only one may be active.
        """
        tasks = [task for task in tasks if task.status is Status.PENDING]
        already = tuple(task for task in tasks if task.start is not None)
        to_start = [task for task in tasks if task.start is None]
        if not to_start:
            return StartResult(already=already)
        if not multiple_active and len(to_start) > 1:
            raise ValidationError("error.one_active", count=len(to_start))
        now = self._clock()
        started = [replace(task, start=now, modified=now) for task in to_start]
        stopped: list[tuple[Task, Session]] = []
        if not multiple_active:
            for other in self.query(include_waiting=True):
                if other.start is not None and other.uuid not in {t.uuid for t in started}:
                    new, session = _stopped(other, now)
                    stopped.append((replace(new, modified=now), session))
        changed = started + [task for task, _ in stopped]
        with self._repo.transaction():
            self._log(now, "start", self._snapshot(changed))
            for task in changed:
                self._repo.update(task)
        return StartResult(tuple(started), tuple(stopped), already)

    def stop(self, tasks: Iterable[Task]) -> list[tuple[Task, Session]]:
        """Stop work on the active ones of ``tasks``, recording each session.

        Returns:
            The stopped tasks, as stored, with the session just ended.
        """
        now = self._clock()
        result = []
        for task in tasks:
            if task.active:
                new, session = _stopped(task, now)
                result.append((replace(new, modified=now), session))
        if result:
            with self._repo.transaction():
                self._log(now, "stop", self._snapshot([task for task, _ in result]))
                for task, _ in result:
                    self._repo.update(task)
        return result

    def modify(self, tasks: Iterable[Task], changes: Changes) -> list[Task]:
        """Apply ``changes`` to ``tasks``; ``modified`` = now on the tasks that change.

        Returns:
            The changed tasks, as stored. Tasks the changes leave as they were are skipped.

        Raises:
            ValidationError: If ``changes`` adds a virtual tag, names a task that does not
                exist, makes a task depend on itself or makes a cycle of dependencies, or
                breaks the recurrence rules (SPEC §4 Recurrence).
        """
        for tag in changes.tags_add:
            check_new_tag(tag)
        if changes.recur:
            check_recur(changes.recur)
        now = self._clock()
        tasks = list(tasks)
        new_tasks = [_recurrence_changed(task, changes) for task in tasks]
        if changes.depends is not None:
            new_tasks = self._apply_depends(new_tasks, changes.depends)
        changed = [
            replace(new, modified=now)
            for task, new in zip(tasks, new_tasks, strict=True)
            if new != task
        ]
        if not changed:
            return []
        with self._repo.transaction():
            self._log(now, "modify", self._snapshot(changed))
            for task in changed:
                self._repo.update(task)
        return changed

    def _apply_depends(self, tasks: list[Task], change: DependsChange) -> list[Task]:
        """Return ``tasks`` with ``change`` applied to their dependencies.

        Raises:
            ValidationError: On a task named that does not exist, a task depending on
                itself, or a cycle.
        """
        add, remove = self._resolve(change.add), self._resolve(change.remove)
        result = []
        for task in tasks:
            if task.uuid in add:
                raise ValidationError("error.depends_self", task=_ref(task))
            current = frozenset() if change.clear else task.depends
            result.append(replace(task, depends=(current - remove) | add))
        edges = self._repo.depends_edges()
        edges.update({task.uuid: set(task.depends) for task in result})
        for task in result:
            if cycle := _cycle(task.uuid, edges):
                names = [_ref(found) if (found := self._repo.get(u)) else u[:8] for u in cycle]
                raise ValidationError("error.depends_cycle", chain=" → ".join(names))
        return result

    def _resolve(self, refs: TaskRefs) -> frozenset[str]:
        """Return the uuids of the tasks ``refs`` names: ids of pending tasks, uuid prefixes.

        Raises:
            ValidationError: If an id or prefix names no task, or a prefix several.
        """
        if not refs:
            return frozenset()
        by_id = {number: uuid for uuid, number in self._repo.pending_ids().items()}
        uuids: set[str] = set()
        for number in sorted(refs.ids):
            if number not in by_id:
                raise ValidationError("error.no_task", ref=str(number))
            uuids.add(by_id[number])
        for prefix in refs.uuid_prefixes:
            found = self.query(Filter(uuid_prefixes=(prefix,), status=ALL), include_waiting=True)
            if len(found) != 1:
                key = "error.no_task" if not found else "error.ambiguous_task"
                raise ValidationError(key, ref=prefix)
            uuids.add(found[0].uuid)
        return frozenset(uuids)

    def links(self) -> Links:
        """Return the dependencies between pending tasks."""
        ids = self._repo.pending_ids()
        blocking = {
            target
            for uuid, targets in self._repo.depends_edges().items()
            if uuid in ids
            for target in targets
            if target in ids
        }
        return Links(ids=ids, blocking=frozenset(blocking))

    def get(self, uuid: str) -> Task | None:
        """Return the task with this full uuid, or None."""
        return self._repo.get(uuid)

    def dependents(self, task: Task) -> list[Task]:
        """Return the pending tasks that depend on ``task``, by short id."""
        return [other for other in self.query(include_waiting=True) if task.uuid in other.depends]

    def unblocked_by(self, done: Iterable[Task]) -> list[Task]:
        """Return the pending tasks that waited for one of ``done`` and wait for nothing now."""
        uuids = {task.uuid for task in done}
        links = self.links()
        return [
            task
            for task in self.query(include_waiting=True)
            if task.depends & uuids and not links.is_blocked(task)
        ]

    def annotate(self, tasks: Iterable[Task], text: str) -> list[Task]:
        """Add an annotation (entry = now) to each of ``tasks``; ``modified`` = now.

        Returns:
            The changed tasks, as stored.

        Raises:
            ValidationError: If ``text`` is blank.
        """
        if not (text := text.strip()):
            raise ValidationError("error.empty_annotation")
        now = self._clock()
        note = Annotation(now, text)
        changed = [
            replace(task, annotations=(*task.annotations, note), modified=now) for task in tasks
        ]
        return self._write("annotate", now, changed)

    def denotate(self, tasks: Iterable[Task], text: str = "") -> list[Task]:
        """Remove one annotation from each of ``tasks``; ``modified`` = now.

        The annotation removed is the one whose text equals ``text`` (case-insensitive),
        else the only one containing it, else (``text`` empty) the most recent. Tasks
        without such an annotation are left as they are.

        Returns:
            The changed tasks, as stored.

        Raises:
            ValidationError: If several annotations of a task contain ``text``; nothing
                is changed.
        """
        now = self._clock()
        changed = []
        for task in tasks:
            if (index := _annotation_to_remove(task, text.strip())) is not None:
                notes = task.annotations[:index] + task.annotations[index + 1 :]
                changed.append(replace(task, annotations=notes, modified=now))
        return self._write("denotate", now, changed)

    def _write(self, cmd: str, now: datetime, changed: list[Task]) -> list[Task]:
        """Store ``changed`` tasks in one undoable transaction; nothing to do if empty."""
        if not changed:
            return []
        with self._repo.transaction():
            self._log(now, cmd, self._snapshot(changed))
            for task in changed:
                self._repo.update(task)
        return changed

    def import_tasks(self, tasks: Iterable[Task]) -> ImportResult:
        """Merge ``tasks`` by uuid: add new ones, update older ones, skip the others.

        A stored task is replaced only if the incoming ``modified`` is newer. New pending
        tasks get the next free short ids, in entry order; if an update changes which
        tasks are pending, all pending tasks are renumbered. One undo step.

        Returns:
            What was added, updated and skipped.
        """
        skipped: list[Task] = []
        before: dict[str, Task | None] = {}
        with self._repo.transaction():
            ids = self._repo.pending_ids()
            for task in tasks:
                current = self._repo.get(task.uuid)
                if current is not None and task.modified <= current.modified:
                    skipped.append(task)
                    continue
                before.setdefault(task.uuid, current)
                self._repo.restore(replace(task, id=current.id if current else None))
            if before:
                self._log(self._clock(), "import", list(before.items()), ids)
                self._number_imported(before)
            stored = {uuid: self._repo.get(uuid) for uuid in before}
        return ImportResult(
            added=tuple(t for u, t in stored.items() if t and before[u] is None),
            updated=tuple(t for u, t in stored.items() if t and before[u] is not None),
            skipped=tuple(skipped),
        )

    def _number_imported(self, before: Mapping[str, Task | None]) -> None:
        """Give short ids to imported tasks (see :meth:`import_tasks`)."""
        stored = [task for uuid in before if (task := self._repo.get(uuid)) is not None]
        if any(
            (old.status is Status.PENDING) != (task.status is Status.PENDING)
            for task in stored
            if (old := before[task.uuid]) is not None
        ):
            self._repo.renumber()
            return
        next_id = self._repo.max_pending_id()
        for task in sorted(stored, key=lambda task: task.entry):
            if task.status is Status.PENDING and task.id is None:
                next_id += 1
                self._repo.update(replace(task, id=next_id))

    def undo(self) -> UndoResult:
        """Revert the last write command (``add``, ``done``, ``delete``, ``modify``, ``import``).

        Each call goes one command further back. An undo cannot itself be undone.

        Returns:
            What was reverted.

        Raises:
            NoMatchError: If there is nothing to undo.
        """
        with self._repo.transaction():
            entry = self._repo.last_undo()
            if entry is None:
                raise NoMatchError("error.nothing_to_undo")
            restored: list[str] = []
            removed: list[Task] = []
            for uuid, task in entry.before:
                if task is None:
                    if (current := self._repo.get(uuid)) is not None:
                        removed.append(current)
                    self._repo.remove(uuid)
                else:
                    self._repo.restore(task)
                    restored.append(uuid)
            if entry.ids is not None:
                self._repo.set_ids(entry.ids)
            self._repo.drop_undo(entry.seq)
            tasks = tuple(task for uuid in restored if (task := self._repo.get(uuid)))
        return UndoResult(cmd=entry.cmd, restored=tasks, removed=tuple(removed))

    def purge(self, tasks: Iterable[Task]) -> PurgeResult:
        """Remove the deleted ones of ``tasks`` for good, after a backup of the database.

        Their annotations and dependencies go too, and so do other tasks' dependencies
        on them. Not undoable: the undo history is cleared.

        Raises:
            NoMatchError: If none of ``tasks`` is deleted (nothing written, no backup).
            StorageError: If the backup cannot be written (nothing removed).
        """
        doomed = tuple(task for task in tasks if task.status is Status.DELETED)
        if not doomed:
            raise NoMatchError("error.nothing_to_purge")
        backup = self._backup()
        with self._repo.transaction():
            self._repo.purge([task.uuid for task in doomed])
            self._repo.clear_undo()
        return PurgeResult(backup=backup, purged=doomed)

    def purge_all(self) -> PurgeResult:
        """Remove every task for good, after a backup; app state (``meta``) is kept.

        Raises:
            NoMatchError: If there is no task at all (nothing written, no backup).
            StorageError: If the backup cannot be written (nothing removed).
        """
        doomed = tuple(self.query(Filter(status=ALL), include_waiting=True))
        if not doomed:
            raise NoMatchError("error.nothing_to_purge")
        backup = self._backup()
        with self._repo.transaction():
            self._repo.purge_all()
            self._repo.clear_undo()
        return PurgeResult(backup=backup, purged=doomed)

    def _backup(self) -> Path:
        """Copy the database to ``tame-YYYYMMDD-HHMMSS.db.bak`` (local time) next to it."""
        folder = self._repo.path.parent
        stem = f"tame-{self._clock().astimezone():%Y%m%d-%H%M%S}"
        target = folder / f"{stem}.db.bak"
        number = 1
        while target.exists():
            number += 1
            target = folder / f"{stem}-{number}.db.bak"
        self._repo.backup(target)
        return target

    def _log(
        self,
        now: datetime,
        cmd: str,
        before: list[tuple[str, Task | None]],
        ids: dict[str, int] | None = None,
    ) -> None:
        """Log a write command for undo, and purge history past the retention."""
        self._repo.push_undo(now, cmd, before, ids)
        if self._undo_retention is not None:
            self._repo.prune_undo(now - self._undo_retention)

    def _snapshot(self, tasks: Iterable[Task]) -> list[tuple[str, Task | None]]:
        """Return the stored state of ``tasks``, for the undo log."""
        return [(task.uuid, self._repo.get(task.uuid)) for task in tasks]

    def state(self, key: str) -> str | None:
        """Return a small piece of app state (``meta`` table), or None if unset."""
        return self._repo.get_meta(key)

    def set_state(self, key: str, value: str) -> None:
        """Store a small piece of app state (``meta`` table); not part of undo."""
        self._repo.set_meta(key, value)

    def query(self, where: Condition | None = None, *, include_waiting: bool = False) -> list[Task]:
        """Return the tasks matching ``where`` (default: all pending).

        Waiting tasks are left out unless ``include_waiting`` or the filter shows them
        (SPEC §4). Ordered by status (pending, completed, deleted), then short id, then
        entry.
        """
        return self.query_hidden(where, include_waiting=include_waiting)[0]

    def query_hidden(
        self, where: Condition | None = None, *, include_waiting: bool = False
    ) -> tuple[list[Task], int]:
        """Like :meth:`query`, also returning how many waiting tasks were left out."""
        where = where or Filter()
        now = self._clock()
        tagger = self.virtual_tagger() if where.uses_virtual_tags else None
        hide = not (include_waiting or where.shows_waiting)
        shown: list[Task] = []
        hidden = 0
        for status in where.statuses:
            for task in self._repo.by_status(status):
                if not where.matches(task, tagger(task) if tagger else frozenset()):
                    continue
                if hide and is_waiting(task, now):
                    hidden += 1
                else:
                    shown.append(task)
        return shown, hidden

    def virtual_tagger(self) -> VirtualTagger:
        """Return a tagger computing virtual tags as of now, in the system time zone."""
        return VirtualTagger(self._clock(), self.links())


def _recurrence_changed(task: Task, changes: Changes) -> Task:
    """Return ``task`` with ``changes`` applied, recurrence rules checked, anchor kept.

    Raises:
        ValidationError: If the result breaks the recurrence rules.
    """
    new = changes.apply(task)
    if changes.recur is None and changes.until is None and changes.due is None:
        return new
    if new.recur is None and task.recur is not None and changes.until is None:
        new = replace(new, until=None)  # `recur:` ends the series, and its end with it.
    new = _check_recurrence(new)
    if changes.recur is not None or changes.due is not None:
        new = anchored(new)
    return new


def _check_recurrence(task: Task) -> Task:
    """Return ``task`` if its ``recur`` has a ``due`` and its ``until`` a ``recur``.

    Raises:
        ValidationError: Otherwise.
    """
    if task.recur is not None and task.due is None:
        raise ValidationError("error.recur_needs_due")
    if task.until is not None and task.recur is None:
        raise ValidationError("error.until_needs_recur")
    return task


def _next_occurrence(task: Task, due: datetime, now: datetime) -> Task:
    """Return the pending task following ``task`` in its series, due on ``due``."""
    shift = due - task.due if task.due is not None else None
    anchor = {ANCHOR: task.extra[ANCHOR]} if ANCHOR in task.extra else {}
    return Task(
        uuid=str(uuid_lib.uuid4()),
        description=task.description,
        entry=now,
        modified=now,
        project=task.project,
        tags=task.tags,
        priority=task.priority,
        due=due,
        wait=task.wait + shift if task.wait is not None and shift is not None else None,
        recur=task.recur,
        until=task.until,
        extra=anchor,
    )


def _stopped(task: Task, now: datetime) -> tuple[Task, Session]:
    """Return ``task`` with its current session ended at ``now``, and that session.

    A task not started is returned as is, with an empty session.
    """
    if task.start is None:
        return task, Session(now, now)
    session = Session(task.start, max(now, task.start))
    return replace(task, start=None, sessions=(*task.sessions, session)), session


def _ref(task: Task) -> str:
    """Name ``task`` as the user knows it: short id, else uuid prefix."""
    return str(task.id) if task.id is not None else task.uuid[:8]


def _cycle(start: str, edges: Mapping[str, set[str]]) -> list[str]:
    """Return a dependency path from ``start`` back to itself, or ``[]`` if none."""
    path = [start]
    seen: set[str] = set()

    def walk(node: str) -> bool:
        for target in sorted(edges.get(node, ())):
            if target == start:
                path.append(target)
                return True
            if target not in seen:
                seen.add(target)
                path.append(target)
                if walk(target):
                    return True
                path.pop()
        return False

    return path if walk(start) else []


def _annotation_to_remove(task: Task, text: str) -> int | None:
    """Return the index of the annotation ``denotate`` removes from ``task``, if any.

    Raises:
        ValidationError: If several annotations contain ``text``.
    """
    notes = task.annotations
    if not notes:
        return None
    if not text:
        return max(range(len(notes)), key=lambda i: (notes[i].entry, i))
    wanted = text.casefold()
    exact = [i for i, note in enumerate(notes) if note.description.casefold() == wanted]
    if exact:
        return exact[0]
    partial = [i for i, note in enumerate(notes) if wanted in note.description.casefold()]
    if len(partial) > 1:
        raise ValidationError(
            "error.ambiguous_annotation",
            task=str(task.id) if task.id is not None else task.uuid[:8],
            text=text,
            candidates=", ".join(f"'{notes[i].description}'" for i in partial),
        )
    return partial[0] if partial else None
