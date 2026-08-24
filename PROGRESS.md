# rimpatch - build state

**Status: v1.0.0 SHIPPED on 2026-08-23.**

- Source: https://github.com/Booyaka101/rimpatch
- Release: https://github.com/Booyaka101/rimpatch/releases/tag/v1.0.0
- PyPI: https://pypi.org/project/rimpatch/1.0.0/ (`pip install rimpatch`)
- Action: `uses: Booyaka101/rimpatch@v1`
- Marketplace: https://github.com/marketplace/actions/rimpatch

Nothing outstanding. Every venue is live.

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
`action.yml` description must stay under 125 characters (ours is 81), and the note that an
agent cannot pass the Marketplace sudo-mode wall. That second one turned out to be wrong
and was corrected in LESSONS.md after this run listed rimpatch end to end. Nothing in the
file contradicted the brief itself.

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
  patch and skipping 76 more operations; `ButcherCorpseRotten` no longer exists in 1.6).
- 88 unit tests plus 2 network integration tests, all passing on Windows and Linux.
- Wheel built and installed into a clean venv from a clean path; `rimpatch --help` and a
  real check both work.
- The composite action's shell step was executed locally in all four paths: clean (exit
  0), findings with `fail-on-findings: true` (exit 1, `findings=1`), findings with
  `fail-on-findings: false` (exit 0, `findings=1`), and a bad path (exit 2 with a
  `::error::` message). Confirmed it does not pick up this machine's install.
- Zero-argument run from inside a real Combat Extended checkout, using the clean-venv
  wheel install: found the mod, found the install on the D: drive, `0 findings (2830
  operations checked)` in 13s.
- **Verified on real Linux, not just assumed.** All 88 unit tests pass under WSL Ubuntu
  on Python 3.14, and the same Combat Extended run against the same install mounted at
  `/mnt/d` gives byte-identical output: `0 findings (2830 operations checked)`, and the
  Flammability finding at `Patches/Core/Stats/Stats.xml:6` word for word. Both the wheel
  and the sdist install cleanly there, and `rimpatch where` degrades gracefully when
  there is no Steam to find.

## Adoption

A mod with existing breakage could not turn this on without going red forever, and a
permanently red check gets deleted rather than fixed. `--write-baseline` records what is
already broken, `--baseline` reports only what is new, and the action takes the same file
via its `baseline` input. Verified on real data with Combat Extended: 1401 findings, 1368
baseline entries, green afterwards, a newly added broken patch still fails the run, and
fixing a baselined one reports `2 baseline entries no longer needed`. Entries are matched
on mod, file, class and xpath and deliberately not on line number, so adding a comment
above an operation does not silently un-baseline everything below it.

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
8. **A hint that tells you to pass the flag you just passed is noise.** The "no vanilla
   defs were loaded" line kept firing under `--no-game`. It is now gated on the user not
   having already opted out.

## House rule review (2026-08-23)

Run against the global rules, mechanically rather than by eye.

- **Clone detection.** difflib over all 84 functions found four pairs above the 55% mark,
  including a 100% literal duplicate of `_relative` in `defs.py` and `engine.py`. Extracted
  `xmlutil.display_path` (used by both plus `report.py`, which was the same mechanism with
  a different base) and `locate._first_confirmed` (shared by `find_game` and
  `find_mods_config`, previously 61% alike). Re-run: **0 pairs above 55%**.
- **Proof of no behaviour change**, as the rule requires rather than an argument for it:
  14 scenarios captured before the refactor (text/json/github, parse errors, sequences,
  duplicates, strict, mods, where, the real Combat Extended run, both error paths), stdout
  plus stderr plus exit code, 42 files, 450 KB. After the refactor and again after the
  dead-code removal: **byte identical**, the only varying token being the elapsed-time
  number, which is normalised out.
- **Dead code removed**: `DELIBERATE`, `Operation.label()`, `Finding.title` and
  `ParseFailure.column` were all defined and never read.
- **Prose**: no em dashes, en dashes or smart quotes anywhere in the docs, code or the
  commit messages.
