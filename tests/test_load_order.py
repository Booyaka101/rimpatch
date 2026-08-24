"""Load order decides which patches can possibly resolve, so it gets its own tests."""

from __future__ import annotations

from pathlib import Path

from rimpatch.discover import (
    Dependency,
    LoadFolder,
    Mod,
    order_by_declared_rules,
    read_mod,
    resolve_load_order,
)
from rimpatch.xmlutil import normalise_package_id


def mod(package_id: str, *, official=False, after=(), before=(), deps=()) -> Mod:
    return Mod(
        path=Path(package_id),
        package_id=package_id,
        name=package_id,
        official=official,
        load_after=tuple(normalise_package_id(x) for x in after),
        load_before=tuple(normalise_package_id(x) for x in before),
        dependencies=tuple(Dependency(x, x) for x in deps),
    )


def ids(mods) -> list[str]:
    return [item.package_id for item in mods]


def test_declared_dependency_moves_a_mod_earlier():
    mods = [mod("b.later", deps=["a.earlier"]), mod("a.earlier")]
    ordered, cyclic = order_by_declared_rules(mods)
    assert ids(ordered) == ["a.earlier", "b.later"]
    assert cyclic == []


def test_load_after_and_load_before_are_both_honoured():
    mods = [mod("c.third", after=["b.second"]), mod("b.second"), mod("a.first", before=["b.second"])]
    ordered, _ = order_by_declared_rules(mods)
    assert ids(ordered) == ["a.first", "b.second", "c.third"]


def test_official_content_loads_first():
    mods = [mod("some.mod"), mod("ludeon.rimworld", official=True)]
    ordered, _ = order_by_declared_rules(mods)
    assert ids(ordered) == ["ludeon.rimworld", "some.mod"]


def test_a_mod_that_declares_loadbefore_core_beats_every_official():
    # Harmony is the real case: it declares loadBefore Ludeon.RimWorld only, but must
    # still come before the expansions rather than deadlocking the whole graph.
    mods = [
        mod("ludeon.rimworld", official=True),
        mod("ludeon.rimworld.anomaly", official=True, after=["ludeon.rimworld"]),
        mod("brrainz.harmony", before=["ludeon.rimworld"]),
        mod("some.mod"),
    ]
    ordered, cyclic = order_by_declared_rules(mods)
    assert cyclic == []
    assert ids(ordered)[0] == "brrainz.harmony"
    assert ids(ordered).index("ludeon.rimworld") < ids(ordered).index("some.mod")


def test_a_genuine_cycle_does_not_strand_the_other_mods():
    mods = [
        mod("a.one", after=["b.two"]),
        mod("b.two", after=["a.one"]),
        mod("c.independent"),
    ]
    ordered, cyclic = order_by_declared_rules(mods)
    assert len(ordered) == 3
    assert set(ids(ordered)) == {"a.one", "b.two", "c.independent"}
    assert cyclic, "the forced pick should be reported"


def test_original_order_is_kept_where_nothing_says_otherwise():
    mods = [mod("z.last"), mod("m.middle"), mod("a.first")]
    ordered, _ = order_by_declared_rules(mods)
    assert ids(ordered) == ["z.last", "m.middle", "a.first"]


def test_auto_order_can_be_switched_off():
    mods = [mod("b.later", deps=["a.earlier"]), mod("a.earlier")]
    order = resolve_load_order(mods, None, auto_order=False)
    assert ids(order.mods) == ["b.later", "a.earlier"]


def test_mods_config_order_wins_and_missing_entries_are_recorded():
    mods = [mod("b.two"), mod("a.one")]
    order = resolve_load_order(mods, ["a.one", "nobody.missing", "b.two"])
    assert ids(order.mods) == ["a.one", "b.two"]
    assert order.missing == ["nobody.missing"]


