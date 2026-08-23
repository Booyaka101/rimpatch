"""Exit codes and output formats, which are what CI actually consumes."""

from __future__ import annotations

import json
import re

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
