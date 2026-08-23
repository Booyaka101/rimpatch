# rimpatch - build state

**Status: v1.0.0 complete and verified end to end. Nothing outstanding in the build.**
The only remaining steps are the owner's to take: publish to PyPI and list the action on
the GitHub Marketplace.

## Phase 0 verification (2026-08-23)

Every resource the brief depends on was fetched and confirmed before any code was
written. All live, all free, no paid API/account/hosting anywhere in the pipeline.

| Resource | Result |
| --- | --- |
| `raw.githubusercontent.com/.../Patches/Core/Stats/Stats.xml` | HTTP 200, 17,902 bytes. The `PatchOperationAdd` for `Defs/StatDef[defName="Flammability"]` really is on **line 6** |
| `api.github.com/.../contents/Patches/Core` | HTTP 200, exactly **31 directories**, all as listed in the brief |
| Zhentar gist `4a1b71cea45b9337f70b30a21d868782` | Live. All operation classes documented, including the wording "PatchOperationSequence will perform each operation in its list in sequence, aborting if an operation fails" |
| `pypi.org/pypi/rimworld/json` | Version 0.3.3, uploaded 2024-07-17, "heavily WIP", `lxml>=5.2.2`, library-only. Incumbent confirmed stale |
| `pypi.org/pypi/rimpatch/json` | **404 - the name is free** |
| `rimworldmodding.wiki.gg/wiki/XML_Software` | Lists only Notepad++, VSCode, Sublime and two generic XML plugins. No validator, schema or patch checker. Empty slot confirmed |
| `api.github.com/repos/RimSort/RimSort` | 1,227 stars, pushed 2026-08-21, 163 open issues. A mod *manager*, not a patch checker |
| Issue search, "Failed to find a node with the given xpath" | 24 issues. CombatExtended #4418/#4419/#4420 (D3nnis3n, 2026-01-05), Outland-Terrain #2 (AnirockGM, 2025-11-22, still open), Hauts-Framework #4 (KayAvalon, 2026-02-16) all confirmed |

`C:\Users\cbosc\claude-phone\ideas\LESSONS.md` was read. Two entries applied: the
`action.yml` description must stay under 125 characters (ours is 81), and an agent
cannot pass the Marketplace sudo-mode TOTP wall, so first listing is the owner's step.
Nothing in the file contradicts this brief. No new lesson was worth appending.

## What was built

`src/rimpatch/` - `__init__` (version), `errors`, `xmlutil` (parsing, MayRequire gating,
packageId normalisation), `locate` (finding the install and ModsConfig), `discover`
(About.xml, LoadFolders.xml, load order), `defs` (merged Def document), `operations` (all
operation classes), `engine` (walk and collect), `diagnose` (deepest-matching-prefix),
`report` (text/json/github), `cli`. Plus `action.yml`, `.github/workflows/ci.yml`,
`CHANGELOG.md`, `tests/` and `tests/make_fixtures.py`.

## Usable by anyone, not just by someone holding the manual

- **Zero-argument use.** `cd MyMod && rimpatch check` works: the current folder becomes
  the mod, and the RimWorld install is found automatically.
- **Install detection on all three platforms.** Steam's `libraryfolders.vdf` is parsed so
  a game on a second drive is found (this machine's is on `D:`, not under Program Files),
  plus the Windows registry, GOG and manual paths, macOS app bundles and Linux/flatpak
  and Proton prefixes. `RIMWORLD_DIR` overrides it.
- **`--mods-config auto`** finds the player's real active list and load order.
- **`rimpatch where`** prints what was found, and when nothing is, every path it tried
  plus the environment variable to set. That is the answer to "it can't find my game".
- **A guard against the one mistake that produces nonsense**: if no vanilla defs loaded
  and operations are missing, the summary says so and names `--game`.
- **`RIMPATCH_NO_AUTODETECT=1`** makes a run independent of what is installed. The test
  suite sets it via an autouse fixture, and the action and CI workflow set it, so results
  are reproducible. This was found the hard way: adding detection made six tests fail
  because they silently picked up the real install.

## Verified working

Measured on this machine against RimWorld 1.6.4871 rev590 at
`D:\SteamLibrary\steamapps\common\RimWorld` (Core + Royalty + Ideology + Biotech +
Anomaly + Odyssey, 237 local mods) and a sparse checkout of Combat Extended's
Development branch.

- **Combat Extended against the real install: `0 findings (2830 operations checked)`,
  exit 0.** Zero false positives across a large, actively maintained mod.
- **Combat Extended with no Core: 1401 findings in 96 files (1459 operations checked).**
  The first is the Flammability operation at `Patches/Core/Stats/Stats.xml:6`, matching
  the brief's expected block verbatim.
- **242-mod load order: 46,097 defs, 6,846 def files, 1,158 patch files, 2,462 top-level
  operations (4,709 including nested), ~58s, 3 findings.** Two were audited and are real
  bugs (Alpha Animals renamed `AA_PseudoBaseMechanoid`, breaking a Rim of Madness - Bones
  patch and skipping 75 more operations; `ButcherCorpseRotten` no longer exists in 1.6).
- 79 unit tests plus 2 network integration tests, all passing.
- Wheel built and installed into a clean venv from a clean path; `rimpatch --help` and a
  real check both work.
- The composite action's shell step was executed locally in all four paths: clean (exit
  0), findings with `fail-on-findings: true` (exit 1, `findings=1`), findings with
  `fail-on-findings: false` (exit 0, `findings=1`), and a bad path (exit 2 with a
  `::error::` message). Confirmed it does not pick up this machine's install.
