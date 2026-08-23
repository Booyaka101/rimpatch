"""Turn "matched 0 nodes" into "the StatDef you named is not there".

Walks the failing xpath one location step at a time and reports the deepest prefix that
still selects something, which is where the author's assumption stopped being true.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from .defs import DefDatabase
from .operations import BadXPath, Context, split_union

_PREDICATE = re.compile(r"""^\s*(@?[\w:.\-]+)\s*=\s*(['"])(.*?)\2\s*$""", re.S)
_STEP = re.compile(r"^([\w:.\-*@]+)(?:\[(.*)\])?$", re.S)


@dataclass(frozen=True)
class Diagnosis:
    prefix: str
    matched: int
    failing_step: str
    explanation: str
    suggestions: tuple[str, ...] = ()

    def line(self) -> str:
        node_word = "node" if self.matched == 1 else "nodes"
        head = self.prefix if self.prefix else "(document root)"
        return f"deepest match: {head} ({self.matched} {node_word}) - {self.explanation}"


def split_steps(expression: str) -> list[tuple[str, str]]:
    """[(separator, step)] where separator is "", "/" or "//"."""
    steps: list[tuple[str, str]] = []
    depth = 0
    quote = ""
    current: list[str] = []
    separator = ""
    index = 0
    while index < len(expression):
        char = expression[index]
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in "'\"":
            quote = char
            current.append(char)
            index += 1
            continue
        if char in "[(":
            depth += 1
        elif char in "])":
            depth -= 1
        if char == "/" and depth == 0:
            token = "".join(current).strip()
            if token or steps:
                steps.append((separator, token))
            separator = "//" if expression[index : index + 2] == "//" else "/"
            index += 2 if separator == "//" else 1
            current = []
            continue
        current.append(char)
        index += 1
    token = "".join(current).strip()
    if token:
        steps.append((separator, token))
    return [(sep, step) for sep, step in steps if step]


def _render(steps: list[tuple[str, str]]) -> str:
    out = []
    for index, (separator, step) in enumerate(steps):
        if index == 0:
            out.append(step if separator in ("", "/") else separator + step)
        else:
            out.append(separator + step)
    return "".join(out)


def _describe_step(step: str) -> str:
    match = _STEP.match(step)
    if match is None:
        return f"no node matching {step}"
    name, predicate = match.group(1), match.group(2)
    if name.startswith("@"):
        return f"no {name} attribute"
    if predicate:
        inner = _PREDICATE.match(predicate)
        if inner is not None:
            key, quote, value = inner.group(1), inner.group(2), inner.group(3)
            subject = "any element" if name == "*" else name
            return f"no {subject} with {key}={quote}{value}{quote}"
        subject = "element" if name == "*" else name
        return f"no {subject} matching [{predicate}]"
    if name == "*":
        return "no child element"
    return f"no <{name}> child"


def _step_parts(step: str) -> tuple[str, str, str]:
    """(element name, predicate key, predicate value) - empty strings when absent."""
    match = _STEP.match(step)
    if match is None:
        return "", "", ""
    name, predicate = match.group(1), match.group(2) or ""
    inner = _PREDICATE.match(predicate) if predicate else None
    if inner is None:
        return name, "", ""
    return name, inner.group(1), inner.group(3)


def diagnose(expression: str, ctx: Context, database: DefDatabase) -> Diagnosis | None:
    """Deepest prefix of `expression` that still matches, and why the next step does not."""
    branch = split_union(expression)[0].strip()
    steps = split_steps(branch)
    if not steps:
        return None

    best_prefix: list[tuple[str, str]] = []
    best_count = 0
    for index in range(len(steps)):
        candidate = steps[: index + 1]
        rendered = _render(candidate)
        try:
            matched = ctx.select(rendered)
        except BadXPath:
            break
        if not matched:
            break
        best_prefix = candidate
        best_count = len(matched)
    else:
        # Every step matched: the union as a whole failed for another reason.
        return None

    failing = steps[len(best_prefix)]
    explanation = _describe_step(failing[1])
    if len(best_prefix) <= 1:
        explanation += " among active mods"
    elif best_prefix:
        explanation += f" under {best_prefix[-1][1]}"

    return Diagnosis(
        prefix=_render(best_prefix),
        matched=best_count,
        failing_step=failing[1],
        explanation=explanation,
        suggestions=_suggest(failing[1], database),
    )


def _suggest(step: str, database: DefDatabase) -> tuple[str, ...]:
    """Near-miss defNames, which is what a renamed def looks like from the outside."""
    name, key, value = _step_parts(step)
    if key != "defName" or not value:
        return ()
    if name and name != "*":
        candidates = database.def_names(name)
        if not candidates:
            known = database.all_def_types()
            close = difflib.get_close_matches(name, known, n=3, cutoff=0.75)
            if close:
                return tuple(f"def type {other} exists" for other in close)
            return ()
    else:
        candidates = sorted(
            {source.def_name for source in database.sources.values() if source.def_name}
        )
    close = difflib.get_close_matches(value, candidates, n=3, cutoff=0.7)
    return tuple(close)


__all__ = ["Diagnosis", "diagnose", "split_steps"]
