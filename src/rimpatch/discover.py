"""Find mods on disk, read their About.xml, and put them in the order the game would load them."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from .errors import GameDataNotFound, NoModsFound, RimpatchError
from .xmlutil import (
    child_elements,
    find_path,
    normalise_package_id,
    parse_failure,
    parse_file,
    text_of,
)

# Official content ships inside <game>/Data and always loads first, in this order.
OFFICIAL_ORDER = (
    "ludeon.rimworld",
    "ludeon.rimworld.royalty",
    "ludeon.rimworld.ideology",
    "ludeon.rimworld.biotech",
    "ludeon.rimworld.anomaly",
    "ludeon.rimworld.odyssey",
)

_VERSION_DIR = re.compile(r"^\d+\.\d+$")


@dataclass(frozen=True)
class Dependency:
    package_id: str
    display_name: str


@dataclass(frozen=True)
class LoadFolder:
    """One <li> of a LoadFolders.xml version block."""

    folder: str
    if_mod_active: tuple[str, ...] = ()
    if_mod_not_active: tuple[str, ...] = ()
    if_mod_active_all: tuple[str, ...] = ()
    if_mod_not_active_all: tuple[str, ...] = ()

    def should_load(self, active: frozenset[str]) -> bool:
        # IfModActive/IfModNotActive are an OR; the *All variants (1.6) are an AND.
        if self.if_mod_active and not any(pid in active for pid in self.if_mod_active):
            return False
        if self.if_mod_not_active and any(pid in active for pid in self.if_mod_not_active):
            return False
        if self.if_mod_active_all and not all(pid in active for pid in self.if_mod_active_all):
            return False
        if self.if_mod_not_active_all and all(pid in active for pid in self.if_mod_not_active_all):
            return False
        return True


@dataclass
class Mod:
    path: Path
    package_id: str
    name: str
    author: str = ""
    supported_versions: tuple[str, ...] = ()
    dependencies: tuple[Dependency, ...] = ()
    load_after: tuple[str, ...] = ()
    load_before: tuple[str, ...] = ()
    load_folders: dict[str, tuple[LoadFolder, ...]] = field(default_factory=dict)
    official: bool = False
    about_problem: str | None = None

    @property
    def key(self) -> str:
        return normalise_package_id(self.package_id)

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"{self.name} ({self.package_id})"

    def content_folders(self, active: frozenset[str], version: str) -> list[Path]:
        """Folders this mod loads content from, in ascending priority (later wins)."""
        entries = self.load_folders.get(_version_key(version))
        if entries:
            folders = []
            for entry in entries:
                if not entry.should_load(active):
                    continue
                target = self.path if entry.folder in ("/", ".", "") else self.path / entry.folder
                if target.is_dir():
                    folders.append(target)
            if folders:
                return folders
        # No LoadFolders (or none matching this version): root, then Common, then <version>.
        folders = [self.path]
        for name in ("Common", version):
            candidate = self.path / name
            if candidate.is_dir():
                folders.append(candidate)
        return folders


def _version_key(version: str) -> str:
    return "v" + version.lstrip("v")


def _parse_load_folders(path: Path) -> dict[str, tuple[LoadFolder, ...]]:
    root = parse_file(path)
    result: dict[str, tuple[LoadFolder, ...]] = {}
    for version_node in child_elements(root):
        entries = []
        for item in child_elements(version_node):
            entries.append(
                LoadFolder(
                    folder=(item.text or "").strip(),
                    if_mod_active=_attr_ids(item, "IfModActive"),
                    if_mod_not_active=_attr_ids(item, "IfModNotActive"),
                    if_mod_active_all=_attr_ids(item, "IfModActiveAll"),
                    if_mod_not_active_all=_attr_ids(item, "IfModNotActiveAll"),
                )
            )
        result[version_node.tag] = tuple(entries)
    return result


def _attr_ids(element: etree._Element, name: str) -> tuple[str, ...]:
    raw = element.get(name)
    if not raw:
        return ()
    return tuple(normalise_package_id(part) for part in raw.split(",") if part.strip())


def read_mod(path: Path) -> Mod:
    """Read a mod folder. A mod with an unreadable About.xml is still returned, flagged."""
    about = _about_path(path)
    if about is None:
        return Mod(
            path=path,
            package_id=path.name.lower(),
            name=path.name,
            about_problem="no About/About.xml",
        )
    try:
        root = parse_file(about)
    except etree.XMLSyntaxError as exc:
        failure = parse_failure(about, exc)
        return Mod(
            path=path,
            package_id=path.name.lower(),
            name=path.name,
            about_problem=f"About.xml line {failure.line}: {failure.message}",
        )

    package_id = text_of(root.find("packageId"))
    name = text_of(root.find("name")) or path.name
    problem = None if package_id else "About.xml has no <packageId>"
    if not package_id:
        package_id = path.name.lower()

    versions = tuple(
        text_of(item) for item in root.findall("supportedVersions/li") if text_of(item)
    )
    dependencies = []
    for holder in ("modDependencies/li", "modDependenciesByVersion/*/li"):
        for item in root.findall(holder):
            dep_id = text_of(item.find("packageId"))
            if dep_id:
                dependencies.append(
                    Dependency(dep_id, text_of(item.find("displayName")) or dep_id)
                )

    load_folders: dict[str, tuple[LoadFolder, ...]] = {}
    folders_file = find_path(path, "LoadFolders.xml")
    if folders_file is not None:
        try:
            load_folders = _parse_load_folders(folders_file)
        except etree.XMLSyntaxError as exc:
            failure = parse_failure(folders_file, exc)
            problem = f"LoadFolders.xml line {failure.line}: {failure.message}"

    return Mod(
        path=path,
        package_id=package_id,
        name=name,
        author=text_of(root.find("author")),
        supported_versions=versions,
        dependencies=tuple(dependencies),
        load_after=_id_list(root, "loadAfter", "forceLoadAfter"),
        load_before=_id_list(root, "loadBefore", "forceLoadBefore"),
        load_folders=load_folders,
        about_problem=problem,
    )


def _id_list(root: etree._Element, *holders: str) -> tuple[str, ...]:
    found = []
    for holder in holders:
        for item in root.findall(f"{holder}/li"):
            value = text_of(item)
            if value:
                found.append(normalise_package_id(value))
    return tuple(found)


def _about_path(path: Path) -> Path | None:
    about_dir = find_path(path, "About")
    if about_dir is None or not about_dir.is_dir():
        return None
    return find_path(about_dir, "About.xml")


def is_mod_dir(path: Path) -> bool:
    return _about_path(path) is not None


def discover_game_mods(game_dir: Path) -> list[Mod]:
    """Core and the expansions from <game>/Data."""
    data = find_path(game_dir, "Data")
    if data is None or not data.is_dir():
        raise GameDataNotFound(
            f"no Data folder under {game_dir}. --game should point at the RimWorld "
            "install root, the folder containing Data/ and RimWorldWin64.exe."
        )
    mods = []
    for child in sorted(data.iterdir()):
        if child.is_dir() and is_mod_dir(child):
            mod = read_mod(child)
            mod.official = True
            mods.append(mod)
    if not mods:
        raise GameDataNotFound(f"{data} contains no mod folders with an About/About.xml")
    order = {pid: index for index, pid in enumerate(OFFICIAL_ORDER)}
    mods.sort(key=lambda mod: (order.get(mod.key, len(order)), mod.key))
    return mods


def expand_mod_paths(paths: list[Path]) -> list[Mod]:
    """Each path is either one mod folder or a folder containing mod folders."""
    mods: list[Mod] = []
    for path in paths:
        if not path.exists():
            raise RimpatchError(f"path does not exist: {path}")
        if not path.is_dir():
            raise RimpatchError(f"not a directory: {path}")
        if is_mod_dir(path):
            mods.append(read_mod(path))
            continue
        children = [
            child for child in sorted(path.iterdir()) if child.is_dir() and is_mod_dir(child)
        ]
        if not children:
            raise NoModsFound(
                f"{path} is not a mod (no About/About.xml) and contains no mod folders"
            )
        mods.extend(read_mod(child) for child in children)
    return mods


def read_mods_config(path: Path) -> tuple[list[str], str | None]:
    """Return (active packageIds in load order, game version) from a ModsConfig.xml."""
    if not path.exists():
        raise RimpatchError(f"ModsConfig.xml not found: {path}")
    try:
        root = parse_file(path)
    except etree.XMLSyntaxError as exc:
        failure = parse_failure(path, exc)
        raise RimpatchError(
            f"ModsConfig.xml is not valid XML (line {failure.line}: {failure.message})"
        ) from exc
    active = [
        normalise_package_id(text_of(item))
        for item in root.findall("activeMods/li")
        if text_of(item)
    ]
    if not active:
        raise RimpatchError(f"{path} has no <activeMods> entries")
    version = text_of(root.find("version")) or None
    return active, version


@dataclass
class LoadOrder:
    mods: list[Mod]
    missing: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    cyclic: list[str] = field(default_factory=list)
    unsatisfied: list[tuple[str, str]] = field(default_factory=list)
    # Checked even though ModsConfig does not list them as active.
    inactive: list[str] = field(default_factory=list)

    @property
    def active_ids(self) -> frozenset[str]:
        return frozenset(mod.key for mod in self.mods)


def unsatisfied_dependencies(mods: list[Mod]) -> list[tuple[str, str]]:
    """Declared modDependencies that are absent from the order, as (mod, dependency).

    A mod whose hard dependency is missing patches a def tree that is missing whatever
    that dependency contributes, so its operations report as unresolved even though
    nothing about the mod is wrong. Naming the dependency is the difference between a
    finding someone can act on and one that makes the tool look broken.
    """
    present = {mod.key for mod in mods}
    gaps = []
    for mod in mods:
        seen: set[str] = set()
        for dependency in mod.dependencies:
            key = normalise_package_id(dependency.package_id)
            if key in present or key in seen:
                continue
            seen.add(key)
            gaps.append((mod.package_id, dependency.display_name or dependency.package_id))
    return gaps


def order_by_declared_rules(mods: list[Mod]) -> tuple[list[Mod], list[str]]:
    """Refine the given order using each mod's own loadAfter/loadBefore/modDependencies.

    Without a ModsConfig.xml there is no real load order to read, and checking a mod
    before the mod it patches on top of reports failures the game would never see.
    The result keeps the given order wherever the mods do not say otherwise.
    """
    import heapq

    index = {mod.key: position for position, mod in enumerate(mods)}
    successors: dict[str, set[str]] = {mod.key: set() for mod in mods}
    incoming: dict[str, int] = {mod.key: 0 for mod in mods}

    def link(earlier: str, later: str) -> None:
        if earlier == later or earlier not in index or later not in index:
            return
        if later in successors[earlier]:
            return
        successors[earlier].add(later)
        incoming[later] += 1

    official_keys = {mod.key for mod in mods if mod.official}
    for mod in mods:
        for other in mod.load_after:
            link(other, mod.key)
        for dependency in mod.dependencies:
            link(normalise_package_id(dependency.package_id), mod.key)
        for other in mod.load_before:
            link(mod.key, other)
        # Official content loads first, except for the handful of mods that exist to
        # load before it - Harmony declares loadBefore Ludeon.RimWorld and means it.
        if not mod.official and not official_keys.intersection(mod.load_before):
            for key in official_keys:
                link(key, mod.key)

    ready = [index[key] for key, count in incoming.items() if count == 0]
    heapq.heapify(ready)
    ordered: list[Mod] = []
    broken: list[str] = []
    placed: set[str] = set()

    while len(ordered) < len(mods):
        if not ready:
            # A circular rule between two mods must not strand everything after them:
            # force the earliest unplaced mod and carry on.
            remaining = [mod for mod in mods if mod.key not in placed]
            forced = remaining[0]
            broken.append(forced.package_id)
            incoming[forced.key] = 0
            heapq.heappush(ready, index[forced.key])
        mod = mods[heapq.heappop(ready)]
        if mod.key in placed:
            continue
        placed.add(mod.key)
        ordered.append(mod)
        for successor in sorted(successors[mod.key], key=lambda key: index[key]):
            incoming[successor] -= 1
            if incoming[successor] <= 0 and successor not in placed:
                heapq.heappush(ready, index[successor])

    return ordered, broken


def resolve_load_order(
    mods: list[Mod], active: list[str] | None, *, auto_order: bool = True
) -> LoadOrder:
    """Order by ModsConfig <activeMods> when given, otherwise by the mods' own rules."""
    by_key: dict[str, Mod] = {}
    duplicates = []
    for mod in mods:
        if mod.key in by_key:
            duplicates.append(mod.package_id)
            continue
        by_key[mod.key] = mod

    def finish(order: LoadOrder) -> LoadOrder:
        order.unsatisfied = unsatisfied_dependencies(order.mods)
        return order

    if active is None:
        deduped = list(by_key.values())
        official = [mod for mod in deduped if mod.official]
        rest = [mod for mod in deduped if not mod.official]
        seeded = official + rest
        if not auto_order:
            return finish(LoadOrder(mods=seeded, duplicates=duplicates))
        ordered, cyclic = order_by_declared_rules(seeded)
        return finish(LoadOrder(mods=ordered, duplicates=duplicates, cyclic=cyclic))

    ordered = []
    missing = []
    for package_id in active:
        mod = by_key.pop(package_id, None)
        if mod is None:
            missing.append(package_id)
        else:
            ordered.append(mod)
    # Mods handed to us on the command line but absent from ModsConfig still get checked;
    # dropping them silently would make `rimpatch check --mods ./MyMod` report nothing.
    # ModsConfig is the real order for the mods it lists, so those keep their positions,
    # but the rest arrive in whatever order the disk gave us. Leaving that alone puts a
    # mod ahead of the dependency it declares it loads after, and every patch that needed
    # what the dependency contributes then reports as unresolved.
    extra = list(by_key.values())
    cyclic: list[str] = []
    if auto_order and extra:
        extra, cyclic = order_by_declared_rules(extra)
    ordered.extend(extra)
    return finish(
        LoadOrder(
            mods=ordered,
            missing=missing,
            duplicates=duplicates,
            cyclic=cyclic,
            inactive=[mod.package_id for mod in extra],
        )
    )


