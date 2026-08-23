"""Find the RimWorld install and the player's ModsConfig.xml without being told where they are.

Typing an install path is the first thing that stops someone using this, and the paths
differ per platform and per Steam library drive. Everything here is best effort: a
candidate is only ever returned once it has been confirmed on disk.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

#: Steam's app id for RimWorld.
APP_ID = "294100"

#: Point these at an install or a Config folder to skip searching for it.
GAME_ENV = "RIMWORLD_DIR"
CONFIG_ENV = "RIMWORLD_CONFIG_DIR"

#: Set to 1 to turn detection off, so a run cannot depend on what this machine has
#: installed. The test suite sets it, and reproducible CI should too.
OFF_ENV = "RIMPATCH_NO_AUTODETECT"


def autodetect_disabled() -> bool:
    return os.environ.get(OFF_ENV, "").strip().lower() in {"1", "true", "yes"}

_VDF_PATH = re.compile(r'"path"\s+"([^"]+)"')


def _home() -> Path:
    return Path.home()


def _steam_roots() -> list[Path]:
    roots: list[Path] = []
    if sys.platform == "win32":
        roots += [
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam",
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Steam",
        ]
        roots.append(_steam_root_from_registry())
    elif sys.platform == "darwin":
        roots.append(_home() / "Library" / "Application Support" / "Steam")
    else:
        roots += [
            _home() / ".steam" / "steam",
            _home() / ".steam" / "root",
            _home() / ".local" / "share" / "Steam",
            _home() / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
        ]
    return [root for root in roots if root is not None]


def _steam_root_from_registry() -> Path | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:  # pragma: no cover - Windows only
        return None
    for hive, key in (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
    ):
        try:
            with winreg.OpenKey(hive, key) as handle:
                for name in ("SteamPath", "InstallPath"):
                    try:
                        value, _ = winreg.QueryValueEx(handle, name)
                    except OSError:
                        continue
                    if value:
                        return Path(value)
        except OSError:
            continue
    return None


def steam_libraries() -> list[Path]:
    """Every Steam library folder, including the ones on other drives."""
    libraries: list[Path] = []
    seen: set[str] = set()

    def remember(path: Path) -> None:
        key = str(path).lower()
        if key not in seen and path.is_dir():
            seen.add(key)
            libraries.append(path)

    for root in _steam_roots():
        remember(root)
        manifests = (
            root / "steamapps" / "libraryfolders.vdf",
            root / "config" / "libraryfolders.vdf",
        )
        for manifest in manifests:
            if not manifest.is_file():
                continue
            try:
                text = manifest.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for raw in _VDF_PATH.findall(text):
                remember(Path(raw.replace("\\\\", "\\")))
    return libraries


def _looks_like_game(path: Path) -> bool:
    data = path / "Data"
    if not data.is_dir():
        return False
    return (data / "Core").is_dir() or any(
        child.is_dir() and (child / "About" / "About.xml").exists() for child in data.iterdir()
    )


def game_candidates() -> list[Path]:
    """Places a RimWorld install turns up, most likely first."""
    candidates: list[Path] = []

    override = os.environ.get(GAME_ENV)
    if override:
        candidates.append(Path(override))

    for library in steam_libraries():
        common = library / "steamapps" / "common"
        candidates.append(common / "RimWorld")
        # macOS keeps Data inside the app bundle.
        candidates.append(common / "RimWorld" / "RimWorldMac.app")

    if sys.platform == "win32":
        for drive in ("C:", "D:", "E:"):
            candidates += [
                Path(f"{drive}/GOG Games/RimWorld"),
                Path(f"{drive}/Games/RimWorld"),
                Path(f"{drive}/RimWorld"),
            ]
    elif sys.platform == "darwin":
        candidates += [
            Path("/Applications/RimWorld.app"),
            _home() / "Applications" / "RimWorld.app",
            _home() / "Library" / "Application Support" / "RimWorld",
        ]
    else:
        candidates += [
            _home() / "GOG Games" / "RimWorld",
            _home() / "games" / "rimworld",
            Path("/opt/RimWorld"),
        ]
    return candidates


def _first_confirmed(candidates: list[Path], confirm) -> Path | None:
    """First candidate `confirm` accepts. A candidate that cannot be read is skipped."""
    if autodetect_disabled():
        return None
    for candidate in candidates:
        try:
            if confirm(candidate):
                return candidate
        except OSError:
            continue
    return None


def find_game() -> Path | None:
    """The first RimWorld install that actually has a Data folder, or None."""
    return _first_confirmed(
        game_candidates(), lambda path: path.is_dir() and _looks_like_game(path)
    )


def config_candidates() -> list[Path]:
    """Places the Config folder holding ModsConfig.xml turns up."""
    candidates: list[Path] = []
    override = os.environ.get(CONFIG_ENV)
    if override:
        candidates.append(Path(override))

    ludeon = "Ludeon Studios/RimWorld by Ludeon Studios"
    if sys.platform == "win32":
        candidates.append(_home() / "AppData" / "LocalLow" / ludeon / "Config")
    elif sys.platform == "darwin":
        support = _home() / "Library" / "Application Support"
        candidates += [
            support / "RimWorld" / "Config",
            support / "Ludeon Studios" / "RimWorld by Ludeon Studios" / "Config",
            support / "unity.Ludeon Studios.RimWorld by Ludeon Studios" / "Config",
        ]
    else:
        candidates += [
            _home() / ".config" / "unity3d" / ludeon / "Config",
            _home() / ".config" / "RimWorld" / "Config",
            _home()
            / ".steam"
            / "steam"
            / "steamapps"
            / "compatdata"
            / APP_ID
            / "pfx"
            / "drive_c"
            / "users"
            / "steamuser"
            / "AppData"
            / "LocalLow"
            / ludeon
            / "Config",
        ]
    return candidates


def find_mods_config() -> Path | None:
    """The player's ModsConfig.xml, or None."""
    return _first_confirmed(
        [folder / "ModsConfig.xml" for folder in config_candidates()],
        lambda path: path.is_file(),
    )


__all__ = [
    "APP_ID",
    "CONFIG_ENV",
    "GAME_ENV",
    "OFF_ENV",
    "autodetect_disabled",
    "config_candidates",
    "find_game",
    "find_mods_config",
    "game_candidates",
    "steam_libraries",
]
