"""
Import options dialog for XG file imports.

Two modes:
- Single-file: two named checkboxes for the file's two players.
- Batch: scrollable checklist of every distinct player name across the queue,
  shown once before processing starts. Triggered by passing
  batch_player_counts to the constructor.
"""

from typing import Dict, List, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QCheckBox, QDoubleSpinBox, QGroupBox,
    QLabel, QDialogButtonBox, QListWidget, QListWidgetItem, QPushButton,
    QLineEdit
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QShowEvent

from ankigammon.settings import Settings


class ImportOptionsDialog(QDialog):
    """
    Dialog for configuring XG import filtering options.

    Allows users to filter imported positions by:
    - Error thresholds (separate for checker play and cube decisions)
    - Player selection (whose mistakes to import)

    Single-file mode shows two checkboxes for player1/player2.
    Batch mode (when batch_player_counts is provided) shows a scrollable
    checklist of every distinct name across the queue with occurrence counts.

    Signals:
        options_accepted(float, float, bool, bool): Emitted when user accepts
            (checker_threshold, cube_threshold, include_player_x, include_player_o).
            In batch mode the two bool fields are always False; read
            settings.import_selected_player_names instead.
    """

    options_accepted = Signal(float, float, bool, bool)

    def __init__(
        self,
        settings: Settings,
        player1_name: Optional[str] = None,
        player2_name: Optional[str] = None,
        batch_player_counts: Optional[Dict[str, int]] = None,
        batch_file_count: int = 0,
        parent: Optional[QDialog] = None
    ):
        super().__init__(parent)
        self.settings = settings
        self.player1_name = player1_name or "Player 1"
        self.player2_name = player2_name or "Player 2"
        self.batch_player_counts = batch_player_counts
        self.batch_file_count = batch_file_count
        self.is_batch_mode = batch_player_counts is not None

        if self.is_batch_mode:
            self.setWindowTitle(f"Batch Import Options ({batch_file_count} match files)")
            self.setMinimumWidth(480)
            self.setMinimumHeight(520)
        else:
            self.setWindowTitle("Import Options")
            self.setMinimumWidth(450)

        self.setModal(True)

        self._setup_ui()
        self._load_settings()
        self._update_ok_button_state()

    def _setup_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        threshold_group = self._create_threshold_group()
        layout.addWidget(threshold_group)

        if self.is_batch_mode:
            player_group = self._create_batch_player_group()
        else:
            player_group = self._create_player_group()
        layout.addWidget(player_group)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        for button in self.button_box.buttons():
            button.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.button_box)

    def _create_threshold_group(self) -> QGroupBox:
        """Create error threshold settings group."""
        group = QGroupBox("Error Thresholds")
        form = QFormLayout(group)

        self.spin_checker_threshold = QDoubleSpinBox()
        self.spin_checker_threshold.setMinimum(0.000)
        self.spin_checker_threshold.setMaximum(1.000)
        self.spin_checker_threshold.setSingleStep(0.001)
        self.spin_checker_threshold.setDecimals(3)
        self.spin_checker_threshold.setValue(0.080)
        self.spin_checker_threshold.setCursor(Qt.PointingHandCursor)
        form.addRow("Checker Play:", self.spin_checker_threshold)

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
        """Create single-file player selection group (two named checkboxes)."""
        group = QGroupBox("Player Selection")
        form = QFormLayout(group)

        # XG file player 1 = internal Player.O, player 2 = Player.X
        self.chk_player_o = QCheckBox(self.player1_name)
        self.chk_player_o.setCursor(Qt.PointingHandCursor)
        self.chk_player_o.stateChanged.connect(self._update_ok_button_state)
        form.addRow(self.chk_player_o)

        self.chk_player_x = QCheckBox(self.player2_name)
        self.chk_player_x.setCursor(Qt.PointingHandCursor)
        self.chk_player_x.stateChanged.connect(self._update_ok_button_state)
        form.addRow(self.chk_player_x)

        self.lbl_warning = QLabel("")
        self.lbl_warning.setStyleSheet(
            "color: #f38ba8; font-size: 11px; margin-top: 8px; min-height: 20px;"
        )
        form.addRow(self.lbl_warning)

        return group

    def _create_batch_player_group(self) -> QGroupBox:
        """Create batch-mode player selection group (scrollable name checklist)."""
        group = QGroupBox(f"Players found across {self.batch_file_count} match file(s)")
        vbox = QVBoxLayout(group)

        help_label = QLabel("Tick the players whose mistakes to import.")
        help_label.setStyleSheet("color: #cdd6f4; font-size: 11px; margin-bottom: 4px;")
        vbox.addWidget(help_label)

        # Filter box (helpful when many distinct names — Select all/none act
        # on the filtered subset, so the user can e.g. search "frank" then
        # Select all to tick every spelling variant in one shot).
        self.txt_batch_filter = QLineEdit()
        self.txt_batch_filter.setPlaceholderText("Filter names…")
        self.txt_batch_filter.textChanged.connect(self._batch_apply_filter)
        vbox.addWidget(self.txt_batch_filter)

        btn_row = QHBoxLayout()
        btn_select_all = QPushButton("Select all")
        btn_select_all.setCursor(Qt.PointingHandCursor)
        btn_select_all.clicked.connect(self._batch_select_all)
        btn_select_none = QPushButton("Select none")
        btn_select_none.setCursor(Qt.PointingHandCursor)
        btn_select_none.clicked.connect(self._batch_select_none)
        btn_row.addWidget(btn_select_all)
        btn_row.addWidget(btn_select_none)
        btn_row.addStretch()
        self.lbl_batch_count = QLabel("")
        self.lbl_batch_count.setStyleSheet("color: #cdd6f4; font-size: 11px;")
        btn_row.addWidget(self.lbl_batch_count)
        vbox.addLayout(btn_row)

        self.list_batch_players = QListWidget()
        self.list_batch_players.setMinimumHeight(220)
        self.list_batch_players.itemChanged.connect(self._update_ok_button_state)

        # Sort by occurrence count descending, then alphabetical
        sorted_names = sorted(
            (self.batch_player_counts or {}).items(),
            key=lambda kv: (-kv[1], kv[0].lower())
        )
        for name, count in sorted_names:
            item = QListWidgetItem(f"{name}  ({count})")
            item.setData(Qt.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.list_batch_players.addItem(item)
        vbox.addWidget(self.list_batch_players)
        self._update_batch_count_label()

        self.lbl_warning = QLabel("")
        self.lbl_warning.setStyleSheet(
            "color: #f38ba8; font-size: 11px; margin-top: 8px; min-height: 20px;"
        )
        vbox.addWidget(self.lbl_warning)

        return group

    def _batch_select_all(self):
        """Tick every visible (filter-matching) item."""
        for i in range(self.list_batch_players.count()):
            item = self.list_batch_players.item(i)
            if not item.isHidden():
                item.setCheckState(Qt.Checked)

    def _batch_select_none(self):
        """Untick every visible (filter-matching) item."""
        for i in range(self.list_batch_players.count()):
            item = self.list_batch_players.item(i)
            if not item.isHidden():
                item.setCheckState(Qt.Unchecked)

    def _batch_apply_filter(self, text: str):
        """Show only items whose name contains the filter substring (case-insensitive)."""
        needle = text.strip().lower()
        for i in range(self.list_batch_players.count()):
            item = self.list_batch_players.item(i)
            name = item.data(Qt.UserRole) or ""
            item.setHidden(bool(needle) and needle not in name.lower())
        self._update_batch_count_label()

    def _update_batch_count_label(self):
        """Update the 'X of Y shown · Z selected' caption."""
        total = self.list_batch_players.count()
        visible = sum(1 for i in range(total) if not self.list_batch_players.item(i).isHidden())
        selected = sum(
            1 for i in range(total)
            if self.list_batch_players.item(i).checkState() == Qt.Checked
        )
        if visible == total:
            self.lbl_batch_count.setText(f"{total} names · {selected} selected")
        else:
            self.lbl_batch_count.setText(f"{visible} of {total} shown · {selected} selected")

    def showEvent(self, event: QShowEvent):
        """Reload settings when dialog is about to be shown."""
        super().showEvent(event)
        self._load_settings()

    def _load_settings(self):
        """Load current settings into widgets."""
        self.spin_checker_threshold.setValue(self.settings.import_checker_error_threshold)
        self.spin_cube_threshold.setValue(self.settings.import_cube_error_threshold)

        selected_names_lower = {n.lower() for n in self.settings.import_selected_player_names}

        if self.is_batch_mode:
            # Pre-tick names that match the user's saved selection
            for i in range(self.list_batch_players.count()):
                item = self.list_batch_players.item(i)
                name = item.data(Qt.UserRole)
                item.setCheckState(
                    Qt.Checked if name.lower() in selected_names_lower else Qt.Unchecked
                )
        else:
            if self.player1_name.lower() in selected_names_lower:
                self.chk_player_o.setChecked(True)
            elif not selected_names_lower:
                self.chk_player_o.setChecked(self.settings.import_include_player_o)
            else:
                self.chk_player_o.setChecked(False)

            if self.player2_name.lower() in selected_names_lower:
                self.chk_player_x.setChecked(True)
            elif not selected_names_lower:
                self.chk_player_x.setChecked(self.settings.import_include_player_x)
            else:
                self.chk_player_x.setChecked(False)

    def _selected_names(self) -> List[str]:
        """Return the currently-selected player names (mode-aware)."""
        if self.is_batch_mode:
            names = []
            for i in range(self.list_batch_players.count()):
                item = self.list_batch_players.item(i)
                if item.checkState() == Qt.Checked:
                    names.append(item.data(Qt.UserRole))
            return names
        else:
            names = []
            if self.chk_player_o.isChecked():
                names.append(self.player1_name)
            if self.chk_player_x.isChecked():
                names.append(self.player2_name)
            return names

    def _update_ok_button_state(self):
        """Enable/disable OK button based on player selection."""
        at_least_one_selected = bool(self._selected_names())

        ok_button = self.button_box.button(QDialogButtonBox.Ok)
        ok_button.setEnabled(at_least_one_selected)

        if at_least_one_selected:
            self.lbl_warning.setText("")
        else:
            self.lbl_warning.setText("At least one player must be selected")

        if self.is_batch_mode:
            self._update_batch_count_label()

    def accept(self):
        """Save settings and emit options."""
        self.settings.import_checker_error_threshold = self.spin_checker_threshold.value()
        self.settings.import_cube_error_threshold = self.spin_cube_threshold.value()

        selected_names = self._selected_names()
        self.settings.import_selected_player_names = selected_names

        if not self.is_batch_mode:
            # Legacy position-based settings only meaningful in single-file mode
            self.settings.import_include_player_x = self.chk_player_x.isChecked()
            self.settings.import_include_player_o = self.chk_player_o.isChecked()

        # Emit per-file boolean view (only meaningful in single-file mode)
        if self.is_batch_mode:
            self.options_accepted.emit(
                self.spin_checker_threshold.value(),
                self.spin_cube_threshold.value(),
                False,
                False
            )
        else:
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
            (checker_threshold, cube_threshold, include_player_x, include_player_o)

        In batch mode the bool fields are always False; callers should read
        settings.import_selected_player_names and resolve per file.
        """
        if self.is_batch_mode:
            return (
                self.spin_checker_threshold.value(),
                self.spin_cube_threshold.value(),
                False,
                False
            )
        return (
            self.spin_checker_threshold.value(),
            self.spin_cube_threshold.value(),
            self.chk_player_x.isChecked(),
            self.chk_player_o.isChecked()
        )
