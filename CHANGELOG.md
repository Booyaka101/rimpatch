# Changelog

All notable changes to rimpatch are recorded here. This project follows
[Semantic Versioning](https://semver.org/).

## 1.1.0 - 2026-08-24

### Fixed

- Mods outside the given `ModsConfig.xml` were appended in whatever order the disk
  returned, with none of their declared `loadAfter` or `modDependencies` rules applied.
  A mod could land ahead of the dependency it says it loads after, and every patch that
  needed what the dependency contributes then reported as unresolved. On a real 242-mod
  run this was 8 of 10 findings: Pawnmorpher sat at position 44 with Humanoid Alien
  Races, which it declares `loadAfter`, at 238. Those extras are now ordered by the same
  declared rules already used when there is no `ModsConfig.xml`, and the run drops to
  the 2 findings that are real.
- The README undercounted the worked example by one. `PatchOperationSequence` takes 76
  later operations with it, not 75.

### Added

- A warning naming a `modDependencies` entry that is not in the load order, raised only
  for mods that also have operations matching nothing, so it explains findings rather
  than linting metadata. With no vanilla defs loaded at all the existing missing-Core
  hint takes precedence, because that is the real cause and naming a dependency on top
  of it misleads.
- A note listing mods that were checked despite not being active in the `ModsConfig.xml`
  that was supplied.
- `starvedMods` in the JSON summary.

## 1.0.0 - 2026-08-23

First release.

### Added

- `rimpatch check` assembles the Def tree the game would assemble and runs every
  PatchOperation against it in load order, reporting the ones that match zero nodes with
  file, line, mod, class and xpath.
- All twelve built-in operation classes plus `PatchOperationFindMod`.
- Deepest-matching-prefix diagnosis, with near-miss defName suggestions when a def looks
  renamed rather than removed.
- Automatic discovery of the RimWorld install, including Steam libraries on other drives
  via `libraryfolders.vdf`, on Windows, macOS and Linux. Override with `RIMWORLD_DIR`,
  disable with `--no-game` or `RIMPATCH_NO_AUTODETECT=1`.
- `rimpatch check` with no arguments treats the current folder as the mod.
- `rimpatch mods` prints the resolved load order and each mod's content folders.
- `rimpatch where` shows the install and `ModsConfig.xml` it can find, and every path it
  looked at when it cannot.
- Load order from `--mods-config`, including `--mods-config auto`. Without one, mods are
  ordered by their declared `modDependencies`, `loadAfter`, `loadBefore` and the `force*`
  variants; `--no-auto-order` keeps the order given.
- `LoadFolders.xml` support, including `IfModActive`/`IfModNotActive` as an OR and
  `IfModActiveAll`/`IfModNotActiveAll` as an AND.
- `MayRequire` and `MayRequireAnyOf` gating in both def and patch files, applied before
  any xpath runs.
- `text`, `json` and `github` output formats. Exit 0 clean, 1 findings, 2 error.
- Warnings for duplicate defNames, a patch root that is not `<Patch>`, an empty
  `<operations>` list and unreadable `About.xml`. Warnings never change the exit code.
- `--write-baseline` and `--baseline`, so a mod with existing breakage can adopt this in
  CI and only fail on what it breaks next. Entries are matched on mod, file, class and
  xpath, never on line number. Entries that no longer occur are reported as unneeded.
- A composite GitHub Action at the repo root with `findings` and `report` outputs, and a
  `baseline` input.

### Notes

- Relative xpaths such as `Defs/StatDef[...]` are evaluated from the document node, the
  way `XmlDocument.SelectNodes` does. About 40% of real-world patch xpaths depend on this.
- Def inheritance is deliberately not resolved, because the game applies patches before
  resolving `ParentName`.
- Operation classes provided by mod assemblies cannot be evaluated without running C#.
  They are counted in the summary and never reported as findings.
