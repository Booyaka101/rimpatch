"""Regenerate tests/fixtures. Checked in so the fixture mods stay readable as real mod folders."""

from __future__ import annotations

import textwrap
from pathlib import Path

ROOT = Path(__file__).parent / "fixtures"


def write(rel: str, text: str) -> None:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")


def about(package_id: str, name: str, deps: tuple[str, ...] = ()) -> str:
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        "<ModMetaData>",
        f"  <name>{name}</name>",
        "  <author>rimpatch tests</author>",
        f"  <packageId>{package_id}</packageId>",
        "  <supportedVersions>",
        "    <li>1.6</li>",
        "  </supportedVersions>",
    ]
    if deps:
        lines.append("  <modDependencies>")
        for dep in deps:
            lines += [
                "    <li>",
                f"      <packageId>{dep}</packageId>",
                f"      <displayName>{dep}</displayName>",
                "    </li>",
            ]
        lines.append("  </modDependencies>")
    lines.append("</ModMetaData>")
    return "\n".join(lines) + "\n"


def main() -> None:
    write("base/About/About.xml", about("Example.Base", "Example Base"))
    write(
        "base/Defs/Stats/Stats.xml",
        """
        <?xml version="1.0" encoding="utf-8"?>
        <Defs>

          <StatDef>
            <defName>Flammability</defName>
            <label>flammability</label>
            <category>BasicsNonPawn</category>
          </StatDef>

          <ThingDef Name="BaseGun" Abstract="True">
            <statBases>
              <Mass>3</Mass>
            </statBases>
          </ThingDef>

          <ThingDef ParentName="BaseGun">
            <defName>Gun_Revolver</defName>
            <label>revolver</label>
          </ThingDef>

        </Defs>
        """,
    )

    # Same shape as Combat Extended's Patches/Core/Stats/Stats.xml: the Add is on line 6.
    write(
        "patcher/About/About.xml",
        about("Example.Patcher", "Example Patcher", ("Example.Base",)),
    )
    write(
        "patcher/Patches/Stats.xml",
        """
        <?xml version="1.0" encoding="utf-8"?>
        <Patch>

          <!-- ========== General ========== -->

          <Operation Class="PatchOperationAdd">
            <xpath>Defs/StatDef[defName="Flammability"]</xpath>
            <value>
              <workerClass>Example.StatWorker_Flammability</workerClass>
            </value>
          </Operation>

          <Operation Class="PatchOperationReplace">
            <xpath>Defs/StatDef[defName="Flammability"]/category</xpath>
            <value>
              <category>Basics</category>
            </value>
          </Operation>

        </Patch>
        """,
    )

    write("sequence/About/About.xml", about("Example.Sequence", "Example Sequence"))
    write(
        "sequence/Patches/Sequence.xml",
        """
        <?xml version="1.0" encoding="utf-8"?>
        <Patch>
          <Operation Class="PatchOperationSequence">
            <operations>
              <li Class="PatchOperationAdd">
                <xpath>Defs/StatDef[defName="Flammability"]</xpath>
                <value>
                  <first>1</first>
                </value>
              </li>
              <li Class="PatchOperationAdd">
                <xpath>Defs/StatDef[defName="NoSuchStat"]</xpath>
                <value>
                  <second>2</second>
                </value>
              </li>
              <li Class="PatchOperationAdd">
                <xpath>Defs/StatDef[defName="Flammability"]</xpath>
                <value>
                  <third>3</third>
                </value>
              </li>
            </operations>
          </Operation>
        </Patch>
        """,
    )

    write("findmod/About/About.xml", about("Example.FindMod", "Example FindMod"))
    write(
        "findmod/Patches/FindMod.xml",
        """
        <?xml version="1.0" encoding="utf-8"?>
        <Patch>
          <Operation Class="PatchOperationFindMod">
            <mods>
              <li>Some Mod Nobody Has Installed</li>
            </mods>
            <match Class="PatchOperationAdd">
              <xpath>Defs/StatDef[defName="Flammability"]</xpath>
              <value>
                <matched>yes</matched>
              </value>
            </match>
            <nomatch Class="PatchOperationAdd">
              <xpath>Defs/StatDef[defName="Flammability"]</xpath>
              <value>
                <fallback>yes</fallback>
              </value>
            </nomatch>
          </Operation>

          <Operation Class="PatchOperationFindMod">
            <mods>
              <li>Some Mod Nobody Has Installed</li>
            </mods>
            <match Class="PatchOperationAdd">
              <xpath>Defs/StatDef[defName="NoSuchStat"]</xpath>
              <value>
                <matched>yes</matched>
              </value>
            </match>
          </Operation>
        </Patch>
        """,
    )

    write("always/About/About.xml", about("Example.Always", "Example Always"))
    write(
        "always/Patches/Always.xml",
        """
        <?xml version="1.0" encoding="utf-8"?>
        <Patch>
          <Operation Class="PatchOperationAdd">
            <success>Always</success>
            <xpath>Defs/StatDef[defName="NoSuchStat"]</xpath>
            <value>
              <workerClass>Example.Nope</workerClass>
            </value>
          </Operation>
        </Patch>
        """,
    )

    write("conditional/About/About.xml", about("Example.Conditional", "Example Conditional"))
    write(
        "conditional/Patches/Conditional.xml",
        """
        <?xml version="1.0" encoding="utf-8"?>
        <Patch>
          <Operation Class="PatchOperationConditional">
            <xpath>Defs/StatDef[defName="NoSuchStat"]</xpath>
            <match Class="PatchOperationAdd">
              <xpath>Defs/StatDef[defName="NoSuchStat"]</xpath>
              <value>
                <nope>1</nope>
              </value>
            </match>
          </Operation>

          <Operation Class="PatchOperationAdd" MayRequire="Nobody.HasThisMod">
            <xpath>Defs/StatDef[defName="NoSuchStat"]</xpath>
            <value>
              <gated>1</gated>
            </value>
          </Operation>
        </Patch>
        """,
    )

    write("gated/About/About.xml", about("Example.Gated", "Example Gated"))
    write(
        "gated/Defs/Gated.xml",
        """
        <?xml version="1.0" encoding="utf-8"?>
        <Defs>
          <StatDef MayRequire="Nobody.HasThisMod">
            <defName>GatedStat</defName>
          </StatDef>
          <StatDef MayRequireAnyOf="Nobody.HasThisMod,Example.Base">
            <defName>AnyOfStat</defName>
          </StatDef>
        </Defs>
        """,
    )
    write(
        "gated/Patches/Gated.xml",
        """
        <?xml version="1.0" encoding="utf-8"?>
        <Patch>
          <Operation Class="PatchOperationAdd" MayRequire="Nobody.HasThisMod">
            <xpath>Defs/StatDef[defName="GatedStat"]</xpath>
            <value>
              <label>gated</label>
            </value>
          </Operation>
          <Operation Class="PatchOperationAdd">
            <xpath>Defs/StatDef[defName="AnyOfStat"]</xpath>
            <value>
              <label>kept</label>
            </value>
          </Operation>
        </Patch>
        """,
    )

    write("broken/About/About.xml", about("Example.Broken", "Example Broken"))
    write(
        "broken/Defs/Malformed.xml",
        """
        <?xml version="1.0" encoding="utf-8"?>
        <Defs>
          <StatDef>
            <defName>Unclosed</defName>
        </Defs>
        """,
    )
    write(
        "broken/Defs/Good.xml",
        """
        <?xml version="1.0" encoding="utf-8"?>
        <Defs>
          <StatDef>
            <defName>SurvivesTheBadFile</defName>
          </StatDef>
        </Defs>
        """,
    )
    write(
        "broken/Patches/Broken.xml",
        """
        <?xml version="1.0" encoding="utf-8"?>
        <Patch>
          <Operation Class="PatchOperationAdd">
            <xpath>Defs/StatDef[defName=</xpath>
            <value>
              <label>x</label>
            </value>
          </Operation>
          <Operation Class="PatchOperationsequence">
            <operations>
              <li Class="PatchOperationAdd">
                <xpath>Defs/StatDef[defName="SurvivesTheBadFile"]</xpath>
                <value>
                  <label>x</label>
                </value>
              </li>
            </operations>
          </Operation>
          <Operation Class="SomeMod.PatchOperationCustomThing">
            <xpath>Defs/StatDef[defName="Whatever"]</xpath>
          </Operation>
        </Patch>
        """,
    )

    write("dupe/About/About.xml", about("Example.Dupe", "Example Dupe"))
    write(
        "dupe/Defs/Dupe.xml",
        """
        <?xml version="1.0" encoding="utf-8"?>
        <Defs>
          <StatDef>
            <defName>Flammability</defName>
            <label>redefined</label>
          </StatDef>
        </Defs>
        """,
    )

    write("empty/About/About.xml", about("Example.Empty", "Example Empty"))
    write(
        "empty/Defs/Nothing.xml",
        """
        <?xml version="1.0" encoding="utf-8"?>
        <Defs>
          <StatDef>
            <defName>Lonely</defName>
          </StatDef>
        </Defs>
        """,
    )

    write("loadfolders/About/About.xml", about("Example.LoadFolders", "Example LoadFolders"))
    write(
        "loadfolders/LoadFolders.xml",
        """
        <?xml version="1.0" encoding="utf-8"?>
        <loadFolders>
          <v1.6>
            <li>/</li>
            <li IfModActive="Example.Base">WithBase</li>
            <li IfModActive="Nobody.HasThisMod">WithMissing</li>
          </v1.6>
        </loadFolders>
        """,
    )
    write(
        "loadfolders/Patches/Root.xml",
        """
        <?xml version="1.0" encoding="utf-8"?>
        <Patch>
          <Operation Class="PatchOperationAdd">
            <xpath>Defs/StatDef[defName="Flammability"]</xpath>
            <value>
              <fromRoot>1</fromRoot>
            </value>
          </Operation>
        </Patch>
        """,
    )
    write(
        "loadfolders/WithBase/Patches/WithBase.xml",
        """
        <?xml version="1.0" encoding="utf-8"?>
        <Patch>
          <Operation Class="PatchOperationAdd">
            <xpath>Defs/StatDef[defName="Flammability"]</xpath>
            <value>
              <fromWithBase>1</fromWithBase>
            </value>
          </Operation>
        </Patch>
        """,
    )
    write(
        "loadfolders/WithMissing/Patches/WithMissing.xml",
        """
        <?xml version="1.0" encoding="utf-8"?>
        <Patch>
          <Operation Class="PatchOperationAdd">
            <xpath>Defs/StatDef[defName="NeverLoaded"]</xpath>
            <value>
              <fromWithMissing>1</fromWithMissing>
            </value>
          </Operation>
        </Patch>
        """,
    )

    write("ops/About/About.xml", about("Example.Ops", "Example Ops"))
    write(
        "ops/Patches/AllOps.xml",
        """
        <?xml version="1.0" encoding="utf-8"?>
        <Patch>
          <Operation Class="PatchOperationInsert">
            <xpath>Defs/StatDef[defName="Flammability"]/category</xpath>
            <value>
              <inserted>1</inserted>
            </value>
          </Operation>
          <Operation Class="PatchOperationRemove">
            <xpath>Defs/StatDef[defName="Flammability"]/label</xpath>
          </Operation>
          <Operation Class="PatchOperationAttributeAdd">
            <xpath>Defs/StatDef[defName="Flammability"]</xpath>
            <attribute>Name</attribute>
            <value>FlammabilityBase</value>
          </Operation>
          <Operation Class="PatchOperationAttributeSet">
            <xpath>Defs/ThingDef[@Name="BaseGun"]</xpath>
            <attribute>Abstract</attribute>
            <value>True</value>
          </Operation>
          <Operation Class="PatchOperationAttributeRemove">
            <xpath>Defs/ThingDef[defName="Gun_Revolver"]</xpath>
            <attribute>ParentName</attribute>
          </Operation>
          <Operation Class="PatchOperationAddModExtension">
            <xpath>Defs/ThingDef[defName="Gun_Revolver"]</xpath>
            <value>
              <li Class="Example.SomeExtension">
                <flag>true</flag>
              </li>
            </value>
          </Operation>
          <Operation Class="PatchOperationSetName">
            <xpath>Defs/StatDef[defName="Flammability"]/category</xpath>
            <name>renamedCategory</name>
          </Operation>
          <Operation Class="PatchOperationTest">
            <xpath>Defs/ThingDef[@Name="BaseGun"]/statBases/Mass</xpath>
          </Operation>
        </Patch>
        """,
    )

    print(f"wrote fixtures under {ROOT}")


if __name__ == "__main__":
    main()
