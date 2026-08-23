"""The semantics that decide whether a report is trustworthy or noise."""

from __future__ import annotations

import pytest


def test_patch_resolves_when_its_target_is_loaded(run):
    report = run("base", "patcher")
    assert report.findings == []
    assert report.ok
    assert report.operations_checked == 2


def test_patch_misses_when_its_target_is_absent(run):
    report = run("patcher")
    assert len(report.findings) == 2

    first = report.findings[0]
    assert first.kind == "no-match"
    assert first.rel_path == "Patches/Stats.xml"
    assert first.line == 6
    assert first.op_class == "PatchOperationAdd"
    assert first.xpath == 'Defs/StatDef[defName="Flammability"]'
    assert first.message == "matched 0 nodes"
    assert first.mod == "Example.Patcher"

    assert first.diagnosis is not None
    assert first.diagnosis.prefix == "Defs"
    assert first.diagnosis.matched == 1
    assert (
        first.diagnosis.line()
        == 'deepest match: Defs (1 node) - no StatDef with defName="Flammability" '
        "among active mods"
    )


def test_sequence_aborts_and_reports_the_children_it_skipped(run):
    report = run("base", "sequence")
    assert len(report.findings) == 1

    finding = report.findings[0]
    assert finding.line == 11, "the failing child, not the sequence"
    assert finding.xpath == 'Defs/StatDef[defName="NoSuchStat"]'
    assert finding.chain == "PatchOperationSequence > PatchOperationAdd"
    assert finding.skipped == (("PatchOperationAdd", 17),)


def test_findmod_nomatch_branch_is_not_a_finding(run):
    report = run("base", "findmod")
    assert report.findings == []
    assert report.operations_checked == 2


def test_conditional_missing_its_own_xpath_is_not_a_finding(run):
    report = run("base", "conditional")
    assert report.findings == []


def test_success_always_is_suppressed_by_default_and_shown_by_strict(run):
    assert run("base", "always").findings == []

    report = run("base", "always", strict=True)
    assert len(report.findings) == 1
    assert report.findings[0].suppressed_by == "success=Always"
    assert report.findings[0].line == 3


def test_may_require_gates_defs_and_operations_before_any_xpath_runs(run):
    report = run("base", "gated")
    assert report.findings == []
    # The gated def and the gated operation are both dropped; only the
    # MayRequireAnyOf def and the operation targeting it survive.
    assert report.operations_checked == 1
    assert report.gated_nodes == 2


def test_load_folders_gate_content_on_active_mods(run):
    report = run("base", "loadfolders")
    assert report.findings == []
    # Root and WithBase load; WithMissing is gated out by IfModActive.
    assert report.operations_checked == 2


@pytest.mark.parametrize(
    "op_class",
    [
        "PatchOperationInsert",
        "PatchOperationRemove",
        "PatchOperationAttributeAdd",
        "PatchOperationAttributeSet",
        "PatchOperationAttributeRemove",
        "PatchOperationAddModExtension",
        "PatchOperationSetName",
        "PatchOperationTest",
    ],
)
def test_every_operation_class_resolves_against_a_real_def(run, op_class):
    report = run("base", "ops")
    failed = [finding.op_class for finding in report.findings]
    assert op_class not in failed
    assert report.findings == []


def test_duplicate_defname_across_mods_is_a_warning_not_a_finding(run):
    report = run("base", "dupe")
    assert report.findings == []
    duplicates = [w for w in report.warnings if w.kind == "duplicate-defname"]
    assert len(duplicates) == 1
    assert 'StatDef "Flammability"' in duplicates[0].message


def test_mod_with_no_patches_folder_is_clean(run):
    report = run("empty")
    assert report.ok
    assert report.operations_checked == 0
