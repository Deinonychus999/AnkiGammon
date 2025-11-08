"""Tests for import dialog player name matching functionality."""

import tempfile
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication

from ankigammon.settings import Settings
from ankigammon.gui.dialogs.import_options_dialog import ImportOptionsDialog


@pytest.fixture(scope="module")
def qapp():
    """Create QApplication instance for GUI tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestImportDialogPlayerMatching:
    """Test player name matching in import dialog."""

    def setup_method(self):
        """Create a temporary config file for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = Path(self.temp_dir) / "config.json"
        self.settings = Settings(config_path=self.config_path)

    def test_first_import_defaults_to_both_players(self, qapp):
        """Test that first import with no history selects both players."""
        dialog = ImportOptionsDialog(
            self.settings,
            player1_name="Alice",
            player2_name="Bob"
        )

        # Should default to both checked (legacy behavior)
        assert dialog.chk_player_o.isChecked()
        assert dialog.chk_player_x.isChecked()

    def test_remembers_single_player_by_name(self, qapp):
        """Test that selecting one player remembers them by name."""
        # First import: Alice vs Bob, select only Alice
        dialog1 = ImportOptionsDialog(
            self.settings,
            player1_name="Alice",
            player2_name="Bob"
        )
        dialog1.chk_player_o.setChecked(True)  # Alice
        dialog1.chk_player_x.setChecked(False)  # Bob unchecked
        dialog1.accept()

        # Second import: Bob vs Alice (positions swapped!)
        dialog2 = ImportOptionsDialog(
            self.settings,
            player1_name="Bob",
            player2_name="Alice"
        )

        # Alice should still be selected even though she's now Player 2
        assert not dialog2.chk_player_o.isChecked()  # Bob unchecked
        assert dialog2.chk_player_x.isChecked()  # Alice checked

    def test_remembers_both_players_by_name(self, qapp):
        """Test that selecting both players remembers both by name."""
        # First import: Alice vs Bob, select both
        dialog1 = ImportOptionsDialog(
            self.settings,
            player1_name="Alice",
            player2_name="Bob"
        )
        dialog1.chk_player_o.setChecked(True)
        dialog1.chk_player_x.setChecked(True)
        dialog1.accept()

        # Second import: Bob vs Alice (positions swapped)
        dialog2 = ImportOptionsDialog(
            self.settings,
            player1_name="Bob",
            player2_name="Alice"
        )

        # Both should still be selected
        assert dialog2.chk_player_o.isChecked()  # Bob
        assert dialog2.chk_player_x.isChecked()  # Alice

    def test_new_player_not_selected(self, qapp):
        """Test that a new player not in history is unchecked."""
        # First import: Alice vs Bob, select only Alice
        dialog1 = ImportOptionsDialog(
            self.settings,
            player1_name="Alice",
            player2_name="Bob"
        )
        dialog1.chk_player_o.setChecked(True)  # Alice
        dialog1.chk_player_x.setChecked(False)  # Bob
        dialog1.accept()

        # Second import: Alice vs Charlie (new player)
        dialog2 = ImportOptionsDialog(
            self.settings,
            player1_name="Alice",
            player2_name="Charlie"
        )

        # Only Alice should be selected
        assert dialog2.chk_player_o.isChecked()  # Alice
        assert not dialog2.chk_player_x.isChecked()  # Charlie (new)

    def test_case_insensitive_matching(self, qapp):
        """Test that player name matching is case-insensitive."""
        # First import: alice vs bob (lowercase)
        dialog1 = ImportOptionsDialog(
            self.settings,
            player1_name="alice",
            player2_name="bob"
        )
        dialog1.chk_player_o.setChecked(True)
        dialog1.chk_player_x.setChecked(False)
        dialog1.accept()

        # Second import: ALICE vs BOB (uppercase)
        dialog2 = ImportOptionsDialog(
            self.settings,
            player1_name="ALICE",
            player2_name="BOB"
        )

        # Alice should be matched case-insensitively
        assert dialog2.chk_player_o.isChecked()  # ALICE matched
        assert not dialog2.chk_player_x.isChecked()  # BOB not in history

    def test_generic_player_names(self, qapp):
        """Test behavior with generic 'Player 1' and 'Player 2' names."""
        # First import: Player 1 vs Player 2, select Player 1
        dialog1 = ImportOptionsDialog(
            self.settings,
            player1_name="Player 1",
            player2_name="Player 2"
        )
        dialog1.chk_player_o.setChecked(True)
        dialog1.chk_player_x.setChecked(False)
        dialog1.accept()

        # Second import: also generic names
        dialog2 = ImportOptionsDialog(
            self.settings,
            player1_name="Player 1",
            player2_name="Player 2"
        )

        # Should remember "Player 1"
        assert dialog2.chk_player_o.isChecked()
        assert not dialog2.chk_player_x.isChecked()

    def test_updating_selection_updates_names(self, qapp):
        """Test that changing selection updates stored names."""
        # First import: Select Alice
        dialog1 = ImportOptionsDialog(
            self.settings,
            player1_name="Alice",
            player2_name="Bob"
        )
        dialog1.chk_player_o.setChecked(True)
        dialog1.chk_player_x.setChecked(False)
        dialog1.accept()

        # Verify Alice is stored
        assert self.settings.import_selected_player_names == ["Alice"]

        # Second import: Select Bob instead
        dialog2 = ImportOptionsDialog(
            self.settings,
            player1_name="Alice",
            player2_name="Bob"
        )
        dialog2.chk_player_o.setChecked(False)
        dialog2.chk_player_x.setChecked(True)
        dialog2.accept()

        # Verify Bob is now stored (Alice removed)
        assert self.settings.import_selected_player_names == ["Bob"]

        # Third import: Should select Bob
        dialog3 = ImportOptionsDialog(
            self.settings,
            player1_name="Bob",
            player2_name="Charlie"
        )
        assert dialog3.chk_player_o.isChecked()  # Bob
        assert not dialog3.chk_player_x.isChecked()  # Charlie

    def test_no_match_with_history_unchecks_all(self, qapp):
        """Test that when no names match history, all are unchecked."""
        # First import: Select Alice and Bob
        dialog1 = ImportOptionsDialog(
            self.settings,
            player1_name="Alice",
            player2_name="Bob"
        )
        dialog1.chk_player_o.setChecked(True)
        dialog1.chk_player_x.setChecked(True)
        dialog1.accept()

        # Second import: Completely different players
        dialog2 = ImportOptionsDialog(
            self.settings,
            player1_name="Charlie",
            player2_name="Diana"
        )

        # Neither should be selected
        assert not dialog2.chk_player_o.isChecked()
        assert not dialog2.chk_player_x.isChecked()
