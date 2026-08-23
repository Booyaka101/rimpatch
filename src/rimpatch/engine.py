"""Walk every mod's Patches folder in load order and collect what no longer resolves."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from .defs import DefDatabase, load_defs, xml_files
from .diagnose import Diagnosis, diagnose
from .discover import LoadOrder, Mod
from .operations import (
    Context,
    Operation,
    Outcome,
    Success,
    describe_chain,
    parse_operation,
)
from .xmlutil import (
    apply_may_require,
    child_elements,
    display_path,
    parse_failure,
    parse_file,
)

ERROR = "error"
WARNING = "warning"


@dataclass
class Finding:
    kind: str
    severity: str
    rel_path: str
    path: Path
    line: int
    mod: str
    op_class: str
    message: str
    xpath: str = ""
    chain: str = ""
    diagnosis: Diagnosis | None = None
    skipped: tuple[tuple[str, int], ...] = ()
    suppressed_by: str = ""
    related: tuple[str, ...] = ()


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)
    operations_checked: int = 0
    operations_evaluated: int = 0
    patch_files: int = 0
    def_files: int = 0
    defs_loaded: int = 0
    gated_nodes: int = 0
    unknown_classes: dict[str, int] = field(default_factory=dict)
    mods: list[str] = field(default_factory=list)
    missing_mods: list[str] = field(default_factory=list)
    baselined: list[Finding] = field(default_factory=list)
    stale_baseline: int = 0
    vanilla_loaded: bool = True
    elapsed: float = 0.0

    @property
    def files_with_findings(self) -> int:
        return len({finding.rel_path for finding in self.findings})

    @property
    def ok(self) -> bool:
        return not self.findings


def _skipped_pairs(operations) -> tuple[tuple[str, int], ...]:
    return tuple((op.class_name, op.line) for op in operations)


def check(
    order: LoadOrder,
    version: str,
    *,
    strict: bool = False,
    warnings: bool = True,
) -> Report:
    """Assemble the Def tree, run every operation against it, and report the failures."""
    started = time.perf_counter()
    active = order.active_ids
    database = load_defs(order.mods, active, version)

    report = Report(
        def_files=database.files_read,
        defs_loaded=database.def_count,
        gated_nodes=database.gated_nodes,
        mods=[mod.package_id for mod in order.mods],
        missing_mods=list(order.missing),
        vanilla_loaded=any(mod.official for mod in order.mods),
    )

    for mod, failure in database.parse_errors:
        report.findings.append(
            Finding(
                kind="parse-error",
                severity=ERROR,
                rel_path=display_path(failure.path, mod.path),
                path=failure.path,
                line=failure.line,
                mod=mod.package_id,
                op_class="XML",
                message=f"could not parse def file: {failure.message}",
            )
        )

    ctx = Context(
        tree=database.tree,
        active_ids=active,
        active_names=frozenset(mod.name.strip().lower() for mod in order.mods),
    )

    for mod in order.mods:
        folders = mod.content_folders(active, version)
        for _, path in xml_files(folders, "Patches"):
            report.patch_files += 1
            _check_patch_file(path, mod, ctx, database, report, strict=strict)

    report.operations_evaluated = ctx.evaluated
    if warnings:
        _add_warnings(order, database, report)
    report.elapsed = time.perf_counter() - started
    return report


def _check_patch_file(
    path: Path,
    mod: Mod,
    ctx: Context,
    database: DefDatabase,
    report: Report,
    *,
    strict: bool,
) -> None:
    rel_path = display_path(path, mod.path)
    try:
        root = parse_file(path)
    except etree.XMLSyntaxError as exc:
        failure = parse_failure(path, exc)
        report.findings.append(
            Finding(
                kind="parse-error",
                severity=ERROR,
                rel_path=rel_path,
                path=path,
                line=failure.line,
                mod=mod.package_id,
                op_class="XML",
                message=f"could not parse patch file: {failure.message}",
            )
        )
        return
    except OSError as exc:
        report.findings.append(
            Finding(
                kind="parse-error",
                severity=ERROR,
                rel_path=rel_path,
                path=path,
                line=0,
                mod=mod.package_id,
                op_class="XML",
                message=f"could not read patch file: {exc}",
            )
        )
        return

    gated = apply_may_require(root, ctx.active_ids)
    if gated < 0:
        return
    report.gated_nodes += gated

    if root.tag != "Patch":
        report.warnings.append(
            Finding(
                kind="patch-root",
                severity=WARNING,
                rel_path=rel_path,
                path=path,
                line=root.sourceline or 1,
                mod=mod.package_id,
                op_class=root.tag,
                message=f"patch file root is <{root.tag}>, the game expects <Patch>",
            )
        )

    for node in child_elements(root):
        operation = parse_operation(node, path, rel_path)
        report.operations_checked += 1
        outcome = operation.apply(ctx)
        _record(operation, outcome, mod, ctx, database, report, strict=strict)


def _record(
    operation: Operation,
    outcome: Outcome,
    mod: Mod,
    ctx: Context,
    database: DefDatabase,
    report: Report,
    *,
    strict: bool,
) -> None:
    failing = outcome.failing or operation
    _scan_tree(operation, mod, report)

    if outcome.effective_ok:
        # The author asked for this to pass regardless; only --strict cares.
        if strict and not outcome.worker_ok:
            report.findings.append(
                _finding(
                    operation, failing, outcome, mod, ctx, database,
                    suppressed_by=f"success={operation.success.value}",
                )
            )
        return

    if operation.success is Success.NEVER and not strict:
        return

    report.findings.append(_finding(operation, failing, outcome, mod, ctx, database))


def _scan_tree(operation: Operation, mod: Mod, report: Report) -> None:
    """Tally operations rimpatch cannot evaluate, and collect advisories."""
    from .operations import OpUnknown

    stack = [operation]
    while stack:
        current = stack.pop()
        if isinstance(current, OpUnknown) and current.from_assembly:
            report.unknown_classes[current.class_name] = (
                report.unknown_classes.get(current.class_name, 0) + 1
            )
        if current.advisory:
            report.warnings.append(
                Finding(
                    kind="dead-operation",
                    severity=WARNING,
                    rel_path=current.rel_path,
                    path=current.path,
                    line=current.line,
                    mod=mod.package_id,
                    op_class=current.class_name,
                    message=current.advisory,
                )
            )
        stack.extend(getattr(current, "children", ()) or ())
        for name in ("match", "nomatch"):
            branch = getattr(current, name, None)
            if branch is not None:
                stack.append(branch)


def _finding(
    operation: Operation,
    failing: Operation,
    outcome: Outcome,
    mod: Mod,
    ctx: Context,
    database: DefDatabase,
    *,
    suppressed_by: str = "",
) -> Finding:
    inner = failing.outcome or outcome
    kind = inner.error_kind or outcome.error_kind or "no-match"
    xpath = getattr(failing, "xpath", "") or ""
    message = inner.reason or outcome.reason or "failed"

    hint = None
    if kind == "no-match" and xpath:
        hint = diagnose(xpath, ctx, database)

    skipped = _skipped_pairs(outcome.skipped)
    if not skipped and failing is not operation:
        parent = failing.parent
        if parent is not None and parent.outcome is not None:
            skipped = _skipped_pairs(parent.outcome.skipped)

    return Finding(
        kind=kind,
        severity=ERROR,
        rel_path=failing.rel_path,
        path=failing.path,
        line=failing.line,
        mod=mod.package_id,
        op_class=failing.class_name,
        message=message,
        xpath=xpath,
        chain=describe_chain(failing) if failing.parent is not None else "",
        diagnosis=hint,
        skipped=skipped,
        suppressed_by=suppressed_by,
    )


def _add_warnings(order: LoadOrder, database: DefDatabase, report: Report) -> None:
    for duplicate in database.duplicates():
        # Ludeon's expansions deliberately override Core defs; nothing to act on there.
        if all(source.mod.official for source in duplicate.sources):
            continue
        first = duplicate.sources[0]
        others = ", ".join(
            f"{src.mod.package_id}:{src.rel_path}:{src.line}" for src in duplicate.sources[1:]
        )
        report.warnings.append(
            Finding(
                kind="duplicate-defname",
                severity=WARNING,
                rel_path=first.rel_path,
                path=first.path,
                line=first.line,
                mod=first.mod.package_id,
                op_class=duplicate.def_type,
                message=(
                    f'{duplicate.def_type} "{duplicate.def_name}" is defined '
                    f"{len(duplicate.sources)} times; the last one wins"
                ),
                related=(others,),
            )
        )

    for mod in order.mods:
        if mod.about_problem:
            report.warnings.append(
                Finding(
                    kind="mod-metadata",
                    severity=WARNING,
                    rel_path="About/About.xml",
                    path=mod.path / "About" / "About.xml",
                    line=1,
                    mod=mod.package_id,
                    op_class="About",
                    message=mod.about_problem,
                )
            )


__all__ = ["Finding", "Report", "check", "ERROR", "WARNING"]
