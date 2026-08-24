"""Custom XG analysis profiles that reuse a built-in level name.

GitHub issue #57. XG lists its 7 built-in levels before the 5 registry
profile slots, and AnkiGammon resolves a level by matching the display name
against that dropdown. A custom profile named "Deep" is therefore
unreachable - the built-in "Deep" always matches first - so the user's
analysis silently ran at the wrong level while the UI reported their name.

Name alone cannot disambiguate the two, so the fix is to stop presenting the
ambiguous duplicate and tell the user to rename it inside XG.
"""

import logging

import pytest

from ankigammon.utils.xg_auto.registry import (
    BUILTIN_ANALYSIS_LEVELS,
    merge_analysis_levels,
)


class TestMergeAnalysisLevels:
    def test_distinct_custom_levels_are_appended(self):
        levels, collisions = merge_analysis_levels(["Gigantic", "Beast Mode"])

        assert levels == list(BUILTIN_ANALYSIS_LEVELS) + ["Gigantic", "Beast Mode"]
        assert collisions == []

    def test_colliding_custom_level_is_dropped_and_reported(self):
        levels, collisions = merge_analysis_levels(["Deep"])

        assert levels == list(BUILTIN_ANALYSIS_LEVELS)
        assert collisions == ["Deep"]

    def test_collision_is_case_insensitive(self):
        """XG's own dropdown match is case-insensitive, so the clash is too."""
        levels, collisions = merge_analysis_levels(["extreme", "DEEP"])

        assert "DEEP" not in levels
        assert collisions == ["DEEP"]
        assert "extreme" in levels

    def test_duplicate_custom_names_collapse(self):
        levels, collisions = merge_analysis_levels(["Gigantic", "Gigantic"])

        assert levels.count("Gigantic") == 1
        assert collisions == ["Gigantic"]

    def test_no_custom_levels_yields_builtins_only(self):
        levels, collisions = merge_analysis_levels([])

        assert levels == list(BUILTIN_ANALYSIS_LEVELS)
        assert collisions == []

    def test_blank_and_whitespace_names_are_ignored(self):
        levels, collisions = merge_analysis_levels(["", "   ", "Real One"])

        assert levels == list(BUILTIN_ANALYSIS_LEVELS) + ["Real One"]
        assert collisions == []

    def test_names_are_stripped(self):
        levels, _ = merge_analysis_levels(["  Gigantic  "])

        assert "Gigantic" in levels

    def test_builtin_list_matches_the_automator(self):
        """The dropdown and the XG-side resolver must agree on the built-ins."""
        pytest.importorskip("pywinauto")
        from ankigammon.utils.xg_auto.automator import XGAutomator

        assert [n.lower() for n in BUILTIN_ANALYSIS_LEVELS] == [
            n.lower() for n in XGAutomator.BUILTIN_ANALYSIS_LEVELS if n != "none"
        ]


class TestSettingsDialogDropdown:
    """The dropdown is where the user meets the collision."""

    @pytest.fixture
    def dialog_for(self, qapp, tmp_path):
        from unittest import mock
        from ankigammon.settings import Settings
        from ankigammon.gui.dialogs.settings_dialog import SettingsDialog

        def build(custom_levels):
            with mock.patch(
                "ankigammon.utils.xg_auto.registry.read_custom_analysis_levels",
                return_value=custom_levels,
            ):
                return SettingsDialog(Settings(config_path=tmp_path / "config.json"))

        return build

    def _items(self, dialog):
        cmb = dialog.cmb_xg_level
        return [cmb.itemText(i) for i in range(cmb.count()) if cmb.itemText(i)]

    def test_distinct_custom_level_is_offered(self, dialog_for):
        dialog = dialog_for(["Gigantic"])

        assert "Gigantic" in self._items(dialog)
        assert dialog.lbl_xg_level_warning.text() == ""

    def test_colliding_custom_level_is_not_offered_twice(self, dialog_for):
        dialog = dialog_for(["Deep"])

        assert self._items(dialog).count("Deep") == 1

    def test_collision_is_named_in_the_warning(self, dialog_for):
        dialog = dialog_for(["Deep"])

        assert "Deep" in dialog.lbl_xg_level_warning.text()

    def _select_xg(self, dialog):
        idx = dialog.cmb_analyzer_type.findData("xg")
        assert idx >= 0
        dialog.cmb_analyzer_type.setCurrentIndex(idx)
        dialog._on_analyzer_type_changed(idx)

    def test_warning_stays_hidden_without_a_collision(self, dialog_for):
        dialog = dialog_for(["Gigantic"])
        self._select_xg(dialog)

        assert not dialog.lbl_xg_level_warning.isVisibleTo(dialog)

    def test_warning_shows_on_the_xg_tab_when_there_is_a_collision(self, dialog_for):
        dialog = dialog_for(["Deep"])
        self._select_xg(dialog)

        assert dialog.lbl_xg_level_warning.isVisibleTo(dialog)

    def test_warning_hidden_again_when_switching_back_to_gnubg(self, dialog_for):
        dialog = dialog_for(["Deep"])
        self._select_xg(dialog)
        idx = dialog.cmb_analyzer_type.findData("gnubg")
        dialog.cmb_analyzer_type.setCurrentIndex(idx)
        dialog._on_analyzer_type_changed(idx)

        assert not dialog.lbl_xg_level_warning.isVisibleTo(dialog)

    def test_registry_failure_falls_back_to_builtins(self, qapp, tmp_path):
        from unittest import mock
        from ankigammon.settings import Settings
        from ankigammon.gui.dialogs.settings_dialog import SettingsDialog

        with mock.patch(
            "ankigammon.utils.xg_auto.registry.read_custom_analysis_levels",
            side_effect=OSError("registry unavailable"),
        ):
            dialog = SettingsDialog(Settings(config_path=tmp_path / "config.json"))

        assert self._items(dialog) == list(BUILTIN_ANALYSIS_LEVELS)


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestAmbiguityIsLogged:
    def test_duplicate_dropdown_entries_warn(self, caplog):
        """XG itself can still present both names; say so instead of picking silently."""
        pytest.importorskip("pywinauto")
        from unittest import mock
        from ankigammon.utils.xg_auto.automator import XGAutomator

        auto = XGAutomator()
        with mock.patch.object(XGAutomator, "_read_combo_items",
                               return_value=["Deep:1:2", "Extensive:1:2", "Deep:9:9"]), \
             mock.patch("ankigammon.utils.xg_auto.automator.user32"), \
             mock.patch("ankigammon.utils.xg_auto.automator.SendMessageW"), \
             mock.patch("ankigammon.utils.xg_auto.automator.WNDENUMPROC"), \
             mock.patch.object(XGAutomator, "_enum_combo_boxes", return_value=[1]), \
             caplog.at_level(logging.WARNING):
            auto._set_analysis_level(0, "Deep")

        assert any("Deep" in r.message and "more than one" in r.message.lower()
                   for r in caplog.records), caplog.text