- Zero-argument run from inside a real Combat Extended checkout, using the clean-venv
  wheel install: found the mod, found the install on the D: drive, `0 findings (2830
  operations checked)` in 13s.
- **Verified on real Linux, not just assumed.** All 79 unit tests pass under WSL Ubuntu
  on Python 3.14, and the same Combat Extended run against the same install mounted at
  `/mnt/d` gives byte-identical output: `0 findings (2830 operations checked)`, and the
  Flammability finding at `Patches/Core/Stats/Stats.xml:6` word for word. Both the wheel
  and the sdist install cleanly there, and `rimpatch where` degrades gracefully when
  there is no Steam to find.

## Things learned the hard way, worth not re-discovering

1. **lxml evaluates a relative XPath against the root element; .NET's
   `XmlDocument.SelectNodes` uses the document node.** So `Defs/StatDef[...]` returns
   nothing in lxml. A survey of 19,589 real xpaths in the local corpus found **40% are
   relative** (`Defs/...` or `*/...`). `operations.to_document_context` rewrites each
   union branch; without it the tool would report thousands of phantom findings.
2. **Patches run before def inheritance is resolved.** Abstract defs are still present
   and `ParentName` is unresolved when patches apply, which is why a patch cannot see an
   inherited field. Resolving inheritance first would hide real breakage.
3. **`LoadFolders.xml` is not optional.** Combat Extended keeps 100 files under
   `Patches/` and hundreds more under `ModPatches/`, loaded only via `IfModActive`.
   Ignoring it produces enormous false-positive counts. `IfModActive`/`IfModNotActive`
   are an OR; the `*All` variants (1.6) are an AND.
4. **Most `Class="..."` attributes in patch files are not operations.** Of 25,971 in the
   local corpus, the majority are `<li Class="CompProperties_X">` inside `<value>`. Only
   nodes in operation position are parsed as operations.
5. **Load order is the difference between a true and a false positive.** An early stress
   test reported 8 findings in Pawnmorpher that vanished once Humanoid Alien Races was
   ordered before it. Hence the declared-rule ordering in `discover.order_by_declared_rules`.
6. **Harmony declares `loadBefore` Core only.** Naively forcing all official content
   ahead of all mods creates a Core -> Anomaly -> Harmony -> Core cycle that stranded the
   entire graph. A mod declaring `loadBefore` any official mod is exempt from the
   synthetic rule, and cycles now force the earliest unplaced mod instead of giving up.
7. **An empty `<operations>` list is silent in-game**, a missing one throws. Only the
   second is a finding; the first is a warning.

## Left for the owner

Both are hard-walled to an agent and were not attempted, per LESSONS.md:

1. `python -m build && twine upload dist/*` to publish `rimpatch` 1.0.0 to PyPI. The
   name is free as of 2026-08-23. Artifacts are already built in `dist/`.
2. Push to GitHub and tick "Publish this Action to the GitHub Marketplace" on the v1.0.0
   release. That triggers sudo-mode TOTP, which an agent cannot pass. Later releases on
   an established listing pick up automatically.

Update `[project.urls]` in `pyproject.toml` and the `uses: Booyaka101/rimpatch@v1` line in
the README if the repo lands under a different owner or name.
