"""The PatchOperation classes, evaluated against the assembled Def document.

Semantics follow the game: an operation's worker either succeeds or fails, the
<success> mode then decides what the game actually reports, and PatchOperationSequence
aborts at the first child whose *reported* result is failure.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from lxml import etree

from .xmlutil import child_elements, text_of


class Success(Enum):
    NORMAL = "Normal"
    ALWAYS = "Always"
    INVERT = "Invert"
    NEVER = "Never"

    @classmethod
    def parse(cls, raw: str) -> "Success":
        wanted = raw.strip().lower()
        for member in cls:
            if member.value.lower() == wanted:
                return member
        return cls.NORMAL


# Deliberate outcomes: the author asked for a result that does not depend on the xpath.
DELIBERATE = (Success.ALWAYS, Success.NEVER)


@dataclass
class Outcome:
    worker_ok: bool
    effective_ok: bool
    matched: int | None = None
    reason: str = ""
    error_kind: str | None = None
    failing: "Operation | None" = None
    skipped: tuple["Operation", ...] = ()
    evaluated: int = 1


class BadXPath(Exception):
    def __init__(self, expression: str, message: str) -> None:
        super().__init__(message)
        self.expression = expression
        self.message = message


def split_union(expression: str) -> list[str]:
    """Split an XPath on top-level '|', ignoring separators inside quotes or brackets."""
    branches = []
    depth = 0
    quote = ""
    current = []
    for char in expression:
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
            continue
        if char in "'\"":
            quote = char
            current.append(char)
            continue
        if char in "[(":
            depth += 1
        elif char in "])":
            depth -= 1
        if char == "|" and depth == 0:
            branches.append("".join(current))
            current = []
            continue
        current.append(char)
    branches.append("".join(current))
    return branches


def to_document_context(expression: str) -> str:
    """Rewrite an xpath so it evaluates from the document node, as XmlDocument does.

    lxml evaluates a relative path against the root *element*, so the near-universal
    `Defs/ThingDef[...]` would silently match nothing. About 40% of real-world patch
    xpaths are written that way.
    """
    rewritten = []
    for branch in split_union(expression):
        stripped = branch.strip()
        if not stripped:
            rewritten.append(branch)
            continue
        if stripped.startswith("/") or stripped.startswith("("):
            rewritten.append(stripped)
        elif stripped == ".":
            rewritten.append("/")
        elif stripped.startswith(".//"):
            rewritten.append(stripped[1:])
        elif stripped.startswith("./"):
            rewritten.append(stripped[1:])
        elif stripped.startswith(".."):
            rewritten.append(stripped)
        else:
            rewritten.append("/" + stripped)
    return " | ".join(rewritten)


@dataclass
class Context:
    """Everything an operation needs to run, plus the compiled-xpath cache."""

    tree: etree._ElementTree
    active_ids: frozenset[str] = frozenset()
    active_names: frozenset[str] = frozenset()
    _cache: dict[str, etree.XPath] = field(default_factory=dict, repr=False)
    evaluated: int = 0

    def select(self, expression: str) -> list:
        compiled = self._cache.get(expression)
        if compiled is None:
            try:
                compiled = etree.XPath(to_document_context(expression), smart_strings=False)
            except etree.XPathSyntaxError as exc:
                raise BadXPath(expression, str(exc)) from exc
            self._cache[expression] = compiled
        try:
            result = compiled(self.tree)
        except etree.XPathEvalError as exc:
            raise BadXPath(expression, str(exc)) from exc
        if isinstance(result, list):
            return result
        return [result] if result else []


@dataclass
class Operation:
    """One <Operation> or <li Class="..."> node."""

    class_name: str
    element: etree._Element
    path: Path
    rel_path: str
    line: int
    success: Success = Success.NORMAL
    outcome: Outcome | None = None
    parent: "Operation | None" = None

    #: xpath text, for the classes that have one
    xpath: str = ""
    #: a note worth surfacing that is not an error the game would report
    advisory: str = ""

    def label(self) -> str:
        return self.class_name

    def apply(self, ctx: Context) -> Outcome:
        ctx.evaluated += 1
        try:
            outcome = self._worker(ctx)
        except BadXPath as exc:
            outcome = Outcome(
                worker_ok=False,
                effective_ok=False,
                matched=None,
                reason=f"invalid xpath: {exc.message}",
                error_kind="bad-xpath",
                failing=None,
            )
            outcome.failing = self
            self.outcome = outcome
            return outcome

        if outcome.failing is None and not outcome.worker_ok:
            outcome.failing = self

        if self.success is Success.ALWAYS:
            outcome.effective_ok = True
        elif self.success is Success.NEVER:
            outcome.effective_ok = False
        elif self.success is Success.INVERT:
            outcome.effective_ok = not outcome.worker_ok
        else:
            outcome.effective_ok = outcome.worker_ok
        self.outcome = outcome
        return outcome

    def _worker(self, ctx: Context) -> Outcome:  # pragma: no cover - overridden
        raise NotImplementedError


class PathedOperation(Operation):
    def _select(self, ctx: Context) -> list:
        if not self.xpath:
            raise BadXPath("", "operation has no <xpath>")
        return ctx.select(self.xpath)

    def _no_match(self, matched: int = 0) -> Outcome:
        return Outcome(worker_ok=False, effective_ok=False, matched=matched, reason="matched 0 nodes")


def _value_children(element: etree._Element) -> list[etree._Element]:
    value = element.find("value")
    if value is None:
        return []
    return child_elements(value)


class OpAdd(PathedOperation):
    def _worker(self, ctx: Context) -> Outcome:
        nodes = self._select(ctx)
        if not nodes:
            return self._no_match()
        payload = _value_children(self.element)
        append = text_of(self.element.find("order")).lower() != "prepend"
        for node in nodes:
            if not isinstance(node, etree._Element):
                continue
            for index, child in enumerate(payload):
                clone = copy.deepcopy(child)
                if append:
                    node.append(clone)
                else:
                    node.insert(index, clone)
        return Outcome(worker_ok=True, effective_ok=True, matched=len(nodes))


class OpInsert(PathedOperation):
    def _worker(self, ctx: Context) -> Outcome:
        nodes = self._select(ctx)
        if not nodes:
            return self._no_match()
        payload = _value_children(self.element)
        after = text_of(self.element.find("order")).lower() == "append"
        for node in nodes:
            parent = node.getparent() if isinstance(node, etree._Element) else None
            if parent is None:
                continue
            position = parent.index(node) + (1 if after else 0)
            for offset, child in enumerate(payload):
                parent.insert(position + offset, copy.deepcopy(child))
        return Outcome(worker_ok=True, effective_ok=True, matched=len(nodes))


class OpRemove(PathedOperation):
    def _worker(self, ctx: Context) -> Outcome:
        nodes = self._select(ctx)
        if not nodes:
            return self._no_match()
        for node in nodes:
            parent = node.getparent() if isinstance(node, etree._Element) else None
            if parent is not None:
                parent.remove(node)
        return Outcome(worker_ok=True, effective_ok=True, matched=len(nodes))


class OpReplace(PathedOperation):
    def _worker(self, ctx: Context) -> Outcome:
        nodes = self._select(ctx)
        if not nodes:
            return self._no_match()
        payload = _value_children(self.element)
        for node in nodes:
            parent = node.getparent() if isinstance(node, etree._Element) else None
            if parent is None:
                continue
            position = parent.index(node)
            for offset, child in enumerate(payload):
                parent.insert(position + offset, copy.deepcopy(child))
            parent.remove(node)
        return Outcome(worker_ok=True, effective_ok=True, matched=len(nodes))


class _AttributeOperation(PathedOperation):
    @property
    def attribute(self) -> str:
        return text_of(self.element.find("attribute"))

    @property
    def attribute_value(self) -> str:
        value = self.element.find("value")
        return "" if value is None else (value.text or "")


class OpAttributeAdd(_AttributeOperation):
    def _worker(self, ctx: Context) -> Outcome:
        nodes = self._select(ctx)
        if not nodes:
            return self._no_match()
        name = self.attribute
        touched = 0
        for node in nodes:
            if isinstance(node, etree._Element) and node.get(name) is None:
                node.set(name, self.attribute_value)
                touched += 1
        if not touched:
            return Outcome(
                worker_ok=False,
                effective_ok=False,
                matched=len(nodes),
                reason=f"all {len(nodes)} matched node(s) already have the "
                f'"{name}" attribute',
            )
        return Outcome(worker_ok=True, effective_ok=True, matched=len(nodes))


class OpAttributeSet(_AttributeOperation):
    def _worker(self, ctx: Context) -> Outcome:
        nodes = self._select(ctx)
        if not nodes:
            return self._no_match()
        for node in nodes:
            if isinstance(node, etree._Element):
                node.set(self.attribute, self.attribute_value)
        return Outcome(worker_ok=True, effective_ok=True, matched=len(nodes))


class OpAttributeRemove(_AttributeOperation):
    def _worker(self, ctx: Context) -> Outcome:
        nodes = self._select(ctx)
        if not nodes:
            return self._no_match()
        name = self.attribute
        touched = 0
        for node in nodes:
            if isinstance(node, etree._Element) and node.get(name) is not None:
                del node.attrib[name]
                touched += 1
        if not touched:
            return Outcome(
                worker_ok=False,
                effective_ok=False,
                matched=len(nodes),
                reason=f'no matched node has the "{name}" attribute',
            )
        return Outcome(worker_ok=True, effective_ok=True, matched=len(nodes))


class OpAddModExtension(PathedOperation):
    def _worker(self, ctx: Context) -> Outcome:
        nodes = self._select(ctx)
        if not nodes:
            return self._no_match()
        payload = _value_children(self.element)
        for node in nodes:
            if not isinstance(node, etree._Element):
                continue
            holder = node.find("modExtensions")
            if holder is None:
                holder = etree.SubElement(node, "modExtensions")
            for child in payload:
                holder.append(copy.deepcopy(child))
        return Outcome(worker_ok=True, effective_ok=True, matched=len(nodes))


class OpSetName(PathedOperation):
    def _worker(self, ctx: Context) -> Outcome:
        nodes = self._select(ctx)
        if not nodes:
            return self._no_match()
        new_name = text_of(self.element.find("name"))
        if not new_name:
            return Outcome(
                worker_ok=False,
                effective_ok=False,
                matched=len(nodes),
                reason="operation has no <name>",
                error_kind="bad-operation",
            )
        for node in nodes:
            if isinstance(node, etree._Element):
                node.tag = new_name
        return Outcome(worker_ok=True, effective_ok=True, matched=len(nodes))


class OpTest(PathedOperation):
    """Reports success or failure without mutating anything."""

    def _worker(self, ctx: Context) -> Outcome:
        nodes = self._select(ctx)
        if not nodes:
            return self._no_match()
        return Outcome(worker_ok=True, effective_ok=True, matched=len(nodes))


class OpSequence(Operation):
    children: list[Operation] = ()

    def _worker(self, ctx: Context) -> Outcome:
        evaluated = 1
        for index, child in enumerate(self.children):
            result = child.apply(ctx)
            evaluated += result.evaluated
            if not result.effective_ok:
                return Outcome(
                    worker_ok=False,
                    effective_ok=False,
                    matched=None,
                    reason=f"aborted at operation {index + 1} of {len(self.children)}",
                    error_kind=result.error_kind,
                    failing=result.failing or child,
                    skipped=tuple(self.children[index + 1 :]),
                    evaluated=evaluated,
                )
        return Outcome(worker_ok=True, effective_ok=True, matched=None, evaluated=evaluated)


class _BranchingOperation(Operation):
    match: "Operation | None" = None
    nomatch: "Operation | None" = None

    def _run_branch(self, ctx: Context, branch: Operation | None, reason: str) -> Outcome:
        if branch is None:
            return Outcome(worker_ok=True, effective_ok=True, matched=None, reason=reason)
        result = branch.apply(ctx)
        return Outcome(
            worker_ok=result.effective_ok,
            effective_ok=result.effective_ok,
            matched=result.matched,
            reason=reason if result.effective_ok else result.reason,
            error_kind=result.error_kind,
            failing=result.failing,
            skipped=result.skipped,
            evaluated=1 + result.evaluated,
        )


class OpConditional(_BranchingOperation, PathedOperation):
    """Runs <match> or <nomatch>; its own xpath matching nothing is never a failure."""

    def _worker(self, ctx: Context) -> Outcome:
        nodes = self._select(ctx)
        if nodes:
            return self._run_branch(ctx, self.match, "xpath matched, ran <match>")
        return self._run_branch(ctx, self.nomatch, "xpath did not match, ran <nomatch>")


class OpFindMod(_BranchingOperation):
    """Runs <match> when one of the named mods is active, else <nomatch>."""

    mods: tuple[str, ...] = ()

    def _worker(self, ctx: Context) -> Outcome:
        found = [name for name in self.mods if self._is_active(ctx, name)]
        if found:
            return self._run_branch(ctx, self.match, f"{found[0]} is active, ran <match>")
        return self._run_branch(ctx, self.nomatch, "none of the named mods are active")

    @staticmethod
    def _is_active(ctx: Context, name: str) -> bool:
        wanted = name.strip().lower()
        return wanted in ctx.active_names or wanted in ctx.active_ids


class OpUnknown(Operation):
    """A Class rimpatch cannot evaluate."""

    from_assembly: bool = True

    def _worker(self, ctx: Context) -> Outcome:
        if self.from_assembly:
            return Outcome(
                worker_ok=True,
                effective_ok=True,
                matched=None,
                reason="provided by a mod assembly, not evaluated",
            )
        return Outcome(
            worker_ok=False,
            effective_ok=False,
            matched=None,
            reason=f'no PatchOperation class named "{self.class_name}"',
            error_kind="unknown-operation",
        )


class OpBroken(Operation):
    """A well-known Class that is missing something it needs."""

    problem: str = ""

    def _worker(self, ctx: Context) -> Outcome:
        return Outcome(
            worker_ok=False,
            effective_ok=False,
            matched=None,
            reason=self.problem,
            error_kind="bad-operation",
        )


BUILTIN: dict[str, type[Operation]] = {
    "PatchOperationAdd": OpAdd,
    "PatchOperationInsert": OpInsert,
    "PatchOperationRemove": OpRemove,
    "PatchOperationReplace": OpReplace,
    "PatchOperationAttributeAdd": OpAttributeAdd,
    "PatchOperationAttributeSet": OpAttributeSet,
    "PatchOperationAttributeRemove": OpAttributeRemove,
    "PatchOperationAddModExtension": OpAddModExtension,
    "PatchOperationSetName": OpSetName,
    "PatchOperationSequence": OpSequence,
    "PatchOperationTest": OpTest,
    "PatchOperationConditional": OpConditional,
    "PatchOperationFindMod": OpFindMod,
}

def parse_operation(
    element: etree._Element,
    path: Path,
    rel_path: str,
    parent: Operation | None = None,
) -> Operation:
    """Build an Operation from an <Operation>/<li>/<match>/<nomatch> node."""
    class_name = (element.get("Class") or "").strip()
    line = element.sourceline or 0
    success = Success.parse(text_of(element.find("success")))

    common = dict(
        class_name=class_name or "(no Class)",
        element=element,
        path=path,
        rel_path=rel_path,
        line=line,
        success=success,
        parent=parent,
    )

    if not class_name:
        operation = OpBroken(**common)
        operation.problem = 'operation node has no Class="..." attribute'
        return operation

    factory = BUILTIN.get(class_name)
    if factory is None:
        operation = OpUnknown(**common)
        # A bare PatchOperationXxx that is not one of the game's own is a typo the game
        # also fails to resolve; a namespaced name comes from a mod assembly.
        operation.from_assembly = "." in class_name or not class_name.startswith("PatchOperation")
        return operation

    operation = factory(**common)

    if isinstance(operation, PathedOperation):
        operation.xpath = text_of(element.find("xpath"))
        if not operation.xpath:
            broken = OpBroken(**common)
            broken.problem = f"{class_name} has no <xpath>"
            return broken

    if isinstance(operation, OpSequence):
        holder = element.find("operations")
        if holder is None:
            # The game hits a null list here and throws; an empty list is silent.
            broken = OpBroken(**common)
            broken.problem = "PatchOperationSequence has no <operations>"
            return broken
        operation.children = [
            parse_operation(child, path, rel_path, operation)
            for child in child_elements(holder)
        ]
        if not operation.children:
            operation.advisory = (
                "PatchOperationSequence has an empty <operations> list, so it does nothing"
            )

    if isinstance(operation, _BranchingOperation):
        operation.match = _branch(element, "match", path, rel_path, operation)
        operation.nomatch = _branch(element, "nomatch", path, rel_path, operation)

    if isinstance(operation, OpFindMod):
        holder = element.find("mods")
        names = [text_of(item) for item in child_elements(holder)] if holder is not None else []
        operation.mods = tuple(name for name in names if name)
        if not operation.mods:
            broken = OpBroken(**common)
            broken.problem = "PatchOperationFindMod has no <mods>"
            return broken

    return operation


def _branch(
    element: etree._Element,
    name: str,
    path: Path,
    rel_path: str,
    parent: Operation,
) -> Operation | None:
    node = element.find(name)
    if node is None:
        return None
    return parse_operation(node, path, rel_path, parent)


def describe_chain(operation: Operation) -> str:
    """`PatchOperationSequence > PatchOperationTest` for a nested failure."""
    parts = []
    current: Operation | None = operation
    while current is not None:
        parts.append(current.class_name)
        current = current.parent
    return " > ".join(reversed(parts))


__all__ = [
    "BUILTIN",
    "BadXPath",
    "Context",
    "Operation",
    "Outcome",
    "PathedOperation",
    "Success",
    "describe_chain",
    "parse_operation",
    "split_union",
    "to_document_context",
]