def test_duplicate_package_ids_are_deduplicated():
    mods = [mod("same.id"), mod("Same.Id")]
    order = resolve_load_order(mods, None)
    assert len(order.mods) == 1
    assert order.duplicates == ["Same.Id"]


def test_steam_and_copy_suffixes_normalise_to_the_same_mod():
    assert normalise_package_id("Author.Mod_steam") == "author.mod"
    assert normalise_package_id("Author.Mod_copy") == "author.mod"


def test_load_folders_conditions(fixtures):
    subject = read_mod(fixtures / "loadfolders")
    entries = subject.load_folders["v1.6"]
    assert [entry.folder for entry in entries] == ["/", "WithBase", "WithMissing"]

    active = frozenset({"example.base", "example.loadfolders"})
    folders = [path.name for path in subject.content_folders(active, "1.6")]
    assert folders == ["loadfolders", "WithBase"]


def test_load_folder_all_variants_are_an_and():
    entry = LoadFolder(folder="X", if_mod_active_all=("a", "b"))
    assert not entry.should_load(frozenset({"a"}))
    assert entry.should_load(frozenset({"a", "b"}))

    either = LoadFolder(folder="X", if_mod_active=("a", "b"))
    assert either.should_load(frozenset({"a"}))


def test_version_folder_is_preferred_when_there_is_no_loadfolders(tmp_path):
    root = tmp_path / "versioned"
    (root / "About").mkdir(parents=True)
    (root / "About" / "About.xml").write_text(
        "<ModMetaData><packageId>a.b</packageId><name>a</name></ModMetaData>",
        encoding="utf-8",
    )
    (root / "1.6").mkdir()
    (root / "Common").mkdir()
    folders = read_mod(root).content_folders(frozenset(), "1.6")
    assert [path.name for path in folders] == ["versioned", "Common", "1.6"]


def test_declared_dependency_absent_from_the_order_is_recorded():
    order = resolve_load_order([mod("b.later", deps=["a.earlier"])], None)
    assert order.unsatisfied == [("b.later", "a.earlier")]

    both = resolve_load_order([mod("b.later", deps=["a.earlier"]), mod("a.earlier")], None)
    assert both.unsatisfied == []


def test_a_dependency_declared_twice_is_reported_once():
    # modDependencies and modDependenciesByVersion routinely name the same mod.
    order = resolve_load_order([mod("b.later", deps=["a.earlier", "a.earlier"])], None)
    assert order.unsatisfied == [("b.later", "a.earlier")]


def test_dependency_matching_ignores_packageid_case():
    mods = [mod("b.later", deps=["Erdelf.HumanoidAlienRaces"]), mod("erdelf.humanoidalienraces")]
    assert resolve_load_order(mods, None).unsatisfied == []


def test_mods_outside_modsconfig_are_recorded_as_inactive():
    order = resolve_load_order([mod("a.one"), mod("b.two")], ["a.one"])
    assert order.inactive == ["b.two"]
    assert [item.package_id for item in order.mods] == ["a.one", "b.two"]


def test_mods_outside_modsconfig_are_still_ordered_by_their_own_rules():
    """ModsConfig fixes the order for what it lists; the rest still have declared rules."""
    mods = [mod("z.dependent", after=["a.provider"]), mod("a.provider"), mod("in.config")]
    order = resolve_load_order(mods, ["in.config"])
    assert ids(order.mods) == ["in.config", "a.provider", "z.dependent"]


def test_modsconfig_positions_are_not_reshuffled_by_declared_rules():
    mods = [mod("first.one"), mod("second.two", before=["first.one"])]
    order = resolve_load_order(mods, ["first.one", "second.two"])
    assert ids(order.mods) == ["first.one", "second.two"]


def test_no_auto_order_leaves_the_extras_alone():
    mods = [mod("z.dependent", after=["a.provider"]), mod("a.provider")]
    order = resolve_load_order(mods, ["nothing.here"], auto_order=False)
    assert ids(order.mods) == ["z.dependent", "a.provider"]
