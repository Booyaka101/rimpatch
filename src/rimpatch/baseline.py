"""Accept the breakage a mod already has, so CI can catch the breakage it adds next.

A mod with a dozen stale patches cannot turn this on without going red on day one, and
a permanently red check gets deleted rather than fixed. A baseline freezes what is
already broken and lets everything new through to the report.
"""

from __future__ import annotations

import json
from pathlib import Path

from .engine import Finding
from .errors import RimpatchError

#: Bumped if the fingerprint scheme ever changes.
FORMAT = 1


def fingerprint(finding: Finding) -> str:
    """Identify a finding across edits.

    Deliberately excludes the line number: adding a comment at the top of a patch file
    should not silently un-baseline everything below it.
    """
    return "|".join(
        (finding.kind, finding.mod, finding.rel_path, finding.op_class, finding.xpath)
    )


def _entry(finding: Finding) -> dict:
    return {
        "kind": finding.kind,
        "mod": finding.mod,
        "file": finding.rel_path,
        "class": finding.op_class,
        "xpath": finding.xpath,
        "message": finding.message,
        "fingerprint": fingerprint(finding),
    }


def write(path: Path, findings: list[Finding]) -> int:
    """Record these findings as accepted. Returns how many were written."""
    entries = sorted(
        ({fingerprint(finding): _entry(finding) for finding in findings}).values(),
        key=lambda entry: entry["fingerprint"],
    )
    payload = {
        "format": FORMAT,
        "note": (
            "Findings accepted by rimpatch. Delete a line once you have fixed it, or "
            "regenerate with --write-baseline."
        ),
        "findings": entries,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise RimpatchError(f"could not write baseline {path}: {exc}") from exc
    return len(entries)


def load(path: Path) -> set[str]:
    """Fingerprints accepted by the baseline file."""
    if not path.exists():
        raise RimpatchError(
            f"baseline not found: {path}. Create it with --write-baseline {path}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RimpatchError(f"could not read baseline {path}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("findings"), list):
        raise RimpatchError(
            f"{path} is not a rimpatch baseline. Regenerate it with --write-baseline."
        )
    known = set()
    for entry in payload["findings"]:
        if isinstance(entry, dict) and entry.get("fingerprint"):
            known.add(str(entry["fingerprint"]))
    return known


def apply(findings: list[Finding], known: set[str]) -> tuple[list[Finding], list[Finding], int]:
    """Split findings into (still reported, accepted) and count baseline entries now unused."""
    reported: list[Finding] = []
    accepted: list[Finding] = []
    matched: set[str] = set()
    for finding in findings:
        mark = fingerprint(finding)
        if mark in known:
            matched.add(mark)
            accepted.append(finding)
        else:
            reported.append(finding)
    return reported, accepted, len(known - matched)


__all__ = ["FORMAT", "apply", "fingerprint", "load", "write"]
