"""Shared XML plumbing: parsing, MayRequire gating and packageId normalisation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lxml import etree

_PARSER = etree.XMLParser(
    recover=False,
    resolve_entities=False,
    huge_tree=True,
    remove_blank_text=False,
    remove_comments=False,
)


@dataclass(frozen=True)
class ParseFailure:
    path: Path
    line: int
    message: str


def normalise_package_id(package_id: str) -> str:
    """RimWorld compares packageIds case-insensitively and ignores the copy/steam suffixes."""
    pid = package_id.strip().lower()
    for suffix in ("_steam", "_copy"):
        if pid.endswith(suffix):
            pid = pid[: -len(suffix)]
    return pid


def parse_file(path: Path) -> etree._Element:
    """Parse an XML file, tolerating a UTF-8 BOM. Raises etree.XMLSyntaxError."""
    return etree.fromstring(path.read_bytes(), _PARSER)


def parse_failure(path: Path, exc: etree.XMLSyntaxError) -> ParseFailure:
    line, _ = getattr(exc, "position", (0, 0))
    message = str(exc).split(", line ")[0]
    return ParseFailure(path=path, line=line or 0, message=message)


def _split_ids(raw: str) -> list[str]:
    return [normalise_package_id(part) for part in raw.split(",") if part.strip()]


def apply_may_require(root: etree._Element, active: frozenset[str]) -> int:
    """Drop nodes gated by MayRequire/MayRequireAnyOf on inactive packageIds.

    The game does this at load time before any xpath runs, so a patch targeting a
    gated-out node is expected to match nothing and must not be reported.
    Returns the number of nodes removed. The root itself gating out means the whole
    document is empty, signalled by returning -1.
    """
    doomed: list[etree._Element] = []
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        required = element.get("MayRequire")
        if required is not None and not all(pid in active for pid in _split_ids(required)):
            doomed.append(element)
            continue
        any_of = element.get("MayRequireAnyOf")
        if any_of is not None and not any(pid in active for pid in _split_ids(any_of)):
            doomed.append(element)

    if root in doomed:
        return -1
    removed = 0
    for element in doomed:
        parent = element.getparent()
        if parent is not None:
            parent.remove(element)
            removed += 1
    return removed


def find_path(parent: Path, name: str) -> Path | None:
    """Child of `parent` named `name`, falling back to a case-insensitive scan.

    Mod folders are authored on Windows and shipped to Linux, so Defs/defs and
    About.xml/about.xml both turn up in the wild.
    """
    direct = parent / name
    if direct.exists():
        return direct
    if not parent.is_dir():
        return None
    lowered = name.lower()
    try:
        for entry in parent.iterdir():
            if entry.name.lower() == lowered:
                return entry
    except OSError:
        return None
    return None


def display_path(path: Path, base: Path) -> str:
    """`path` written relative to `base` with forward slashes, or absolute if unrelated."""
    try:
        return str(path.relative_to(base)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def child_elements(element: etree._Element) -> list[etree._Element]:
    """Element children only, skipping comments and processing instructions."""
    return [child for child in element if isinstance(child.tag, str)]


def text_of(element: etree._Element | None) -> str:
    if element is None:
        return ""
    return "".join(element.itertext()).strip()