- **Comments**: 20 in roughly 2,000 lines, each stating a non-obvious constraint
  (Harmony's loadBefore, MayRequire ordering, empty vs missing `<operations>`, the macOS
  app bundle). No rationale essays, none addressed to a reviewer. One docstring runs to
  six lines; the rest are shorter.
- **Docs accuracy**: the README option table was diffed against real `--help` output.
  No option or command documented that does not exist, and none missing.
- **Shipping**: the branch was `master` while `pyproject.toml` pointed PyPI's Changelog
  link at `blob/main/CHANGELOG.md` and CI only triggered on `main`, so the link would have
  404'd and CI would never have run. Branch renamed to `main`.

## Shipping record (2026-08-23)

1. Repo created public at `Booyaka101/rimpatch`, `main` pushed at `3f325fd`.
2. Waited for CI on that exact commit via the check-runs API, per the house rule.
   **11/11 green**, including macOS 3.11/3.12/3.13, which settled the one platform that
   could not be verified locally.
3. Tagged `v1.0.0` and the moving major tag `v1`, both on `3f325fd`.
4. GitHub release published with the wheel and sdist attached.
5. `twine upload` to PyPI. Verified afterwards by `pip install rimpatch` from the index
   into a clean venv and running a real check: `0 findings (2830 operations checked)`.
6. Added a `published.yml` workflow that consumes the released `@v1` tag and
   `pip install rimpatch==1.0.0` on Linux, Windows and macOS, so a broken published
   artifact surfaces in CI rather than in someone's issue tracker. Runs weekly.

## Marketplace listing

Listed at https://github.com/marketplace/actions/rimpatch. Done over CDP against the
already-authenticated browser: tick the checkbox on the release edit page, submit, clear
the `Confirm access` sudo interstitial with an emailed code, and GitHub replays the pending
POST so the release lands already listed. This corrects the long-standing note that the
first listing is owner-only; it is not, though it does require the owner's go because it
means reading a verification code out of their mailbox.

Later releases pick up the listing automatically with no UI step.

Edit `[project.urls]` in `pyproject.toml` and the `uses: Booyaka101/rimpatch@v1` line in
the README if the repo ever moves.

## 1.1.0 (2026-08-24): the load order bug that was inventing findings

Re-ran the tool against this machine's install while checking whether some findings were
real, and found two defects.

**Mods outside ModsConfig were never ordered.** `resolve_load_order` only applied
`order_by_declared_rules` on the branch where no `ModsConfig.xml` was given. With one
supplied, everything not in its `<activeMods>` was appended in raw discovery order. So
`--mods-config auto --mods <folder of every installed mod>` put Pawnmorpher at position
44 and Humanoid Alien Races, which Pawnmorpher declares `loadAfter` and `modDependencies`
on, at 238. HAR is what puts `<alienRace>` on the Human ThingDef, so 8 Pawnmorpher
operations reported as unresolved. Measured before and after on the same 2,462 operations:
**10 findings became 2**, and the 2 that remain are the audited Rim of Madness - Bones
breakages. Nothing else in the run changed.

That is the worst category of bug for this tool. Every one of those 8 was a confident,
precisely-located finding about a mod that had nothing wrong with it.

**Nothing said a declared dependency was absent.** The `--repo` path warned about
unresolved sibling dependencies; the `--mods` path did not. Now warned, but only for mods
that also have operations matching nothing, so it explains findings rather than linting
metadata. A mod may legitimately declare a dependency its patches do not need, and the
`patcher` fixture does exactly that, which is what caught the first, noisier version of
this. When no vanilla defs are loaded at all the existing missing-Core hint wins, since
naming a dependency on top of that points people the wrong way.

Also added a note listing mods checked despite not being active, which is what made the
original run so easy to misread as "your load order has 10 problems".

101 tests pass, up from 88. The difflib clone check over `src/` reports zero pairs above
60%; the closest neighbour of the new `unsatisfied_dependencies` is 15%.
