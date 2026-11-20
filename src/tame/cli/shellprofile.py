"""Tab completion in the user's shell profiles, driven by the ``completion`` setting.

SPEC §7 "Completion setup". TAME owns one block, between :data:`BEGIN` and :data:`END`,
in each profile; the rest of the file is never changed. Profiles are found once (asking
PowerShell where ``$PROFILE`` is) and cached in the ``meta`` table.
"""

import codecs
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from tame.cli import completion
from tame.core.service import TaskService
from tame.i18n import t

BEGIN = "# >>> tame completion >>>"
END = "# <<< tame completion <<<"
_PROFILES_KEY = "completion_profiles"
_TIP_KEY = "completion_tip"
_BLOCKED_KEY = "completion_blocked"
_BLOCKING_POLICIES = frozenset({"Restricted", "AllSigned"})
"""PowerShell execution policies under which a profile script fails to run."""
_ASK_PROFILE = "$PROFILE.CurrentUserCurrentHost; Get-ExecutionPolicy"


@dataclass(frozen=True, slots=True)
class Profile:
    """A shell profile TAME may write its completion block to.

    Attributes:
        shell: ``powershell`` or ``bash`` (a :data:`completion.SHELLS` name).
        path: The profile file.
        policy: PowerShell execution policy; ``""`` for bash.
    """

    shell: str
    path: str
    policy: str = ""

    @property
    def allowed(self) -> bool:
        """False if the shell would refuse to run the profile."""
        return self.policy not in _BLOCKING_POLICIES


def is_terminal() -> bool:
    """True if stdout is a terminal: profiles are only touched in interactive use."""
    return sys.stdout.isatty()


def discover() -> list[Profile]:
    """Find the profiles of the user's shells (may run PowerShell: about 0.3 s each)."""
    if sys.platform == "win32":
        # PSModulePath inherited from one PowerShell (tk run from pwsh, say) points the
        # other to modules it cannot load, so Get-ExecutionPolicy fails: let each shell
        # rebuild its own.
        env = {key: value for key, value in os.environ.items() if key.upper() != "PSMODULEPATH"}
        found = []
        for exe in ("powershell", "pwsh"):
            if shutil.which(exe) is None:
                continue
            try:
                result = subprocess.run(
                    [exe, "-NoProfile", "-NonInteractive", "-Command", _ASK_PROFILE],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                    env=env,
                )
            except (OSError, subprocess.SubprocessError):
                continue
            lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            if len(lines) == 2:
                found.append(Profile("powershell", lines[0], lines[1]))
        return found
    if Path(os.environ.get("SHELL", "")).name == "bash":
        return [Profile("bash", str(Path.home() / ".bashrc"))]
    return []


def edit_block(text: str, block: str | None, newline: str) -> str:
    """Return ``text`` with TAME's block replaced by ``block``, added, or (None) removed."""
    lines = text.splitlines()
    try:
        start = lines.index(BEGIN)
        end = lines.index(END, start)
    except ValueError:
        start = end = -1
    new = [BEGIN, *block.splitlines(), END] if block is not None else []
    if start >= 0:
        lines[start : end + 1] = new
    elif new:
        lines += ([""] if lines and lines[-1].strip() else []) + new
    return newline.join(lines) + newline if lines else ""


def has_block(text: str) -> bool:
    """True if ``text`` holds TAME's block."""
    return BEGIN in text.splitlines()


def _read(path: Path) -> tuple[str, str, str]:
    """Return the text, encoding and newline of ``path`` (empty UTF-8 if missing)."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return "", "utf-8", "\r\n" if sys.platform == "win32" else "\n"
    encoding = "utf-8"
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        encoding = "utf-16"
    elif data.startswith(codecs.BOM_UTF8):
        encoding = "utf-8-sig"
    text = data.decode(encoding)
    newline = "\r\n" if "\r\n" in text or (not text and sys.platform == "win32") else "\n"
    return text, encoding, newline


def _write_block(path: Path, block: str | None) -> bool:
    """Put ``block`` (None: remove it) in ``path``; return True if the file changed."""
    text, encoding, newline = _read(path)
    new = edit_block(text, block, newline)
    if new == text or (block is None and not text):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(new.encode(encoding))
    return True


def _cached(service: TaskService) -> list[Profile] | None:
    raw = service.state(_PROFILES_KEY)
    return None if raw is None else [Profile(**item) for item in json.loads(raw)]


def reconcile(
    service: TaskService,
    enabled: bool,
    names: Sequence[str],
    *,
    explicit: bool = False,
    find: Callable[[], list[Profile]] | None = None,
) -> list[str]:
    """Align the shell profiles with the ``completion`` setting.

    Args:
        service: For the cached profiles and one-time messages (``meta``).
        enabled: The ``completion`` setting.
        names: Command names to register (``tk``, ``tame``, aliases).
        explicit: The user just changed the setting: find the profiles again and
            report every outcome.
        find: Finds the profiles; default :func:`discover`, looked up at call time.

    Returns:
        Messages to print, in order.
    """
    profiles = _cached(service)
    if enabled and (explicit or profiles is None):
        profiles = (find or discover)()
        service.set_state(_PROFILES_KEY, json.dumps([asdict(p) for p in profiles]))
    if profiles is None:  # Never set up, and still disabled.
        if service.state(_TIP_KEY) is None:
            service.set_state(_TIP_KEY, "1")
            return [t("completion.tip")]
        return []
    messages = []
    if enabled and explicit and not profiles:
        messages.append(t("completion.none"))
    for profile in profiles:
        path = Path(profile.path)
        if not enabled:
            if _write_block(path, None):
                messages.append(t("completion.removed", path=path))
            continue
        if not profile.allowed:
            if explicit or service.state(_BLOCKED_KEY) is None:
                service.set_state(_BLOCKED_KEY, "1")
                messages.append(t("completion.blocked", path=path, policy=profile.policy))
            continue
        was_there = has_block(_read(path)[0])
        if _write_block(path, completion.script(profile.shell, names)) and not was_there:
            messages.append(t("completion.enabled", path=path))
        elif explicit and was_there:
            messages.append(t("completion.already", path=path))
    return messages
