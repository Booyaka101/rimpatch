"""Exit codes and output formats, which are what CI actually consumes."""

from __future__ import annotations

import json
import re
from pathlib import Path

from click.testing import CliRunner

from rimpatch import __version__
from rimpatch.cli import main

ANNOTATION = re.compile(r"^::error file=(?P<file>[^,]+),line=(?P<line>\d+),title=(?P<title>[^:]+)::")


def invoke(*args):
    return CliRunner().invoke(main, list(args))


def test_clean_run_prints_one_line_and_exits_zero(fixtures):
    result = invoke("check", "--mods", str(fixtures / "base"), "--mods", str(fixtures / "patcher"))
    assert result.exit_code == 0
    assert result.output.strip() == "0 findings (2 operations checked)"


def test_findings_exit_one(fixtures):
    result = invoke("check", "--mods", str(fixtures / "patcher"))
    assert result.exit_code == 1
    assert "2 findings in 1 file" in result.output


def test_exit_zero_flag_keeps_the_findings_but_drops_the_exit_code(fixtures):
    result = invoke("check", "--mods", str(fixtures / "patcher"), "--exit-zero")
    assert result.exit_code == 0
    assert "2 findings in 1 file" in result.output


def test_github_format_matches_the_annotation_shape(fixtures):
    result = invoke("check", "--mods", str(fixtures / "patcher"), "--format", "github")
    assert result.exit_code == 1
    lines = [line for line in result.output.splitlines() if line.startswith("::")]
    assert len(lines) == 2
    match = ANNOTATION.match(lines[0])
    assert match is not None
    assert match.group("file").endswith("Patches/Stats.xml")
    assert match.group("line") == "6"
    assert match.group("title") == "PatchOperationAdd"
    assert "%0A" in lines[0], "newlines must be escaped for GitHub"
    assert "\n" not in lines[0]


def test_json_format_is_machine_readable(fixtures):
    result = invoke("check", "--mods", str(fixtures / "patcher"), "--format", "json")
    payload = json.loads(result.output)
    assert payload["summary"]["findings"] == 2
    assert payload["summary"]["operationsChecked"] == 2
    finding = payload["findings"][0]
    assert finding["line"] == 6
    assert finding["class"] == "PatchOperationAdd"
    assert finding["kind"] == "no-match"
    assert finding["diagnosis"]["deepestMatch"] == "Defs"


def test_no_warnings_hides_warnings(fixtures):
    with_warnings = invoke("check", "--mods", str(fixtures / "base"), "--mods", str(fixtures / "dupe"))
    assert "warning" in with_warnings.output
    without = invoke(
        "check",
        "--mods",
        str(fixtures / "base"),
        "--mods",
        str(fixtures / "dupe"),
        "--no-warnings",
    )
    assert "warning" not in without.output
    assert without.exit_code == 0


def test_mods_config_sets_the_load_order(fixtures, tmp_path):
    config = tmp_path / "ModsConfig.xml"
    config.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<ModsConfigData><version>1.6.4871 rev590</version><activeMods>"
        "<li>Example.Base</li><li>Example.Patcher</li>"
        "</activeMods></ModsConfigData>\n",
        encoding="utf-8",
    )
    result = invoke(
        "mods",
        "--mods",
        str(fixtures / "patcher"),
        "--mods",
        str(fixtures / "base"),
        "--mods-config",
        str(config),
    )
    assert result.exit_code == 0
    body = result.output
    assert body.index("Example.Base") < body.index("Example.Patcher")
    assert "game version 1.6" in body


def test_repo_mode_resolves_a_sibling_dependency(fixtures):
    result = invoke("check", "--repo", str(fixtures / "patcher"))
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "0 findings (2 operations checked)"


def test_repo_mode_reports_an_unresolved_dependency_as_a_note(fixtures, tmp_path):
    lonely = tmp_path / "lonely"
    (lonely / "About").mkdir(parents=True)
    (lonely / "About" / "About.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<ModMetaData><name>Lonely</name><packageId>Example.Lonely</packageId>"
        "<modDependencies><li><packageId>Nobody.Missing</packageId>"
        "<displayName>Nobody Missing</displayName></li></modDependencies></ModMetaData>\n",
        encoding="utf-8",
    )
    result = invoke("check", "--repo", str(lonely))
    assert result.exit_code == 0
    assert "Nobody Missing" in result.output


def test_version_flag():
    result = invoke("--version")
    assert result.exit_code == 0
    assert __version__ in result.output


def test_running_inside_a_mod_folder_needs_no_arguments(fixtures, monkeypatch):
    monkeypatch.chdir(fixtures / "sequence")
    result = invoke("check")
    assert result.exit_code == 1
    assert "checking the current folder as a mod" in result.output
    assert "1 finding in 1 file" in result.output


def test_findings_with_no_vanilla_say_so(fixtures):
    result = invoke("check", "--mods", str(fixtures / "sequence"))
    assert result.exit_code == 1
    assert "No vanilla defs were loaded" in result.output
    assert "--game" in result.output


def fake_install(root: Path) -> Path:
    """A minimal <game>/Data/Core, so --game can be tested without RimWorld installed."""
    core = root / "Data" / "Core"
    (core / "About").mkdir(parents=True)
    (core / "About" / "About.xml").write_text(
        "<ModMetaData><packageId>Ludeon.RimWorld</packageId><name>Core</name></ModMetaData>",
        encoding="utf-8",
    )
    (core / "Defs").mkdir()
    (core / "Defs" / "Stats.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<Defs>\n  <StatDef>\n'
        "    <defName>Flammability</defName>\n    <category>BasicsNonPawn</category>\n"
        "  </StatDef>\n</Defs>\n",
        encoding="utf-8",
    )
    (root / "Version.txt").write_text("1.6.4871 rev590\n", encoding="utf-8")
    return root