def find_sibling_dependencies(repo: Path, mod: Mod, already: set[str]) -> tuple[list[Mod], list[str]]:
    """For --repo: resolve declared modDependencies from checkouts beside the repo."""
    parent = repo.resolve().parent
    candidates: dict[str, Mod] = {}
    if parent.is_dir():
        for child in sorted(parent.iterdir()):
            if child.is_dir() and child.resolve() != repo.resolve() and is_mod_dir(child):
                found = read_mod(child)
                candidates.setdefault(found.key, found)

    resolved: list[Mod] = []
    unresolved: list[str] = []
    for dependency in mod.dependencies:
        key = normalise_package_id(dependency.package_id)
        if key in already:
            continue
        match = candidates.get(key)
        if match is None:
            unresolved.append(dependency.display_name or dependency.package_id)
        else:
            resolved.append(match)
            already.add(key)
    return resolved, unresolved


def game_version(game_dir: Path | None, mods_config_version: str | None, mods: list[Mod]) -> str:
    """Best available "1.6"-style version: the install, then ModsConfig, then the mods."""
    if game_dir is not None:
        version_file = find_path(game_dir, "Version.txt")
        if version_file is not None and version_file.is_file():
            raw = version_file.read_text(encoding="utf-8", errors="replace").strip()
            match = re.match(r"(\d+\.\d+)", raw)
            if match:
                return match.group(1)
    if mods_config_version:
        match = re.match(r"(\d+\.\d+)", mods_config_version)
        if match:
            return match.group(1)
    for mod in mods:
        for version in reversed(mod.supported_versions):
            if _VERSION_DIR.match(version):
                return version
    return "1.6"


__all__ = [
    "Dependency",
    "LoadFolder",
    "LoadOrder",
    "Mod",
    "OFFICIAL_ORDER",
    "discover_game_mods",
    "expand_mod_paths",
    "find_sibling_dependencies",
    "game_version",
    "is_mod_dir",
    "order_by_declared_rules",
    "read_mod",
    "read_mods_config",
    "resolve_load_order",
    "unsatisfied_dependencies",
]
