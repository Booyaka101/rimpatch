"""Render a Report as text, JSON or GitHub Actions annotations."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .engine import Finding, Report
from .xmlutil import display_path

FORMATS = ("text", "json", "github")


def render(
    report: Report,
    fmt: str,
    *,
    show_warnings: bool = True,
    color: bool = False,
    show_hint: bool = True,
) -> str:
    if fmt == "json":
        return _json(report, show_warnings=show_warnings)
    if fmt == "github":
        return _github(report, show_warnings=show_warnings, show_hint=show_hint)
    return _text(report, show_warnings=show_warnings, color=color, show_hint=show_hint)


#: A single aborted sequence can skip dozens of children; the full list stays in JSON.
SKIPPED_SHOWN = 5


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _skipped_line(skipped: tuple[tuple[str, int], ...]) -> str:
    shown = ", ".join(f"{name} (line {line})" for name, line in skipped[:SKIPPED_SHOWN])
    if len(skipped) > SKIPPED_SHOWN:
        shown += f", and {len(skipped) - SKIPPED_SHOWN} more"
    return f"skipped as a result: {shown}"


def _text(report: Report, *, show_warnings: bool, color: bool, show_hint: bool = True) -> str:
    bold = "\033[1m" if color else ""
    red = "\033[31m" if color else ""
    yellow = "\033[33m" if color else ""
    dim = "\033[2m" if color else ""
    off = "\033[0m" if color else ""

    lines: list[str] = []
    for finding in report.findings:
        lines.append(
            f"{bold}{finding.rel_path}:{finding.line}{off}  "
            f"{red}{finding.op_class}{off}  {finding.message}"
        )
        if finding.xpath:
            lines.append(f"  xpath: {finding.xpath}")
        if finding.diagnosis is not None:
            lines.append(f"  {finding.diagnosis.line()}")
            if finding.diagnosis.suggestions:
                lines.append(f"  did you mean: {', '.join(finding.diagnosis.suggestions)}")
        if finding.chain:
            lines.append(f"  in: {finding.chain}")
        if finding.skipped:
            lines.append("  " + _skipped_line(finding.skipped))
        if finding.suppressed_by:
            lines.append(f"  {dim}suppressed by {finding.suppressed_by}, shown by --strict{off}")
        lines.append(f"  mod: {finding.mod}")
        lines.append("")

    if show_warnings and report.warnings:
        for warning in report.warnings:
            lines.append(
                f"{yellow}warning{off} {warning.rel_path}:{warning.line}  {warning.message}"
            )
            for related in warning.related:
                if related:
                    lines.append(f"  also: {related}")
            lines.append(f"  mod: {warning.mod}")
            lines.append("")

    lines.append(_summary(report, show_warnings=show_warnings, show_hint=show_hint))
    return "\n".join(lines)


def _summary(report: Report, *, show_warnings: bool, show_hint: bool = True) -> str:
    checked = _plural(report.operations_checked, "operation")
    if not report.findings:
        summary = f"0 findings ({checked} checked)"
    else:
        summary = (
            f"{_plural(len(report.findings), 'finding')} in "
            f"{_plural(report.files_with_findings, 'file')} "
            f"({checked} checked, {report.elapsed:.1f}s)"
        )
    extras = []
    if show_warnings and report.warnings:
        extras.append(_plural(len(report.warnings), "warning"))
    if report.unknown_classes:
        total = sum(report.unknown_classes.values())
        extras.append(
            f"{_plural(total, 'operation')} from mod assemblies not evaluated"
        )
    if report.baselined:
        extras.append(f"{len(report.baselined)} accepted by the baseline")
    if report.stale_baseline:
        count = report.stale_baseline
        noun = "baseline entry" if count == 1 else "baseline entries"
        extras.append(f"{count} {noun} no longer needed")
    if report.missing_mods:
        extras.append(f"{_plural(len(report.missing_mods), 'active mod')} not found on disk")
    if extras:
        summary += ", " + ", ".join(extras)
    hint = _hint(report) if show_hint else ""
    return summary + hint if hint else summary


def _hint(report: Report) -> str:
    """Explain findings that are an artifact of the load order rather than a mod bug."""
    unresolved = [finding for finding in report.findings if finding.kind == "no-match"]
    if not unresolved:
        return ""
    if not report.vanilla_loaded:
        return (
            "\n\nNo vanilla defs were loaded, so every patch targeting Core reports as"
            " unresolved.\nPass --game <RimWorld install>, or --no-game to silence this."
        )
    # A mod missing a declared dependency patches a tree without whatever that dependency
    # adds, so its findings say more about the load order than about the mod.
    starved = sorted({finding.mod for finding in unresolved} & set(report.starved_mods))
    if not starved:
        return ""
    affected = sum(1 for finding in unresolved if finding.mod in set(starved))
    return (
        f"\n\n{_plural(affected, 'finding')} come from "
        + ", ".join(starved[:3])
        + ("..." if len(starved) > 3 else "")
        + ", which declare a dependency that is not loaded.\nAdd the dependency, or"
        " exclude the mod, before treating those as real."
    )


def _escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _annotation(finding: Finding, level: str) -> str:
    parts = [finding.message]
    if finding.xpath:
        parts.append(f"xpath: {finding.xpath}")
    if finding.diagnosis is not None:
        parts.append(finding.diagnosis.line())
        if finding.diagnosis.suggestions:
            parts.append(f"did you mean: {', '.join(finding.diagnosis.suggestions)}")
    if finding.skipped:
        parts.append(_skipped_line(finding.skipped))
    parts.append(f"mod: {finding.mod}")
    body = _escape("\n".join(parts))
    line = max(finding.line, 1)
    return (
        f"::{level} file={display_path(finding.path, Path.cwd())},line={line},"
        f"title={finding.op_class}::{body}"
    )


def _github(report: Report, *, show_warnings: bool, show_hint: bool = True) -> str:
    lines = [_annotation(finding, "error") for finding in report.findings]
    if show_warnings:
        lines.extend(_annotation(warning, "warning") for warning in report.warnings)
    lines.append(_summary(report, show_warnings=show_warnings, show_hint=show_hint))
    return "\n".join(lines)


def _finding_json(finding: Finding) -> dict:
    payload = {
        "kind": finding.kind,
        "severity": finding.severity,
        "file": finding.rel_path,
        "absolutePath": str(finding.path),
        "line": finding.line,
        "mod": finding.mod,
        "class": finding.op_class,
        "message": finding.message,
    }
    if finding.xpath:
        payload["xpath"] = finding.xpath
    if finding.chain:
        payload["chain"] = finding.chain
    if finding.diagnosis is not None:
        payload["diagnosis"] = {
            "deepestMatch": finding.diagnosis.prefix,
            "matched": finding.diagnosis.matched,
            "failingStep": finding.diagnosis.failing_step,
            "explanation": finding.diagnosis.explanation,
            "suggestions": list(finding.diagnosis.suggestions),
        }
    if finding.skipped:
        payload["skipped"] = [
            {"class": name, "line": line} for name, line in finding.skipped
        ]
    if finding.suppressed_by:
        payload["suppressedBy"] = finding.suppressed_by
    if finding.related:
        payload["related"] = [item for item in finding.related if item]
    return payload


def _json(report: Report, *, show_warnings: bool) -> str:
    payload = {
        "findings": [_finding_json(finding) for finding in report.findings],
        "warnings": (
            [_finding_json(warning) for warning in report.warnings] if show_warnings else []
        ),
        "summary": {
            "findings": len(report.findings),
            "filesWithFindings": report.files_with_findings,
            "operationsChecked": report.operations_checked,
            "operationsEvaluated": report.operations_evaluated,
            "patchFiles": report.patch_files,
            "defFiles": report.def_files,
            "defsLoaded": report.defs_loaded,
            "nodesGatedByMayRequire": report.gated_nodes,
            "elapsedSeconds": round(report.elapsed, 3),
            "mods": report.mods,
            "baselined": len(report.baselined),
            "staleBaselineEntries": report.stale_baseline,
            "missingMods": report.missing_mods,
            "starvedMods": report.starved_mods,
            "vanillaLoaded": report.vanilla_loaded,
            "unevaluatedClasses": report.unknown_classes,
        },
    }
    return json.dumps(payload, indent=2)


def wants_color(fmt: str, stream_isatty: bool) -> bool:
    if fmt != "text" or not stream_isatty:
        return False
    if os.environ.get("NO_COLOR"):
        return False
    return True


__all__ = ["FORMATS", "render", "wants_color"]
