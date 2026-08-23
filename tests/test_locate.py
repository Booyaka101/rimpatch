"""Finding the install is the first thing that has to work for a stranger."""

from __future__ import annotations

import pytest

from rimpatch import locate


@pytest.fixture
def detecting(monkeypatch):
    """Undo the suite-wide kill switch for the tests that exercise detection itself."""
    monkeypatch.delenv(locate.OFF_ENV, raising=False)


def make_install(root, *, with_core=True):
    data = root / "Data"
    if with_core:
        core = data / "Core" / "About"
        core.mkdir(parents=True)
        (core / "About.xml").write_text(
            "<ModMetaData><packageId>Ludeon.RimWorld</packageId><name>Core</name></ModMetaData>",
            encoding="utf-8",
        )
    else:
        data.mkdir(parents=True)
    return root


def test_kill_switch_wins_over_everything(monkeypatch, tmp_path):
    make_install(tmp_path / "game")
    monkeypatch.setenv(locate.GAME_ENV, str(tmp_path / "game"))
    monkeypatch.setenv(locate.OFF_ENV, "1")
    assert locate.find_game() is None
    assert locate.find_mods_config() is None


def test_env_override_is_used_first(detecting, monkeypatch, tmp_path):
    install = make_install(tmp_path / "game")
    monkeypatch.setenv(locate.GAME_ENV, str(install))
    assert locate.find_game() == install


def test_a_folder_without_data_is_not_an_install(detecting, monkeypatch, tmp_path):
    empty = tmp_path / "not-a-game"
    empty.mkdir()
    monkeypatch.setenv(locate.GAME_ENV, str(empty))
    # Falls through to the real candidates, none of which exist under a fake home.
    monkeypatch.setattr(locate, "_home", lambda: tmp_path / "home")
    monkeypatch.setattr(locate, "_steam_roots", list)
    monkeypatch.setattr(locate, "game_candidates", lambda: [empty])
    assert locate.find_game() is None


def test_a_data_folder_of_expansions_counts_even_without_core(detecting, monkeypatch, tmp_path):
    root = make_install(tmp_path / "game", with_core=False)
    about = root / "Data" / "Royalty" / "About"
    about.mkdir(parents=True)
    (about / "About.xml").write_text("<ModMetaData/>", encoding="utf-8")
    monkeypatch.setenv(locate.GAME_ENV, str(root))
    assert locate.find_game() == root


def test_steam_libraries_are_read_out_of_libraryfolders_vdf(detecting, monkeypatch, tmp_path):
    steam = tmp_path / "Steam"
    (steam / "steamapps").mkdir(parents=True)
    other = tmp_path / "SecondDrive"
    other.mkdir()
    (steam / "steamapps" / "libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"'
        + str(steam).replace("\\", "\\\\")
        + '"\n\t}\n\t"1"\n\t{\n\t\t"path"\t\t"'
        + str(other).replace("\\", "\\\\")
        + '"\n\t}\n}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(locate, "_steam_roots", lambda: [steam])
    libraries = locate.steam_libraries()
    assert steam in libraries
    assert other in libraries, "a library on another drive must be picked up"


def test_a_game_in_a_second_steam_library_is_found(detecting, monkeypatch, tmp_path):
    steam = tmp_path / "Steam"
    (steam / "steamapps").mkdir(parents=True)
    other = tmp_path / "SecondDrive"
    install = make_install(other / "steamapps" / "common" / "RimWorld")
    (steam / "steamapps" / "libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n\t"1"\n\t{\n\t\t"path"\t\t"'
        + str(other).replace("\\", "\\\\")
        + '"\n\t}\n}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(locate, "_steam_roots", lambda: [steam])
    monkeypatch.delenv(locate.GAME_ENV, raising=False)
    assert locate.find_game() == install


def test_mods_config_env_override(detecting, monkeypatch, tmp_path):
    config = tmp_path / "Config"
    config.mkdir()
    (config / "ModsConfig.xml").write_text("<ModsConfigData/>", encoding="utf-8")
    monkeypatch.setenv(locate.CONFIG_ENV, str(config))
    assert locate.find_mods_config() == config / "ModsConfig.xml"


def test_missing_mods_config_returns_none(detecting, monkeypatch, tmp_path):
    monkeypatch.setattr(locate, "config_candidates", lambda: [tmp_path / "nope"])
    assert locate.find_mods_config() is None


def test_candidate_lists_are_never_empty():
    assert locate.game_candidates()
    assert locate.config_candidates()
