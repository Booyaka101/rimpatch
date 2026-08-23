"""Assemble the single in-memory <Defs> document the game assembles, in load order."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from .discover import Mod
from .xmlutil import (
    ParseFailure,
    apply_may_require,
    child_elements,
    find_path,
    parse_failure,
    parse_file,
    text_of,
)


@dataclass(frozen=True)
class DefSource:
    mod: Mod
    path: Path
    rel_path: str
    line: int
    def_type: str
    def_name: str
    name: str
    parent_name: str
    abstract: bool


@dataclass(frozen=True)
class DuplicateDef:
    def_type: str
    def_name: str
    sources: tuple[DefSource, ...]


@dataclass
class DefDatabase:
    root: etree._Element
    tree: etree._ElementTree
    sources: dict[etree._Element, DefSource] = field(default_factory=dict)
    parse_errors: list[tuple[Mod, ParseFailure]] = field(default_factory=list)
    files_read: int = 0
    gated_nodes: int = 0

    @property
    def def_count(self) -> int:
        return len(self.root)

    def def_names(self, def_type: str) -> list[str]:
        return sorted(
            {
                source.def_name
                for source in self.sources.values()
                if source.def_type == def_type and source.def_name
            }
        )

    def all_def_types(self) -> list[str]:
        return sorted({source.def_type for source in self.sources.values()})

    def duplicates(self) -> list[DuplicateDef]:
        buckets: dict[tuple[str, str], list[DefSource]] = defaultdict(list)
        for source in self.sources.values():
            if source.def_name:
                buckets[(source.def_type, source.def_name)].append(source)
        result = []
        for (def_type, def_name), sources in sorted(buckets.items()):
            if len(sources) > 1:
                ordered = tuple(sorted(sources, key=lambda src: (src.rel_path, src.line)))
                result.append(DuplicateDef(def_type, def_name, ordered))
        return result


def xml_files(folders: list[Path], subdir: str) -> list[tuple[str, Path]]:
    """(relative path, absolute path) for every .xml under <folder>/<subdir>, later folders winning.

    The game keeps one file per relative path across a mod's content folders, with the
    highest-priority folder winning; folders arrive here in ascending priority.
    """
    chosen: dict[str, Path] = {}
    for folder in folders:
        target = find_path(folder, subdir)
        if target is None or not target.is_dir():
            continue
        for path in target.rglob("*"):
            if path.is_file() and path.suffix.lower() == ".xml":
                chosen[str(path.relative_to(target)).replace("\\", "/")] = path
    return sorted(chosen.items())


def load_defs(mods: list[Mod], active: frozenset[str], version: str) -> DefDatabase:
    """Parse every XML under Defs/ for every mod, gate MayRequire, merge into one document."""
    root = etree.Element("Defs")
    database = DefDatabase(root=root, tree=etree.ElementTree(root))

    for mod in mods:
        folders = mod.content_folders(active, version)
        for _, path in xml_files(folders, "Defs"):
            try:
                file_root = parse_file(path)
            except etree.XMLSyntaxError as exc:
                database.parse_errors.append((mod, parse_failure(path, exc)))
                continue
            except OSError as exc:
                database.parse_errors.append(
                    (mod, ParseFailure(path=path, line=0, column=0, message=str(exc)))
                )
                continue

            database.files_read += 1
            removed = apply_may_require(file_root, active)
            if removed < 0:
                continue
            database.gated_nodes += removed

            rel_path = _relative(path, mod.path)
            for element in child_elements(file_root):
                line = element.sourceline or 0
                root.append(element)
                database.sources[element] = DefSource(
                    mod=mod,
                    path=path,
                    rel_path=rel_path,
                    line=line,
                    def_type=element.tag,
                    def_name=text_of(element.find("defName")),
                    name=element.get("Name", ""),
                    parent_name=element.get("ParentName", ""),
                    abstract=(element.get("Abstract", "").lower() == "true"),
                )
    return database


def _relative(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


__all__ = ["DefDatabase", "DefSource", "DuplicateDef", "load_defs", "xml_files"]
