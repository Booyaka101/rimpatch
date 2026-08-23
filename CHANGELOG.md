# Changelog

All notable changes to rimpatch are recorded here. This project follows
[Semantic Versioning](https://semver.org/).

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
- A composite GitHub Action at the repo root with `findings` and `report` outputs.

### Notes

- Relative xpaths such as `Defs/StatDef[...]` are evaluated from the document node, the
  way `XmlDocument.SelectNodes` does. About 40% of real-world patch xpaths depend on this.
- Def inheritance is deliberately not resolved, because the game applies patches before
  resolving `ParentName`.
- Operation classes provided by mod assemblies cannot be evaluated without running C#.
  They are counted in the summary and never reported as findings.
