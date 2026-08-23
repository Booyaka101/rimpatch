"""Run the real Combat Extended patch corpus through the engine.

Combat Extended is the largest published PatchOperation corpus there is, so it is the
honest test of "does this parse and evaluate everything real mods actually write".
Needs the network; run with `pytest -m integration`.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from lxml import etree

from rimpatch.defs import DefDatabase
from rimpatch.operations import BUILTIN, Context, parse_operation
from rimpatch.xmlutil import child_elements

pytestmark = pytest.mark.integration

REPO = "CombatExtended-Continued/CombatExtended"
BRANCH = "Development"
TREE = f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}?recursive=1"
RAW = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/"


def fetch(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "rimpatch-tests"})
    token = os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


@pytest.fixture(scope="module")
def patch_files() -> list[tuple[str, bytes]]:
    try:
        listing = json.loads(fetch(TREE))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        pytest.skip(f"GitHub unreachable: {exc}")
    if "tree" not in listing:
        pytest.skip(f"unexpected GitHub response: {listing.get('message')}")

    paths = [
        item["path"]
        for item in listing["tree"]
        if item["type"] == "blob"
        and item["path"].startswith("Patches/")
        and item["path"].endswith(".xml")
    ]
    assert paths, "Combat Extended should have patch files under Patches/"

    def get(path: str) -> tuple[str, bytes]:
        return path, fetch(RAW + urllib.parse.quote(path))

    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(get, paths))


def test_every_operation_parses_and_evaluates_without_raising(patch_files, tmp_path):
    root = etree.Element("Defs")
    database = DefDatabase(root=root, tree=etree.ElementTree(root))
    ctx = Context(tree=database.tree)

    operations = 0
    classes: set[str] = set()
    for path, blob in patch_files:
        document = etree.fromstring(blob)
        assert document.tag == "Patch", f"{path} root should be <Patch>"
        for node in child_elements(document):
            operation = parse_operation(node, Path(path), path)
            operations += 1
            classes.add(operation.class_name)
            outcome = operation.apply(ctx)
            assert outcome is not None

    assert operations > 500, f"expected a large corpus, evaluated {operations}"
    # The corpus must exercise the classes this tool exists to model.
    assert {"PatchOperationAdd", "PatchOperationReplace"} <= classes
    assert classes & set(BUILTIN), "no built-in operation classes seen"


def test_the_flammability_operation_is_still_the_first_one(patch_files):
    stats = dict(patch_files)["Patches/Core/Stats/Stats.xml"]
    document = etree.fromstring(stats)
    first = child_elements(document)[0]
    assert first.get("Class") == "PatchOperationAdd"
    assert first.sourceline == 6
    assert first.findtext("xpath").strip() == 'Defs/StatDef[defName="Flammability"]'
