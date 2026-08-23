"""Bad input must produce a message, never a traceback."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from rimpatch.cli import main
from rimpatch.diagnose import split_steps
from rimpatch.operations import split_union, to_document_context


def test_malformed_def_file_is_reported_and_the_rest_still_load(run):
    report = run("broken")
    parse_errors = [f for f in report.findings if f.kind == "parse-error"]
    assert len(parse_errors) == 1
    assert parse_errors[0].rel_path == "Defs/Malformed.xml"
    assert parse_errors[0].line > 0
    # Good.xml in the same folder still loaded, so the patch targeting it resolves.
    assert report.defs_loaded == 1


def test_invalid_xpath_is_its_own_finding_kind(run):
    report = run("broken")
    bad = [f for f in report.findings if f.kind == "bad-xpath"]
    assert len(bad) == 1
    assert bad[0].xpath == 'Defs/StatDef[defName='
    assert "invalid xpath" in bad[0].message


def test_misspelled_builtin_class_is_reported_but_assembly_classes_are_not(run):
    report = run("broken")
    unknown = [f for f in report.findings if f.kind == "unknown-operation"]
    assert len(unknown) == 1
    assert unknown[0].op_class == "PatchOperationsequence"
    # A namespaced class comes from a mod assembly: counted, never reported.
    assert report.unknown_classes == {"SomeMod.PatchOperationCustomThing": 1}


def test_empty_operations_list_is_a_warning_not_a_finding(run, fixtures, tmp_path):
    mod = tmp_path / "emptyseq"
    (mod / "About").mkdir(parents=True)
    (mod / "About" / "About.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<ModMetaData><name>Empty Sequence</name>"
        "<packageId>Example.EmptySeq</packageId></ModMetaData>\n",
        encoding="utf-8",
    )
    (mod / "Patches").mkdir()
    (mod / "Patches" / "Empty.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<Patch>\n  <Operation Class=\"PatchOperationSequence\">\n"
        "    <operations>\n    </operations>\n  </Operation>\n</Patch>\n",
        encoding="utf-8",
    )
    result = CliRunner().invoke(main, ["check", "--mods", str(mod)])
    assert result.exit_code == 0
    assert "does nothing" in result.output


def test_missing_path_exits_two_with_a_message():
    result = CliRunner().invoke(main, ["check", "--mods", "no/such/folder"])
    assert result.exit_code == 2
    assert "does not exist" in result.output
    assert "Traceback" not in result.output


def test_folder_that_is_not_a_mod_exits_two(tmp_path):
    (tmp_path / "notamod").mkdir()
    result = CliRunner().invoke(main, ["check", "--mods", str(tmp_path / "notamod")])
    assert result.exit_code == 2
    assert "About/About.xml" in result.output


def test_game_path_without_data_exits_two(tmp_path):
    result = CliRunner().invoke(main, ["check", "--game", str(tmp_path)])
    assert result.exit_code == 2
    assert "no Data folder" in result.output


def test_no_input_at_all_exits_two():
    result = CliRunner().invoke(main, ["check"])
    assert result.exit_code == 2
    assert "nothing to check" in result.output


def test_repo_pointing_at_a_non_mod_exits_two(tmp_path):
    result = CliRunner().invoke(main, ["check", "--repo", str(tmp_path)])
    assert result.exit_code == 2
    assert "not a mod folder" in result.output


def test_unreadable_mods_config_exits_two(tmp_path, fixtures):
    bad = tmp_path / "ModsConfig.xml"
    bad.write_text("<ModsConfigData><activeMods>", encoding="utf-8")
    result = CliRunner().invoke(
        main,
        ["check", "--mods", str(fixtures / "base"), "--mods-config", str(bad)],
    )
    assert result.exit_code == 2
    assert "not valid XML" in result.output


@pytest.mark.parametrize(
    "expression,expected",
    [
        ('Defs/StatDef[defName="X"]', '/Defs/StatDef[defName="X"]'),
        ("/Defs/ThingDef", "/Defs/ThingDef"),
        ("*/ThingDef", "/*/ThingDef"),
        ("//ThingDef", "//ThingDef"),
        (".//li[@Class='X']", "//li[@Class='X']"),
        ("./Defs", "/Defs"),
        (".", "/"),
        ("Defs/A | Defs/B", "/Defs/A | /Defs/B"),
        ('Defs/A[x="a|b"]', '/Defs/A[x="a|b"]'),
    ],
)
def test_relative_xpaths_are_rewritten_to_document_context(expression, expected):
    assert to_document_context(expression) == expected


def test_union_split_ignores_separators_inside_brackets_and_quotes():
    assert split_union('a[b="x|y"]|c') == ['a[b="x|y"]', "c"]


def test_step_split_ignores_slashes_inside_predicates():
    steps = split_steps('/Defs/ThingDef[defName="a/b"]/statBases')
    assert [step for _, step in steps] == [
        "Defs",
        'ThingDef[defName="a/b"]',
        "statBases",
    ]
