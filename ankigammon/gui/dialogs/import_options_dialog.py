"""
Import options dialog for XG file imports.
"""

from typing import Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout,
    QCheckBox, QDoubleSpinBox, QGroupBox,
    QLabel, QDialogButtonBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QShowEvent

from ankigammon.settings import Settings


class ImportOptionsDialog(QDialog):
    """
    Dialog for configuring XG import filtering options.

    Allows users to filter imported positions by:
    - Error thresholds (separate for checker play and cube decisions)
    - Player selection (import mistakes from X, O, or both)

    Signals:
        options_accepted(float, float, bool, bool): Emitted when user accepts
            Args: (checker_threshold, cube_threshold, include_player_x, include_player_o)
    """

    options_accepted = Signal(float, float, bool, bool)

    def __init__(
        self,
        settings: Settings,
        player1_name: Optional[str] = None,
        player2_name: Optional[str] = None,
        parent: Optional[QDialog] = None
    ):
        super().__init__(parent)
        self.settings = settings
        self.player1_name = player1_name or "Player 1"
        self.player2_name = player2_name or "Player 2"

        self.setWindowTitle("Import Options")
        self.setModal(True)
        self.setMinimumWidth(450)

        self._setup_ui()
        self._load_settings()
        self._update_ok_button_state()

    def _setup_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        # Error threshold group
        threshold_group = self._create_threshold_group()
        layout.addWidget(threshold_group)

        # Player selection group
        player_group = self._create_player_group()
        layout.addWidget(player_group)

        # Dialog buttons
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        # Add cursor pointers to buttons
        for button in self.button_box.buttons():
            button.setCursor(Qt.PointingHandCursor)

        layout.addWidget(self.button_box)

    def _create_threshold_group(self) -> QGroupBox:
        """Create error threshold settings group."""
        group = QGroupBox("Error Thresholds")
        form = QFormLayout(group)

        # Checker play threshold spinbox
        self.spin_checker_threshold = QDoubleSpinBox()
        self.spin_checker_threshold.setMinimum(0.000)
        self.spin_checker_threshold.setMaximum(1.000)
        self.spin_checker_threshold.setSingleStep(0.001)
        self.spin_checker_threshold.setDecimals(3)
        self.spin_checker_threshold.setValue(0.080)
        self.spin_checker_threshold.setCursor(Qt.PointingHandCursor)
        form.addRow("Checker Play:", self.spin_checker_threshold)

        # Cube decision threshold spinbox
        self.spin_cube_threshold = QDoubleSpinBox()
        self.spin_cube_threshold.setMinimum(0.000)
        self.spin_cube_threshold.setMaximum(1.000)
        self.spin_cube_threshold.setSingleStep(0.001)
        self.spin_cube_threshold.setDecimals(3)
        self.spin_cube_threshold.setValue(0.080)
        self.spin_cube_threshold.setCursor(Qt.PointingHandCursor)
        form.addRow("Cube Decisions:", self.spin_cube_threshold)

        return group

    def _create_player_group(self) -> QGroupBox:
        """Create player selection group."""
        group = QGroupBox("Player Selection")
        form = QFormLayout(group)

        # Player checkboxes (XG file player 1 = internal Player.O, player 2 = Player.X)
        self.chk_player_o = QCheckBox(self.player1_name)
        self.chk_player_o.setCursor(Qt.PointingHandCursor)
        self.chk_player_o.stateChanged.connect(self._update_ok_button_state)
        form.addRow(self.chk_player_o)

        # Player 2 checkbox
        self.chk_player_x = QCheckBox(self.player2_name)
        self.chk_player_x.setCursor(Qt.PointingHandCursor)
        self.chk_player_x.stateChanged.connect(self._update_ok_button_state)
        form.addRow(self.chk_player_x)

        # Warning label
        self.lbl_warning = QLabel("")
        self.lbl_warning.setStyleSheet(
            "color: #f38ba8; font-size: 11px; margin-top: 8px; min-height: 20px;"
        )
        form.addRow(self.lbl_warning)

        return group

    def showEvent(self, event: QShowEvent):
        """Reload settings when dialog is about to be shown."""
        super().showEvent(event)
        # Reload settings every time the dialog is shown to ensure we have
        # the latest values (in case a previous dialog in the import sequence updated them)
        self._load_settings()

    def _load_settings(self):
        """Load current settings into widgets, matching by player name."""
        self.spin_checker_threshold.setValue(self.settings.import_checker_error_threshold)
        self.spin_cube_threshold.setValue(self.settings.import_cube_error_threshold)

        selected_names = self.settings.import_selected_player_names
        selected_names_lower = [name.lower() for name in selected_names]

        if self.player1_name.lower() in selected_names_lower:
            self.chk_player_o.setChecked(True)
        elif not selected_names:
            # No history - use legacy position-based settings
            self.chk_player_o.setChecked(self.settings.import_include_player_o)
        else:
            # Has history but name doesn't match
            self.chk_player_o.setChecked(False)

        if self.player2_name.lower() in selected_names_lower:
            self.chk_player_x.setChecked(True)
        elif not selected_names:
            # No history - use legacy position-based settings
            self.chk_player_x.setChecked(self.settings.import_include_player_x)
        else:
            # Has history but name doesn't match
            self.chk_player_x.setChecked(False)

    def _update_ok_button_state(self):
        """Enable/disable OK button based on player selection."""
        at_least_one_selected = (
            self.chk_player_x.isChecked() or self.chk_player_o.isChecked()
        )

        ok_button = self.button_box.button(QDialogButtonBox.Ok)
        ok_button.setEnabled(at_least_one_selected)

        if at_least_one_selected:
            self.lbl_warning.setText("")
        else:
            self.lbl_warning.setText("At least one player must be selected")

    def accept(self):
        """Save settings and emit options."""
        self.settings.import_checker_error_threshold = self.spin_checker_threshold.value()
        self.settings.import_cube_error_threshold = self.spin_cube_threshold.value()

        selected_names = []
        if self.chk_player_o.isChecked():
            selected_names.append(self.player1_name)
        if self.chk_player_x.isChecked():
            selected_names.append(self.player2_name)

        self.settings.import_selected_player_names = selected_names

        # Also update legacy position-based settings for backward compatibility
        self.settings.import_include_player_x = self.chk_player_x.isChecked()
        self.settings.import_include_player_o = self.chk_player_o.isChecked()

        self.options_accepted.emit(
            self.spin_checker_threshold.value(),
            self.spin_cube_threshold.value(),
            self.chk_player_x.isChecked(),
            self.chk_player_o.isChecked()
        )

        super().accept()

    def get_options(self) -> tuple[float, float, bool, bool]:
        """
        Get the selected import options.

        Returns:
            Tuple of (checker_threshold, cube_threshold, include_player_x, include_player_o)
        """
        return (
            self.spin_checker_threshold.value(),
            self.spin_cube_threshold.value(),
            self.chk_player_x.isChecked(),
            self.chk_player_o.isChecked()
        )
