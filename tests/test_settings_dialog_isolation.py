"""Opening the Settings dialog must not write the default config file.

It used to snapshot the incoming settings into `Settings()`, whose property
setters save on every assignment, so constructing the dialog rewrote
~/.ankigammon/config.json with whatever settings it was handed. In the app
those were the same values; in the test suite they were a temp config's
defaults, so every pytest run reset the developer's GnuBG and XG paths.
"""

from pathlib import Path
from unittest import mock

import pytest

from ankigammon.settings import Settings


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    assert Path.home() == home
    return home


@pytest.fixture
def dialog_for(qapp):
    from ankigammon.gui.dialogs.settings_dialog import SettingsDialog

    def build(settings):
        with mock.patch("ankigammon.utils.xg_auto.registry.read_custom_analysis_levels", return_value=[]):
            return SettingsDialog(settings)

    return build


def test_opening_the_dialog_leaves_the_default_config_alone(fake_home, tmp_path, dialog_for):
    given = Settings(config_path=tmp_path / "given.json")
    # Not gnubg_path: a path starts a validation thread that outlives the test.
    given.max_moves = 7

    dialog_for(given)

    assert not (fake_home / ".ankigammon" / "config.json").exists()


@pytest.mark.parametrize("was_on, expect_notice", [(False, True), (True, False)])
def test_subdeck_notice_only_when_turning_subdecks_on(fake_home, tmp_path, dialog_for, was_on, expect_notice):
    given = Settings(config_path=tmp_path / "given.json")
    given.use_subdecks_by_type = was_on
    dialog = dialog_for(given)
    dialog.chk_use_subdecks.setChecked(False)

    with mock.patch("ankigammon.gui.dialogs.settings_dialog.QMessageBox.information") as notice:
        dialog.chk_use_subdecks.setChecked(True)

    assert notice.called is expect_notice
