"""A mod with existing breakage has to be able to adopt this without going red forever."""

from __future__ import annotations

import json

from click.testing import CliRunner

from rimpatch import baseline
from rimpatch.cli import main


def invoke(*args):
    return CliRunner().invoke(main, list(args))


def test_the_adoption_workflow(fixtures, tmp_path):
    record = tmp_path / "rimpatch-baseline.json"
    subject = str(fixtures / "patcher")

    # Day one: the mod is broken.
    before = invoke("check", "--mods", subject)
    assert before.exit_code == 1

    # Freeze it.
    written = invoke("check", "--mods", subject, "--write-baseline", str(record))
    assert written.exit_code == 0
    assert "wrote 2 finding(s)" in written.output
    assert record.is_file()

    # CI is green, and says what it accepted.
    after = invoke("check", "--mods", subject, "--baseline", str(record))
    assert after.exit_code == 0
    assert "2 accepted by the baseline" in after.output


def test_a_new_break_is_still_reported(fixtures, tmp_path):
    record = tmp_path / "base.json"
    subject = str(fixtures / "patcher")
    invoke("check", "--mods", subject, "--write-baseline", str(record))

    # A finding that is not in the baseline must come through.
    result = invoke("check", "--mods", subject, "--mods", str(fixtures / "sequence"), "--baseline", str(record))
    assert result.exit_code == 1
    assert "1 finding in 1 file" in result.output
    assert "2 accepted by the baseline" in result.output


def test_fixed_entries_are_reported_as_no_longer_needed(fixtures, tmp_path):
    record = tmp_path / "base.json"
    invoke("check", "--mods", str(fixtures / "patcher"), "--write-baseline", str(record))

    # Loading the base mod fixes both baselined findings.
    result = invoke(
        "check",
        "--mods",
        str(fixtures / "base"),
        "--mods",
        str(fixtures / "patcher"),
        "--baseline",
        str(record),
    )
    assert result.exit_code == 0
    assert "2 baseline entries no longer needed" in result.output


def test_fingerprint_survives_a_line_number_change(fixtures, tmp_path):
    """Adding a comment above an operation must not un-baseline it."""
    mod = tmp_path / "shifting"
    (mod / "About").mkdir(parents=True)
    (mod / "About" / "About.xml").write_text(
        "<ModMetaData><packageId>Example.Shift</packageId><name>Shift</name></ModMetaData>",
        encoding="utf-8",
    )
    (mod / "Patches").mkdir()
    patch = mod / "Patches" / "P.xml"
    body = (
        '<?xml version="1.0" encoding="utf-8"?>\n<Patch>\n{pad}'
        '  <Operation Class="PatchOperationAdd">\n'
        '    <xpath>Defs/StatDef[defName="Nope"]</xpath>\n'
        "    <value><a>1</a></value>\n  </Operation>\n</Patch>\n"
    )
    patch.write_text(body.format(pad=""), encoding="utf-8")

    record = tmp_path / "base.json"
    invoke("check", "--mods", str(mod), "--write-baseline", str(record))
    assert invoke("check", "--mods", str(mod), "--baseline", str(record)).exit_code == 0

    patch.write_text(body.format(pad="  <!-- a new comment -->\n"), encoding="utf-8")
    shifted = invoke("check", "--mods", str(mod), "--baseline", str(record))
    assert shifted.exit_code == 0, "a moved line must stay baselined"


def test_missing_baseline_file_explains_how_to_make_one(fixtures, tmp_path):
    result = invoke(
        "check", "--mods", str(fixtures / "patcher"), "--baseline", str(tmp_path / "nope.json")
    )
    assert result.exit_code == 2
    assert "--write-baseline" in result.output


def test_a_file_that_is_not_a_baseline_is_rejected(fixtures, tmp_path):
    junk = tmp_path / "junk.json"
    junk.write_text('{"hello": "world"}', encoding="utf-8")
    result = invoke("check", "--mods", str(fixtures / "patcher"), "--baseline", str(junk))
    assert result.exit_code == 2
    assert "not a rimpatch baseline" in result.output


def test_malformed_json_is_rejected(fixtures, tmp_path):
    junk = tmp_path / "junk.json"
    junk.write_text("{not json", encoding="utf-8")
    result = invoke("check", "--mods", str(fixtures / "patcher"), "--baseline", str(junk))
    assert result.exit_code == 2
    assert "could not read baseline" in result.output


def test_baseline_file_is_readable_and_stable(fixtures, tmp_path):
    record = tmp_path / "base.json"
    invoke("check", "--mods", str(fixtures / "patcher"), "--write-baseline", str(record))
    payload = json.loads(record.read_text(encoding="utf-8"))
    assert payload["format"] == baseline.FORMAT
    entries = payload["findings"]
    assert len(entries) == 2
    assert {entry["class"] for entry in entries} == {
        "PatchOperationAdd",
        "PatchOperationReplace",
    }
    assert all("line" not in entry for entry in entries), "line numbers would be fragile"

    # Regenerating produces the same bytes.
    first = record.read_bytes()
    invoke("check", "--mods", str(fixtures / "patcher"), "--write-baseline", str(record))
    assert record.read_bytes() == first


def test_no_game_suppresses_the_vanilla_hint(fixtures):
    with_hint = invoke("check", "--mods", str(fixtures / "sequence"))
    assert "No vanilla defs were loaded" in with_hint.output

    asked_for_it = invoke("check", "--no-game", "--mods", str(fixtures / "sequence"))
    assert "No vanilla defs were loaded" not in asked_for_it.output, (
        "telling someone to pass --no-game when they just did is noise"
    )
