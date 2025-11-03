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

from ankigammon.settings import Settings


class ImportOptionsDialog(QDialog):
    """
    Dialog for configuring XG import filtering options.

    Allows users to filter imported positions by:
    - Error threshold (only import mistakes above this threshold)
    - Player selection (import mistakes from X, O, or both)

    Signals:
        options_accepted(float, bool, bool): Emitted when user accepts
            Args: (threshold, include_player_x, include_player_o)
    """

    options_accepted = Signal(float, bool, bool)

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
        group = QGroupBox("Error Threshold")
        form = QFormLayout(group)

        # Threshold spinbox
        self.spin_threshold = QDoubleSpinBox()
        self.spin_threshold.setMinimum(0.000)
        self.spin_threshold.setMaximum(1.000)
        self.spin_threshold.setSingleStep(0.001)
        self.spin_threshold.setDecimals(3)
        self.spin_threshold.setValue(0.080)
        self.spin_threshold.setCursor(Qt.PointingHandCursor)
        form.addRow("Minimum Error:", self.spin_threshold)

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
        self.lbl_warning = QLabel("At least one player must be selected")
        self.lbl_warning.setStyleSheet("color: #f38ba8; font-size: 11px; margin-top: 8px;")
        self.lbl_warning.setVisible(False)
        form.addRow(self.lbl_warning)

        return group

    def _load_settings(self):
        """Load current settings into widgets."""
        self.spin_threshold.setValue(self.settings.import_error_threshold)
        self.chk_player_x.setChecked(self.settings.import_include_player_x)
        self.chk_player_o.setChecked(self.settings.import_include_player_o)

    def _update_ok_button_state(self):
        """Enable/disable OK button based on player selection."""
        at_least_one_selected = (
            self.chk_player_x.isChecked() or self.chk_player_o.isChecked()
        )

        ok_button = self.button_box.button(QDialogButtonBox.Ok)
        ok_button.setEnabled(at_least_one_selected)

        # Show/hide warning
        self.lbl_warning.setVisible(not at_least_one_selected)

    def accept(self):
        """Save settings and emit options."""
        # Update settings
        self.settings.import_error_threshold = self.spin_threshold.value()
        self.settings.import_include_player_x = self.chk_player_x.isChecked()
        self.settings.import_include_player_o = self.chk_player_o.isChecked()

        # Emit signal with selected options
        self.options_accepted.emit(
            self.spin_threshold.value(),
            self.chk_player_x.isChecked(),
            self.chk_player_o.isChecked()
        )

        super().accept()

    def get_options(self) -> tuple[float, bool, bool]:
        """
        Get the selected import options.

        Returns:
            Tuple of (threshold, include_player_x, include_player_o)
        """
        return (
            self.spin_threshold.value(),
            self.chk_player_x.isChecked(),
            self.chk_player_o.isChecked()
        )
