# rimpatch

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

Point it at your mod and at your RimWorld install, which is where the vanilla defs come
from. rimpatch never ships game data.

```
rimpatch check --game "C:/Program Files (x86)/Steam/steamapps/common/RimWorld" --mods ./MyMod
```

In CI, where the game is not installed, check the checkout against sibling checkouts of
the mods it declares in `About.xml`:

```
rimpatch check --repo .
```

Exit code is 0 when clean, 1 when there are findings, 2 when rimpatch itself could not
run (bad path, unreadable ModsConfig).

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
patch in Rim of Madness - Bones lands nowhere and takes 75 later operations with it,
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

      - uses: cbosch101/rimpatch@v1
        with:
          repo: .
```

Inputs: `repo`, `mods` (one path per line), `game`, `mods-config`, `game-version`,
`strict`, `warnings`, `fail-on-findings`, `version`, `python-version`.
Outputs: `findings` (count) and `report` (path to the JSON report).

Without a RimWorld install on the runner, vanilla defs are absent, so operations
targeting Core will legitimately report as unresolved. Either check out the mods you
patch as siblings, or scope the action to a mod that only patches other mods.

## Getting the load order right

Which patches can resolve depends entirely on what loaded before them, so rimpatch takes
load order seriously.

- `--mods-config path/to/ModsConfig.xml` is the exact answer: the active list and order
  the game itself will use. On Windows it lives in
  `%USERPROFILE%/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios/Config/`.
- Otherwise official content loads first, then your mods are ordered by what they
  declare: `modDependencies`, `loadAfter`, `loadBefore` and the `force*` variants.
  Anything the mods do not constrain keeps the order you gave. `--no-auto-order` turns
  this off and uses your order verbatim.
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

## First distribution step

Post it in the [RimWorld modding Discord's](https://discord.gg/rimworld) `#mod-development`
channel and on `/r/RimWorldMods`, replying to one of the open "Failed to find a node with
the given xpath" issues with the exact finding rimpatch produces for it. The people
filing those issues are the users; showing the tool naming the broken line beats
describing it.

## License

MIT.
