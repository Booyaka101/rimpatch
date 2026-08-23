"""Command line entry point."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from . import __version__
from .discover import (
    LoadOrder,
    Mod,
    discover_game_mods,
    expand_mod_paths,
    find_sibling_dependencies,
    is_mod_dir,
    read_mod,
    read_mods_config,
    resolve_load_order,
)
from .discover import (
    game_version as resolve_game_version,
)
from .engine import check as run_check
from .errors import RimpatchError
from .report import FORMATS, render, wants_color

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2

_PATH = click.Path(exists=False, file_okay=False, dir_okay=True, path_type=Path)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "-V", "--version", prog_name="rimpatch")
def main() -> None:
    """Find RimWorld PatchOperations that no longer resolve, without launching the game."""


def _load_order_options(func):
    func = click.option(
        "--game",
        type=_PATH,
        default=None,
        help="RimWorld install root (the folder holding Data/). Loads Core and the expansions.",
    )(func)
    func = click.option(
        "--mods",
        "mod_paths",
        type=_PATH,
        multiple=True,
        help="A mod folder, or a folder of mod folders. Repeatable; order is load order.",
    )(func)
    func = click.option(
        "--repo",
        type=_PATH,
        default=None,
        help="Check this checkout as a mod and resolve its modDependencies from sibling folders.",
    )(func)
    func = click.option(
        "--mods-config",
        type=click.Path(exists=False, dir_okay=False, path_type=Path),
        default=None,
        help="ModsConfig.xml to take the active list and load order from.",
    )(func)
    func = click.option(
        "--no-auto-order",
        is_flag=True,
        help="Do not reorder mods by their declared loadAfter/loadBefore/modDependencies.",
    )(func)
    func = click.option(
        "--game-version",
        default=None,
        help='Version used for LoadFolders and version subfolders, e.g. "1.6".',
    )(func)
    return func


def _build_load_order(
    game: Path | None,
    mod_paths: tuple[Path, ...],
    repo: Path | None,
    mods_config: Path | None,
    version_override: str | None,
    auto_order: bool,
) -> tuple[LoadOrder, str, list[str]]:
    notes: list[str] = []
    mods: list[Mod] = []

    if game is not None:
        mods.extend(discover_game_mods(game))

    if repo is not None:
        if not repo.exists():
            raise RimpatchError(f"--repo path does not exist: {repo}")
        if not is_mod_dir(repo):
            raise RimpatchError(
                f"{repo} has no About/About.xml, so it is not a mod folder. "
                "Point --repo at the folder containing About/, Defs/ and Patches/."
            )
        subject = read_mod(repo)
        already = {mod.key for mod in mods} | {subject.key}
        resolved, unresolved = find_sibling_dependencies(repo, subject, already)
        mods.extend(resolved)
        mods.append(subject)
        for name in unresolved:
            notes.append(
                f"declared dependency not found beside the checkout: {name}"
            )

    if mod_paths:
        mods.extend(expand_mod_paths(list(mod_paths)))

    if not mods:
        raise RimpatchError(
            "nothing to check. Pass --mods, --repo or --game (see `rimpatch check --help`)."
        )

    active: list[str] | None = None
    config_version: str | None = None
    if mods_config is not None:
        active, config_version = read_mods_config(mods_config)

    order = resolve_load_order(mods, active, auto_order=auto_order)
    version = version_override or resolve_game_version(game, config_version, order.mods)
    for package_id in order.duplicates:
        notes.append(f"packageId given more than once, later copy ignored: {package_id}")
    if order.cyclic:
        notes.append(
            "circular load order rules, forced an order for "
            + ", ".join(order.cyclic[:5])
            + ("..." if len(order.cyclic) > 5 else "")
        )
    return order, version, notes


@main.command()
@_load_order_options
@click.option(
    "--format",
    "fmt",
    type=click.Choice(FORMATS),
    default="text",
    show_default=True,
    help="Output format. github emits ::error annotations.",
)
@click.option(
    "--strict",
    is_flag=True,
    help='Also report operations whose <success> mode hides the failure.',
)
@click.option("--no-warnings", is_flag=True, help="Hide warnings such as duplicate defNames.")
@click.option("--exit-zero", is_flag=True, help="Always exit 0, even when there are findings.")
def check(
    game: Path | None,
    mod_paths: tuple[Path, ...],
    repo: Path | None,
    mods_config: Path | None,
    no_auto_order: bool,
    game_version: str | None,
    fmt: str,
    strict: bool,
    no_warnings: bool,
    exit_zero: bool,
) -> None:
    """Run every PatchOperation against the assembled Def tree and report what misses."""
    try:
        order, version, notes = _build_load_order(
            game, mod_paths, repo, mods_config, game_version, not no_auto_order
        )
        report = run_check(order, version, strict=strict, warnings=not no_warnings)
    except RimpatchError as exc:
        click.echo(f"rimpatch: {exc}", err=True)
        raise SystemExit(EXIT_ERROR) from exc

    for note in notes:
        click.echo(f"rimpatch: note: {note}", err=True)

    output = render(
        report,
        fmt,
        show_warnings=not no_warnings,
        color=wants_color(fmt, sys.stdout.isatty()),
    )
    click.echo(output)
    if exit_zero or report.ok:
        raise SystemExit(EXIT_OK)
    raise SystemExit(EXIT_FINDINGS)


@main.command("mods")
@_load_order_options
def mods_command(
    game: Path | None,
    mod_paths: tuple[Path, ...],
    repo: Path | None,
    mods_config: Path | None,
    no_auto_order: bool,
    game_version: str | None,
) -> None:
    """Print the resolved load order, which is what `check` will run against."""
    try:
        order, version, notes = _build_load_order(
            game, mod_paths, repo, mods_config, game_version, not no_auto_order
        )
    except RimpatchError as exc:
        click.echo(f"rimpatch: {exc}", err=True)
        raise SystemExit(EXIT_ERROR) from exc

    for note in notes:
        click.echo(f"rimpatch: note: {note}", err=True)

    click.echo(f"game version {version}")
    for index, mod in enumerate(order.mods, start=1):
        folders = mod.content_folders(order.active_ids, version)
        suffix = " [official]" if mod.official else ""
        click.echo(f"{index:3d}. {mod.package_id}{suffix}  {mod.name}")
        for folder in folders:
            click.echo(f"       {folder}")
    for missing in order.missing:
        click.echo(f"     active but not found on disk: {missing}")
    raise SystemExit(EXIT_OK)


if __name__ == "__main__":  # pragma: no cover
    main()