def test_game_flag_loads_core_and_resolves_the_patch(fixtures, tmp_path):
    game = fake_install(tmp_path / "RimWorld")
    result = invoke("check", "--game", str(game), "--mods", str(fixtures / "patcher"))
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "0 findings (2 operations checked)"


def test_the_hint_is_absent_once_vanilla_is_present(fixtures, tmp_path):
    game = fake_install(tmp_path / "RimWorld")
    result = invoke(
        "check", "--game", str(game), "--mods", str(fixtures / "sequence")
    )
    assert result.exit_code == 1
    assert "No vanilla defs were loaded" not in result.output


def test_game_version_is_read_from_the_install(fixtures, tmp_path):
    game = fake_install(tmp_path / "RimWorld")
    result = invoke("mods", "--game", str(game), "--mods", str(fixtures / "patcher"))
    assert "game version 1.6" in result.output


def test_no_game_flag_is_accepted(fixtures):
    result = invoke("check", "--no-game", "--mods", str(fixtures / "base"))
    assert result.exit_code == 0


def test_mods_config_auto_explains_itself_when_nothing_is_found(fixtures):
    result = invoke(
        "check", "--mods", str(fixtures / "base"), "--mods-config", "auto"
    )
    assert result.exit_code == 2
    assert "could not find ModsConfig.xml" in result.output
    assert "rimpatch where" in result.output


def test_where_reports_what_it_can_and_cannot_find():
    result = invoke("where")
    assert result.exit_code == 0
    assert "RimWorld install" in result.output
    assert "ModsConfig.xml" in result.output
    # Detection is off for tests, so it must fall back to listing where it looked.
    assert "Looked for the install in:" in result.output
    assert "RIMWORLD_DIR" in result.output


def starved_mod(root: Path, *, dependency: str = "Example.Missing") -> Path:
    """A mod that declares a dependency and patches something that dependency would add."""
    (root / "About").mkdir(parents=True)
    (root / "About" / "About.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<ModMetaData>'
        "<packageId>Example.Starved</packageId><name>Example Starved</name>"
        f"<modDependencies><li><packageId>{dependency}</packageId>"
        f"<displayName>{dependency}</displayName></li></modDependencies>"
        "</ModMetaData>",
        encoding="utf-8",
    )
    (root / "Patches").mkdir()
    (root / "Patches" / "Starved.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<Patch>\n'
        '  <Operation Class="PatchOperationAdd">\n'
        '    <xpath>Defs/StatDef[defName="AddedByTheDependency"]</xpath>\n'
        "    <value><workerClass>X</workerClass></value>\n"
        "  </Operation>\n</Patch>\n",
        encoding="utf-8",
    )
    return root


def test_missing_dependency_is_named_next_to_the_findings_it_explains(fixtures, tmp_path):
    game = fake_install(tmp_path / "RimWorld")
    mod_dir = starved_mod(tmp_path / "Starved")
    result = invoke("check", "--game", str(game), "--mods", str(mod_dir))
    assert result.exit_code == 1
    assert "Example.Missing" in result.output
    assert "not in the load order" in result.output
    assert "which declare a dependency that is not loaded" in result.output


def test_no_dependency_warning_when_the_mods_patches_all_resolve(fixtures, tmp_path):
    """Declaring a dependency you do not need for your patches is not rimpatch's business."""
    game = fake_install(tmp_path / "RimWorld")
    result = invoke("check", "--game", str(game), "--mods", str(fixtures / "patcher"))
    assert result.exit_code == 0, result.output
    assert "Example.Base" not in result.output
    assert "dependency" not in result.output


def test_missing_core_outranks_a_missing_dependency(tmp_path):
    """With no vanilla at all, everything misses; blaming the dependency misleads."""
    mod_dir = starved_mod(tmp_path / "Starved")
    result = invoke("check", "--mods", str(mod_dir))
    assert result.exit_code == 1
    assert "No vanilla defs were loaded" in result.output
    assert "Example.Missing" not in result.output


def test_dependency_warning_goes_away_once_the_dependency_is_loaded(fixtures, tmp_path):
    game = fake_install(tmp_path / "RimWorld")
    mod_dir = starved_mod(tmp_path / "Starved", dependency="Example.Base")
    result = invoke(
        "check", "--game", str(game), "--mods", str(fixtures / "base"), "--mods", str(mod_dir)
    )
    assert "not in the load order" not in result.output
    assert "which declare a dependency" not in result.output


def test_json_reports_which_mods_are_missing_a_dependency(tmp_path):
    game = fake_install(tmp_path / "RimWorld")
    mod_dir = starved_mod(tmp_path / "Starved")
    result = invoke("check", "--game", str(game), "--mods", str(mod_dir), "--format", "json")
    payload = json.loads(result.output)
    assert payload["summary"]["starvedMods"] == ["Example.Starved"]


def test_mods_absent_from_modsconfig_are_called_out(fixtures, tmp_path):
    config = tmp_path / "ModsConfig.xml"
    config.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<ModsConfigData><version>1.6.4871 rev590</version><activeMods>"
        "<li>Example.Base</li></activeMods></ModsConfigData>\n",
        encoding="utf-8",
    )
    result = invoke(
        "check",
        "--mods",
        str(fixtures / "base"),
        "--mods",
        str(fixtures / "patcher"),
        "--mods-config",
        str(config),
    )
    assert "not active in ModsConfig but were checked anyway" in result.output
    assert "Example.Patcher" in result.output
