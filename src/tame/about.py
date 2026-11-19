"""License and third-party information, read from the installed package metadata.

Never prints. The CLI turns this into ``tk help license`` and ``tk help credits``.
"""

import re
from dataclasses import dataclass
from importlib.metadata import Distribution, PackageNotFoundError, distribution

DIST_NAME = "tame-tasks"
"""Name of TAME's distribution package (PyPI)."""

_REQUIREMENT_NAME = re.compile(r"[A-Za-z0-9._-]+")


@dataclass(frozen=True, slots=True)
class Library:
    """An installed library TAME depends on, directly or not.

    Attributes:
        name: Distribution name, as published.
        version: Installed version.
        license: SPDX expression or license name; ``?`` if the metadata does not say.
    """

    name: str
    version: str
    license: str


def license_text() -> str | None:
    """Return TAME's license text from the installed package, or None if unavailable."""
    try:
        dist = distribution(DIST_NAME)
    except PackageNotFoundError:
        return None
    for path in dist.files or ():
        if path.name.upper().startswith("LICENSE"):
            return path.read_text(encoding="utf-8")
    return None


def libraries() -> list[Library]:
    """Return every installed library TAME needs at run time, sorted by name.

    Optional extras are skipped. A dependency that is not installed is skipped too.
    """
    found: dict[str, Library] = {}
    _collect(DIST_NAME, found)
    return sorted(found.values(), key=lambda library: library.name.lower())


def _collect(name: str, found: dict[str, Library]) -> None:
    try:
        dist = distribution(name)
    except PackageNotFoundError:
        return
    for requirement in dist.requires or ():
        if "extra ==" in requirement:
            continue
        match = _REQUIREMENT_NAME.match(requirement)
        if match is None:
            continue
        child = match[0]
        key = re.sub(r"[-_.]+", "-", child).lower()
        if key in found:
            continue
        try:
            child_dist = distribution(child)
        except PackageNotFoundError:
            continue
        found[key] = Library(child_dist.metadata["Name"], child_dist.version, _license(child_dist))
        _collect(child, found)


def _license(dist: Distribution) -> str:
    """Return the license of ``dist``: SPDX expression, else classifier, else License field."""
    metadata = dist.metadata
    if expression := metadata.get("License-Expression"):
        return str(expression)
    for classifier in metadata.get_all("Classifier") or ():
        text = str(classifier)
        if text.startswith("License :: OSI Approved :: "):
            return text.rsplit(" :: ", 1)[1].removesuffix(" License")
    license_field = str(metadata.get("License") or "").strip()
    return license_field.splitlines()[0][:40] if license_field else "?"
