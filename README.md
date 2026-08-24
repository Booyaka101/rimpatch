# rimpatch

[![PyPI](https://img.shields.io/pypi/v/rimpatch)](https://pypi.org/project/rimpatch/)
[![Python](https://img.shields.io/pypi/pyversions/rimpatch)](https://pypi.org/project/rimpatch/)
[![CI](https://github.com/Booyaka101/rimpatch/actions/workflows/ci.yml/badge.svg)](https://github.com/Booyaka101/rimpatch/actions/workflows/ci.yml)
[![License](https://img.shields.io/pypi/l/rimpatch)](LICENSE)

Find RimWorld PatchOperations that no longer resolve, without launching the game.

RimWorld applies your `Patches/**/*.xml` to the combined Def tree at load time. When a
def you target gets renamed or moved, your `<Operation>` silently matches nothing and
the only signal is a line buried in the player's log:

    Failed to find a node with the given xpath: Defs/ThingDef[defName="Gun_Autopistol"]/statBases

You find out when a player opens an issue. rimpatch assembles the same Def tree the game
would assemble, runs every operation against it in load order, and tells you which ones
match zero nodes, with file, line, mod, class and xpath. No game launch, no C#, no
bundled game data.

## Install

```
pip install rimpatch
```

Python 3.11+. Pulls in `lxml` and `click`.

## Use it

Stand in your mod folder and run it. rimpatch treats the current folder as the mod and
finds your RimWorld install on its own, including Steam libraries on other drives:

```
$ cd MyMod
$ rimpatch check
rimpatch: note: checking the current folder as a mod: D:\Mods\MyMod
rimpatch: note: using the RimWorld install at D:\SteamLibrary\steamapps\common\RimWorld
0 findings (2830 operations checked)
```

Vanilla defs are read from that install. rimpatch never ships game data. If detection
guesses wrong or finds nothing, say where things are:

```
rimpatch check --game "C:/Program Files (x86)/Steam/steamapps/common/RimWorld" --mods ./MyMod
```

`rimpatch where` prints what it found, and when it finds nothing, every path it tried.

In CI, where the game is not installed, check the checkout against sibling checkouts of
the mods it declares in `About.xml`:

```
rimpatch check --repo .
```

Exit code is 0 when clean, 1 when there are findings, 2 when rimpatch itself could not
run (bad path, unreadable ModsConfig).

### Commands and options

| | |
| --- | --- |
| `rimpatch check` | Run the operations and report what misses |
| `rimpatch mods` | Print the resolved load order and each mod's content folders |
| `rimpatch where` | Show the install and `ModsConfig.xml` it can find |
| `--game PATH` | RimWorld install root. Found automatically if omitted |
| `--no-game` | Do not look for an install at all |
| `--mods PATH` | A mod folder, or a folder of mod folders. Repeatable, order is load order |
| `--repo PATH` | Check this checkout and resolve its `modDependencies` from sibling folders |
| `--mods-config PATH` | Take the active list and order from a `ModsConfig.xml`, or `auto` to find it |
| `--no-auto-order` | Use the order given instead of the mods' declared rules |
| `--game-version 1.6` | Version used for `LoadFolders` and version subfolders |
| `--format text\|json\|github` | Output format |
| `--strict` | Also report operations whose `<success>` mode hides the failure |
| `--no-warnings` | Hide warnings |
| `--exit-zero` | Always exit 0 |
| `--baseline FILE` | Accept the findings recorded in FILE, report only new ones |
| `--write-baseline FILE` | Record the current findings and exit 0 |

Environment: `RIMWORLD_DIR` and `RIMWORLD_CONFIG_DIR` point detection straight at an
install or a Config folder. `RIMPATCH_NO_AUTODETECT=1` turns detection off entirely, so
a run cannot depend on what happens to be installed. Set it in CI for reproducibility.

### The worked example

Combat Extended's `Patches/Core/Stats/Stats.xml` opens with an operation that expects
Core's `Flammability` StatDef. Run Combat Extended on its own, with no Core, and that
first operation has nothing to land on:

```
$ rimpatch check --mods ./CombatExtended
Patches/Core/Stats/Stats.xml:6  PatchOperationAdd  matched 0 nodes
  xpath: Defs/StatDef[defName="Flammability"]
  deepest match: Defs (1 node) - no StatDef with defName="Flammability" among active mods
  mod: CETeam.CombatExtended

... one of these for every Core def Combat Extended expects ...

1401 findings in 96 files (1459 operations checked, 4.3s), 52 operations from mod assemblies not evaluated
```

`deepest match` is the point where your assumption stopped being true. Here nothing
below `Defs` matched, so the StatDef itself is missing. Add the game and the same run is
clean:

```
$ rimpatch check --game "D:/SteamLibrary/steamapps/common/RimWorld" --mods ./CombatExtended
0 findings (2830 operations checked), 68 operations from mod assemblies not evaluated
$ echo $?
0
```

Those 2,830 operations are Combat Extended's real Patches tree against a real RimWorld
1.6 install with all five expansions, and every one of them resolves.

### What a real break looks like

From a 242-mod load order on a live install. Alpha Animals renamed a base def, so a
patch in Rim of Madness - Bones lands nowhere and takes 76 later operations with it,
because `PatchOperationSequence` stops at the first child that fails:

```
Patches/BonelessAlphaAnimals.xml:23  PatchOperationAdd  matched 0 nodes
  xpath: /Defs/ThingDef[@Name="AA_PseudoBaseMechanoid"]/statBases
  deepest match: Defs (1 node) - no ThingDef with @Name="AA_PseudoBaseMechanoid" among active mods
  in: PatchOperationFindMod > PatchOperationSequence > PatchOperationAdd
  skipped as a result: PatchOperationAdd (line 30), PatchOperationAdd (line 36), PatchOperationAdd (line 42), PatchOperationAdd (line 48), PatchOperationAdd (line 54), and 71 more
  mod: sihv.rombones
```

When a def looks renamed rather than gone, you get candidates:

```
Patches/ButcherRotten.xml:3  PatchOperationReplace  matched 0 nodes
  xpath: Defs/RecipeDef[defName="ButcherCorpseRotten"]/recipeUsers
  deepest match: Defs (1 node) - no RecipeDef with defName="ButcherCorpseRotten" among active mods
  did you mean: ButcherCorpseFlesh, ButcherCorpseMechanoid
  mod: sihv.rombones
```

## GitHub Action

`action.yml` at the repo root installs the package and runs `rimpatch check --format
github`, so findings land as inline annotations on the changed lines.

```yaml
name: Patches
on: [push, pull_request]

jobs:
  rimpatch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # Check out whatever your About.xml declares as a modDependency, next to your mod.
      - uses: actions/checkout@v4
        with:
          repository: CombatExtended-Continued/CombatExtended
          path: ../CombatExtended

      - uses: Booyaka101/rimpatch@v1
        with:
          repo: .
```

Inputs: `repo`, `mods` (one path per line), `game`, `mods-config`, `game-version`,
`baseline`, `strict`, `warnings`, `fail-on-findings`, `version`, `python-version`.
Outputs: `findings` (count) and `report` (path to the JSON report).

Without a RimWorld install on the runner, vanilla defs are absent, so operations
targeting Core will legitimately report as unresolved. Either check out the mods you
patch as siblings, or scope the action to a mod that only patches other mods.

## Adopting it on a mod that is already broken

A mod with a dozen stale patches would go red the day you add this, and a permanently
red check gets deleted rather than fixed. Record what is already broken and CI will only
fail on what you break next:

```
$ rimpatch check --write-baseline rimpatch-baseline.json
wrote 12 finding(s) to rimpatch-baseline.json. Commit it, then pass --baseline to report only what is new.

$ rimpatch check --baseline rimpatch-baseline.json
0 findings (412 operations checked), 12 accepted by the baseline
```

Commit the file. From then on a new break comes through on its own:

```
$ rimpatch check --baseline rimpatch-baseline.json
Patches/Guns.xml:14  PatchOperationAdd  matched 0 nodes
  xpath: Defs/ThingDef[defName="Gun_Autopistol"]/statBases
  ...
1 finding in 1 file (413 operations checked, 0.4s), 12 accepted by the baseline
```

Fix one and rimpatch tells you the entry is dead: `2 baseline entries no longer needed`.
Regenerate with `--write-baseline` to clear them. Entries are matched on mod, file,
class and xpath but deliberately **not** on line number, so adding a comment above an
operation does not silently un-baseline everything below it.

The action takes the same file via the `baseline` input.

## Getting the load order right

Which patches can resolve depends entirely on what loaded before them, so rimpatch takes
load order seriously.

- `--mods-config auto` is the exact answer: the active list and order the game itself
  will use, found for you. Pass a path instead if you keep it somewhere unusual.
  `rimpatch where` shows which one it picked.
- Otherwise official content loads first, then your mods are ordered by what they
  declare: `modDependencies`, `loadAfter`, `loadBefore` and the `force*` variants.
  Anything the mods do not constrain keeps the order you gave. `--no-auto-order` turns
  this off and uses your order verbatim.
- Mods you pass that are not in the `ModsConfig.xml` you gave are still checked, and are
  still ordered by those declared rules. They are listed in a note so it is clear they
  are not part of the active list.
- If a mod declares a `modDependencies` entry that is not loaded at all, and that mod has
  operations matching nothing, rimpatch says so. Those findings usually say more about
  the load order than about the mod.
- `rimpatch mods ...` prints the resolved order and each mod's content folders, which is
  the fastest way to see why something did or did not load.

## What it models

Every one of these is a place a naive checker would invent failures that the game never
reports:

| Behaviour | What rimpatch does |
| --- | --- |
| `PatchOperationSequence` | Runs children in order, stops at the first failure, reports that child and lists the ones skipped as a result |
| `PatchOperationTest` | Reports success or failure, mutates nothing |
| `PatchOperationConditional` | Its own xpath matching nothing is normal, not a finding; runs `<match>` or `<nomatch>` |
| `PatchOperationFindMod` | Taking the `<nomatch>` branch because the named mods are inactive is normal, not a finding |
| `<success>Always</success>` | A failure the author asked to ignore, suppressed unless `--strict` |
| `<success>Invert</success>` | Failure is the intended result, handled as the game does |
| `MayRequire` / `MayRequireAnyOf` | Gated nodes are dropped at load time, before any xpath runs, in both defs and patch files |
| `LoadFolders.xml` | `IfModActive` / `IfModNotActive` are an OR, `IfModActiveAll` / `IfModNotActiveAll` an AND |
| Def inheritance | Not resolved, because the game applies patches *before* resolving `ParentName`. A patch cannot see an inherited field, and rimpatch cannot either |
| Relative xpaths | `Defs/StatDef[...]` is evaluated from the document node, as `XmlDocument.SelectNodes` does. Roughly 40% of real-world patch xpaths are written this way |

All twelve operation classes are implemented: `Add`, `Insert`, `Remove`, `Replace`,
`AttributeAdd`, `AttributeSet`, `AttributeRemove`, `AddModExtension`, `SetName`,
`Sequence`, `Test`, `Conditional`, plus `FindMod`.

## Findings and warnings

Findings set the exit code. Kinds: `no-match`, `bad-xpath` (the xpath does not parse),
`bad-operation` (a class is missing something it needs), `unknown-operation` (a
misspelled built-in such as `PatchOperationsequence`), `parse-error` (malformed XML,
reported with file and line while every other file still loads).

Warnings never affect the exit code and are hidden with `--no-warnings`: duplicate
defNames across active mods, a patch file whose root is not `<Patch>`, a
`PatchOperationSequence` with an empty `<operations>` list, unreadable `About.xml`.

## Output formats

`--format text` (default), `--format json` for tooling, `--format github` for
annotations:

```
::error file=Patches/Core/Stats/Stats.xml,line=6,title=PatchOperationAdd::matched 0 nodes%0Axpath: Defs/StatDef[defName="Flammability"]%0A...
```

The JSON report carries the full skipped list, the diagnosis, and a summary with
`operationsChecked`, `defsLoaded`, `nodesGatedByMayRequire` and the mods in load order.

## Limitations

- Operation classes provided by mod assemblies, such as
  `CombatExtended.PatchOperationMakeGunCECompatible`, cannot be evaluated without running
  C#. They are counted in the summary and never reported as findings.
- rimpatch checks whether an xpath resolves. It does not check that the value you patch
  in is a field the game's classes actually have; that needs `Assembly-CSharp.dll`.
- `PatchOperationFindMod` matches on mod name, as the game does, and falls back to
  packageId.
- Vanilla defs come from your own install via `--game`. No game data is bundled.
- Roughly a second per 50 operations against a 46,000-def tree. A single mod against Core
  plus expansions is a few seconds; a 242-mod load order is about a minute.

## Tests

```
python -m pip install -e ".[dev]"
python -m pytest                      # everything
python -m pytest -m "not integration" # skip the test that fetches Combat Extended
```

The integration test pulls Combat Extended's live Patches tree from GitHub and asserts
every operation in it parses and evaluates without raising. It skips itself if GitHub is
unreachable.

## Who this is for

Anyone who ships a RimWorld mod with a `Patches/` folder and keeps the source in git.
There are roughly 500 repos tagged `rimworld-mod` on GitHub and about 53,000 XML files
using `PatchOperationAdd`, so the thing it checks is everywhere, but the audience that can
wire it into CI is the subset who version their mod rather than editing straight in the
Workshop folder.

It is not a mod manager and not a player-facing tool. If you do not write patches, it has
nothing to tell you.

## License

MIT.
