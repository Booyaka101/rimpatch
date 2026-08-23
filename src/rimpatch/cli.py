"""Command line entry point."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from . import __version__, locate
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

_DIR = click.Path(exists=False, file_okay=False, dir_okay=True, path_type=Path)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "-V", "--version", prog_name="rimpatch")
def main() -> None:
    """Find RimWorld PatchOperations that no longer resolve, without launching the game.

    With no arguments, `rimpatch check` treats the current folder as the mod and looks
    for your RimWorld install automatically.
    """


def _load_order_options(func):
    func = click.option(
        "--game",
        type=_DIR,
        default=None,
        help="RimWorld install root (the folder holding Data/). Found automatically if omitted.",
    )(func)
    func = click.option(
        "--no-game",
        is_flag=True,
        help="Do not look for a RimWorld install. Vanilla defs will be absent.",
    )(func)
    func = click.option(
        "--mods",
        "mod_paths",
        type=_DIR,
        multiple=True,
        help="A mod folder, or a folder of mod folders. Repeatable; order is load order.",
    )(func)
    func = click.option(
        "--repo",
        type=_DIR,
        default=None,
        help="Check this checkout as a mod and resolve its modDependencies from sibling folders.",
    )(func)
    func = click.option(
        "--mods-config",
        default=None,
        metavar="PATH",
        help='ModsConfig.xml to take the active list and load order from, or "auto" to find it.',
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


def _resolve_mods_config(value: str | None, notes: list[str]) -> Path | None:
    if value is None:
        return None
    if value.strip().lower() == "auto":
        found = locate.find_mods_config()
        if found is None:
            raise RimpatchError(
                "could not find ModsConfig.xml automatically. Pass the path instead, or "
                f"set {locate.CONFIG_ENV}. `rimpatch where` shows everywhere it looked."
            )
        notes.append(f"using ModsConfig.xml at {found}")
        return found
    path = Path(value)
    if not path.exists():
        raise RimpatchError(f"ModsConfig.xml not found: {path}")
    return path


def _build_load_order(
    game: Path | None,
    no_game: bool,
    mod_paths: tuple[Path, ...],
    repo: Path | None,
    mods_config: str | None,
    version_override: str | None,
    auto_order: bool,
) -> tuple[LoadOrder, str, list[str]]:
    notes: list[str] = []
    mods: list[Mod] = []

    config_path = _resolve_mods_config(mods_config, notes)

    # With nothing named at all, the folder you are standing in is the obvious subject.
    if repo is None and not mod_paths:
        here = Path.cwd()
        if is_mod_dir(here):
            repo = here
            notes.append(f"checking the current folder as a mod: {here}")

    explicit_game = game is not None
    if game is None and not no_game:
        game = locate.find_game()
        if game is not None:
            notes.append(f"using the RimWorld install at {game}")

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
            notes.append(f"declared dependency not found beside the checkout: {name}")

    if mod_paths:
        mods.extend(expand_mod_paths(list(mod_paths)))

    # An install found by searching this machine supports the check; it is never the
    # thing being checked. Without a subject there is nothing to report on.
    if not mods or (not explicit_game and not any(not mod.official for mod in mods)):
        raise RimpatchError(
            "nothing to check. Run rimpatch from inside a mod folder, or pass --mods, "
            "--repo or --game (see `rimpatch check --help`)."
        )

    active: list[str] | None = None
    config_version: str | None = None
    if config_path is not None:
        active, config_version = read_mods_config(config_path)

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
    help="Also report operations whose <success> mode hides the failure.",
)
@click.option("--no-warnings", is_flag=True, help="Hide warnings such as duplicate defNames.")
@click.option("--exit-zero", is_flag=True, help="Always exit 0, even when there are findings.")
def check(
    game: Path | None,
    no_game: bool,
    mod_paths: tuple[Path, ...],
    repo: Path | None,
    mods_config: str | None,
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
            game, no_game, mod_paths, repo, mods_config, game_version, not no_auto_order
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
    no_game: bool,
    mod_paths: tuple[Path, ...],
    repo: Path | None,
    mods_config: str | None,
    no_auto_order: bool,
    game_version: str | None,
) -> None:
    """Print the resolved load order, which is what `check` will run against."""
    try:
        order, version, notes = _build_load_order(
            game, no_game, mod_paths, repo, mods_config, game_version, not no_auto_order
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


@main.command("where")
def where_command() -> None:
    """Show the RimWorld install and ModsConfig.xml rimpatch can find, and where it looked."""
    game = locate.find_game()
    click.echo(f"RimWorld install : {game or 'not found'}")
    config = locate.find_mods_config()
    click.echo(f"ModsConfig.xml   : {config or 'not found'}")

    libraries = locate.steam_libraries()
    click.echo("\nSteam libraries:")
    for library in libraries or []:
        click.echo(f"  {library}")
    if not libraries:
        click.echo("  none found")

    if game is None:
        click.echo("\nLooked for the install in:")
        for candidate in locate.game_candidates():
            click.echo(f"  {candidate}")
        click.echo(f"\nSet {locate.GAME_ENV} to point at it directly.")
    if config is None:
        click.echo("\nLooked for the config in:")
        for candidate in locate.config_candidates():
            click.echo(f"  {candidate}")
        click.echo(f"\nSet {locate.CONFIG_ENV} to point at that folder.")
    raise SystemExit(EXIT_OK)


if __name__ == "__main__":  # pragma: no cover
    main()
