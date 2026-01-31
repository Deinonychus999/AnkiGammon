"""
Settings configuration dialog.
"""

import os
import sys
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
import qtawesome as qta
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QComboBox, QCheckBox, QLineEdit, QPushButton,
    QGroupBox, QFileDialog, QLabel, QDialogButtonBox,
    QGraphicsOpacityEffect, QFrame, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QThread

from ankigammon.settings import Settings
from ankigammon.renderer.color_schemes import list_schemes


class GnuBGValidationWorker(QThread):
    """Worker thread for validating GnuBG executable without blocking UI."""

    # Signals to communicate with main thread
    validation_complete = Signal(str, str)  # (status_text, status_type)

    def __init__(self, gnubg_path: str):
        super().__init__()
        self.gnubg_path = gnubg_path

    def run(self):
        """Run validation in background thread."""
        path_obj = Path(self.gnubg_path)

        # Check if file exists
        if not path_obj.exists():
            self.validation_complete.emit("File not found", "error")
            return

        if not path_obj.is_file():
            self.validation_complete.emit("Not a file", "error")
            return

        # Create a simple command file (same approach as gnubg_analyzer)
        command_file = None
        try:
            # Create temp command file
            fd, command_file = tempfile.mkstemp(suffix=".txt", prefix="gnubg_test_")
            try:
                with os.fdopen(fd, 'w') as f:
                    # Simple command that should work on any gnubg
                    f.write("quit\n")
            except:
                os.close(fd)
                raise

            # Try to run gnubg with -t (text mode), -q (quiet mode), and -c (command file)
            # Suppress console window on Windows; allow extra time for neural network loading
            kwargs = {
                'capture_output': True,
                'text': True,
                'timeout': 15
            }
            if sys.platform == 'win32':
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

            result = subprocess.run(
                [str(self.gnubg_path), "-t", "-q", "-c", command_file],
                **kwargs
            )

            # Check if it's actually GNU Backgammon
            output = result.stdout + result.stderr
            if "GNU Backgammon" in output or result.returncode == 0:
                # Check for GUI version and recommend CLI version on Windows
                exe_name = path_obj.stem.lower()
                if sys.platform == 'win32' and "cli" not in exe_name and exe_name == "gnubg":
                    self.validation_complete.emit(
                        "GUI version detected (use gnubg-cli.exe)",
                        "warning"
                    )
                else:
                    self.validation_complete.emit(
                        "Valid GnuBG executable",
                        "valid"
                    )
            else:
                self.validation_complete.emit("Not GNU Backgammon", "warning")

        except subprocess.TimeoutExpired:
            self.validation_complete.emit("Validation timeout", "warning")
        except Exception as e:
            self.validation_complete.emit(
                f"Cannot execute: {type(e).__name__}",
                "warning"
            )
        finally:
            # Clean up temp file
            if command_file:
                try:
                    os.unlink(command_file)
                except OSError:
                    pass


class SettingsDialog(QDialog):
    """
    Dialog for configuring application settings.

    Signals:
        settings_changed(Settings): Emitted when user saves changes
    """

    settings_changed = Signal(Settings)

    def __init__(self, settings: Settings, parent: Optional[QDialog] = None):
        super().__init__(parent)
        self.settings = settings
        self.original_settings = Settings()
        self.original_settings.color_scheme = settings.color_scheme
        self.original_settings.swap_checker_colors = settings.swap_checker_colors
        self.original_settings.deck_name = settings.deck_name
        self.original_settings.use_subdecks_by_type = settings.use_subdecks_by_type
        self.original_settings.show_options = settings.show_options
        self.original_settings.show_pip_count = settings.show_pip_count
        self.original_settings.interactive_moves = settings.interactive_moves
        self.original_settings.preview_moves_before_submit = settings.preview_moves_before_submit
        self.original_settings.export_method = settings.export_method
        self.original_settings.board_orientation = settings.board_orientation
        self.original_settings.gnubg_path = settings.gnubg_path
        self.original_settings.gnubg_analysis_ply = settings.gnubg_analysis_ply
        self.original_settings.generate_score_matrix = settings.generate_score_matrix
        self.original_settings.max_moves = settings.max_moves

        # Validation worker
        self.validation_worker: Optional[GnuBGValidationWorker] = None

        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(500)

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        # 2x2 grid layout for settings groups
        grid = QGridLayout()

        # Row 0, Column 0: Anki Export
        anki_group = self._create_anki_group()
        grid.addWidget(anki_group, 0, 0)

        # Row 0, Column 1: GnuBG Integration
        gnubg_group = self._create_gnubg_group()
        grid.addWidget(gnubg_group, 0, 1)

        # Row 1, Column 0: Board Appearance
        board_group = self._create_board_group()
        grid.addWidget(board_group, 1, 0)

        # Row 1, Column 1: Study Options
        study_group = self._create_study_group()
        grid.addWidget(study_group, 1, 1)

        layout.addLayout(grid)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        # Add cursor pointers to OK and Cancel buttons
        for button in button_box.buttons():
            button.setCursor(Qt.PointingHandCursor)

        layout.addWidget(button_box)

    def _create_anki_group(self) -> QGroupBox:
        """Create Anki settings group."""
        group = QGroupBox("Anki Export")
        form = QFormLayout(group)

        # Deck name
        self.txt_deck_name = QLineEdit()
        form.addRow("Default Deck Name:", self.txt_deck_name)

        # Export method
        self.cmb_export_method = QComboBox()
        self.cmb_export_method.addItems(["AnkiConnect", "APKG File"])
        self.cmb_export_method.setCursor(Qt.PointingHandCursor)
        form.addRow("Default Export Method:", self.cmb_export_method)

        # Subdeck organization
        self.chk_use_subdecks = QCheckBox("Split checker and cube decisions into subdecks")
        self.chk_use_subdecks.setCursor(Qt.PointingHandCursor)
        self.chk_use_subdecks.stateChanged.connect(self._on_subdeck_toggled)
        form.addRow(self.chk_use_subdecks)

        # Clear positions after export
        self.chk_clear_after_export = QCheckBox("Clear position list after export")
        self.chk_clear_after_export.setCursor(Qt.PointingHandCursor)
        self.chk_clear_after_export.setToolTip(
            "When enabled, the position list is cleared after a successful export.\n"
            "Disable this to keep positions for re-export or further review."
        )
        form.addRow(self.chk_clear_after_export)

        return group

    def _create_board_group(self) -> QGroupBox:
        """Create board appearance settings group."""
        group = QGroupBox("Board Appearance")
        form = QFormLayout(group)
        form.setVerticalSpacing(8)

        # Theme
        self.cmb_color_scheme = QComboBox()
        self.cmb_color_scheme.addItems(list_schemes())
        self.cmb_color_scheme.setCursor(Qt.PointingHandCursor)
        self.cmb_color_scheme.setToolTip("Visual color scheme for the backgammon board")
        form.addRow("Theme:", self.cmb_color_scheme)

        # Orientation
        self.cmb_board_orientation = QComboBox()
        self.cmb_board_orientation.addItem("Counter-clockwise", "counter-clockwise")
        self.cmb_board_orientation.addItem("Clockwise", "clockwise")
        self.cmb_board_orientation.addItem("Random (at export)", "random")
        self.cmb_board_orientation.setCursor(Qt.PointingHandCursor)
        self.cmb_board_orientation.setToolTip(
            "Direction of point numbering:\n"
            "• Counter-clockwise (bear-off on the right)\n"
            "• Clockwise (bear-off on the left)\n"
            "• Random: Randomly varies per card (trains both perspectives)"
        )
        form.addRow("Orientation:", self.cmb_board_orientation)

        # Score format
        self.cmb_score_format = QComboBox()
        self.cmb_score_format.addItem("Absolute", "absolute")
        self.cmb_score_format.addItem("Away", "away")
        self.cmb_score_format.setCursor(Qt.PointingHandCursor)
        self.cmb_score_format.setToolTip(
            "How to display match scores:\n"
            "• Absolute: Current scores\n"
            "• Away: Points needed to win"
        )
        form.addRow("Score Format:", self.cmb_score_format)

        # Pip count display
        self.chk_show_pip_count = QCheckBox("Show pip count")
        self.chk_show_pip_count.setCursor(Qt.PointingHandCursor)
        self.chk_show_pip_count.setStyleSheet("font-size: 14px;")
        self.chk_show_pip_count.setToolTip(
            "Display pip counts on the board showing the total distance\n"
            "each player needs to bear off all their checkers."
        )
        form.addRow(self.chk_show_pip_count)

        # Swap checker colors
        self.chk_swap_checker_colors = QCheckBox("Swap checker colors")
        self.chk_swap_checker_colors.setCursor(Qt.PointingHandCursor)
        self.chk_swap_checker_colors.setStyleSheet("font-size: 14px;")
        self.chk_swap_checker_colors.setToolTip(
            "Swap the checker colors so the dark/colored checkers\n"
            "are on roll instead of white/light checkers."
        )
        form.addRow(self.chk_swap_checker_colors)

        return group

    def _create_study_group(self) -> QGroupBox:
        """Create study options group."""
        group = QGroupBox("Study Options")
        form = QFormLayout(group)
        form.setVerticalSpacing(8)

        # Multiple Choice Mode (parent)
        self.chk_show_options = QCheckBox("Show answer choices")
        self.chk_show_options.setCursor(Qt.PointingHandCursor)
        self.chk_show_options.setStyleSheet("font-size: 14px;")
        self.chk_show_options.setToolTip(
            "Display answer choices on the card front as a multiple-choice question.\n"
            "If unchecked, only the position is shown (self-reveal mode)."
        )
        form.addRow(self.chk_show_options)

        # Preview moves (child, indented)
        preview_layout = QHBoxLayout()
        preview_layout.addSpacing(20)  # Indent to show hierarchy
        self.chk_preview_moves = QCheckBox("Preview before answering")
        self.chk_preview_moves.setCursor(Qt.PointingHandCursor)
        self.chk_preview_moves.setStyleSheet("font-size: 14px;")
        self.chk_preview_moves.setToolTip(
            "When enabled, clicking an answer choice shows the resulting position\n"
            "and adds a Submit button. Without this, clicking an option instantly reveals the answer."
        )
        preview_layout.addWidget(self.chk_preview_moves)
        preview_layout.addStretch()
        form.addRow(preview_layout)

        # Maximum moves to display on cards
        max_moves_layout = QHBoxLayout()
        self.lbl_max_moves = QLabel("Max moves:")
        max_moves_layout.addWidget(self.lbl_max_moves)
        max_moves_layout.addSpacing(8)  # Space between label and dropdown
        self.cmb_max_moves = QComboBox()
        self.cmb_max_moves.addItems([str(i) for i in range(2, 11)])
        self.cmb_max_moves.setCursor(Qt.PointingHandCursor)
        self.cmb_max_moves.setMaximumWidth(80)
        self.cmb_max_moves.setToolTip(
            "Maximum number of moves to display on cards (2-10).\n"
            "Applies to MCQ choices and back card analysis.\n"
            "Fewer moves may be shown if there aren't enough alternatives."
        )
        max_moves_layout.addWidget(self.cmb_max_moves)
        max_moves_layout.addStretch()
        form.addRow(max_moves_layout)

        # Interactive move visualization (independent, works on all card types)
        self.chk_interactive_moves = QCheckBox("Interactive moves in analysis")
        self.chk_interactive_moves.setCursor(Qt.PointingHandCursor)
        self.chk_interactive_moves.setStyleSheet("font-size: 14px;")
        self.chk_interactive_moves.setToolTip(
            "Click on alternative moves in the analysis table to see the resulting position.\n"
            "Works on the back of both multiple-choice and self-reveal cards."
        )
        form.addRow(self.chk_interactive_moves)

        # Connect checkbox to enable/disable preview sub-option
        self.chk_show_options.toggled.connect(self._on_show_options_toggled_preview)

        return group

    def _create_gnubg_group(self) -> QGroupBox:
        """Create GnuBG settings group."""
        group = QGroupBox("GnuBG Integration (for non-analyzed positions)")
        form = QFormLayout(group)

        # GnuBG path
        path_layout = QHBoxLayout()
        self.txt_gnubg_path = QLineEdit()
        self.txt_gnubg_path.setToolTip("Path to the GnuBG executable (gnubg-cli.exe on Windows)")
        btn_browse = QPushButton("Browse...")
        btn_browse.setCursor(Qt.PointingHandCursor)
        btn_browse.clicked.connect(self._browse_gnubg)
        path_layout.addWidget(self.txt_gnubg_path)
        path_layout.addWidget(btn_browse)
        form.addRow("GnuBG CLI Path:", path_layout)

        # Analysis depth
        self.cmb_gnubg_ply = QComboBox()
        self.cmb_gnubg_ply.addItems(["0", "1", "2", "3", "4"])
        self.cmb_gnubg_ply.setCursor(Qt.PointingHandCursor)
        self.cmb_gnubg_ply.setMaximumWidth(60)  # Small dropdown for single digits
        self.cmb_gnubg_ply.setToolTip(
            "Analysis depth (moves ahead to evaluate):\n"
            "• 0-ply: Instant evaluation (least accurate)\n"
            "• 2-ply: Balanced (recommended, ~10 seconds per position)\n"
            "• 4-ply: Most thorough (very slow, ~1+ minute per position)"
        )
        form.addRow("Analysis Depth (ply):", self.cmb_gnubg_ply)

        # Score matrix generation
        matrix_layout = QHBoxLayout()
        self.chk_generate_score_matrix = QCheckBox("Generate score matrix for cube decisions")
        self.chk_generate_score_matrix.setCursor(Qt.PointingHandCursor)
        self.chk_generate_score_matrix.setStyleSheet("font-size: 14px;")
        self.chk_generate_score_matrix.setToolTip(
            "Generates a detailed table showing winning chances at different match scores.\n"
            "This is very time-consuming and can significantly slow down analysis."
        )
        matrix_layout.addWidget(self.chk_generate_score_matrix)
        matrix_warning = QLabel("(time-consuming)")
        matrix_warning.setStyleSheet("font-size: 11px; color: #a6adc8; margin-left: 8px;")
        matrix_layout.addWidget(matrix_warning)
        matrix_layout.addStretch()
        form.addRow(matrix_layout)

        # Move score matrix generation (checker play)
        move_matrix_layout = QHBoxLayout()
        self.chk_generate_move_score_matrix = QCheckBox("Generate move analysis by score for checker play")
        self.chk_generate_move_score_matrix.setCursor(Qt.PointingHandCursor)
        self.chk_generate_move_score_matrix.setStyleSheet("font-size: 14px;")
        self.chk_generate_move_score_matrix.setToolTip(
            "Generates a table showing top 3 moves at different match scores:\n"
            "Neutral (money), DMP, Gammon-Save, and Gammon-Go.\n"
            "This is time-consuming and can significantly slow down analysis."
        )
        move_matrix_layout.addWidget(self.chk_generate_move_score_matrix)
        move_matrix_warning = QLabel("(time-consuming)")
        move_matrix_warning.setStyleSheet("font-size: 11px; color: #a6adc8; margin-left: 8px;")
        move_matrix_layout.addWidget(move_matrix_warning)
        move_matrix_layout.addStretch()
        form.addRow(move_matrix_layout)

        # Status display (icon + text in horizontal layout)
        status_layout = QHBoxLayout()
        self.lbl_gnubg_status_icon = QLabel()
        self.lbl_gnubg_status_text = QLabel()
        status_layout.addWidget(self.lbl_gnubg_status_icon)
        status_layout.addWidget(self.lbl_gnubg_status_text)
        status_layout.addStretch()
        form.addRow("Status:", status_layout)

        return group

    def _on_subdeck_toggled(self, _state):
        """Show info when enabling subdecks for the first time."""
        is_checked = self.chk_use_subdecks.isChecked()
        if is_checked and not self.original_settings.use_subdecks_by_type:
            QMessageBox.information(
                self,
                "Subdeck Organization",
                "New exports will use subdecks.\n\n"
                "Existing cards won't move automatically. "
                "Use Anki's Browser to reorganize if needed."
            )

    def _load_settings(self):
        """Load current settings into widgets."""
        self.txt_deck_name.setText(self.settings.deck_name)
        self.chk_use_subdecks.setChecked(self.settings.use_subdecks_by_type)
        self.chk_clear_after_export.setChecked(self.settings.clear_positions_after_export)

        # Export method
        method_index = 0 if self.settings.export_method == "ankiconnect" else 1
        self.cmb_export_method.setCurrentIndex(method_index)

        # Color scheme
        scheme_index = list_schemes().index(self.settings.color_scheme)
        self.cmb_color_scheme.setCurrentIndex(scheme_index)

        # Board orientation
        orientation_map = {"counter-clockwise": 0, "clockwise": 1, "random": 2}
        orientation_index = orientation_map.get(self.settings.board_orientation, 0)
        self.cmb_board_orientation.setCurrentIndex(orientation_index)

        self.chk_show_options.setChecked(self.settings.show_options)
        self.chk_show_pip_count.setChecked(self.settings.show_pip_count)
        self.chk_swap_checker_colors.setChecked(self.settings.swap_checker_colors)

        # Score format
        score_format_map = {"absolute": 0, "away": 1}
        score_format_index = score_format_map.get(self.settings.score_format, 0)
        self.cmb_score_format.setCurrentIndex(score_format_index)
        self.chk_interactive_moves.setChecked(self.settings.interactive_moves)
        self.chk_preview_moves.setChecked(self.settings.preview_moves_before_submit)

        # Max moves dropdown (index is value minus 2)
        self.cmb_max_moves.setCurrentIndex(self.settings.max_moves - 2)

        # Initialize preview enabled state based on show options checkbox
        self._on_show_options_toggled_preview(self.settings.show_options)

        # GnuBG
        if self.settings.gnubg_path:
            self.txt_gnubg_path.setText(self.settings.gnubg_path)
        self.cmb_gnubg_ply.setCurrentIndex(self.settings.gnubg_analysis_ply)
        self.chk_generate_score_matrix.setChecked(self.settings.generate_score_matrix)
        self.chk_generate_move_score_matrix.setChecked(self.settings.generate_move_score_matrix)
        self._update_gnubg_status()

    def _browse_gnubg(self):
        """Browse for GnuBG executable."""
        # Platform-specific file filter
        if sys.platform == 'win32':
            file_filter = "Executables (*.exe);;All Files (*)"
        else:
            file_filter = "All Files (*)"

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select GnuBG Executable",
            "",
            file_filter
        )
        if file_path:
            self.txt_gnubg_path.setText(file_path)
            self._update_gnubg_status()

    def _update_gnubg_status(self):
        """Update GnuBG status label asynchronously."""
        # Cancel any running validation
        if self.validation_worker and self.validation_worker.isRunning():
            self.validation_worker.quit()
            self.validation_worker.wait()

        path = self.txt_gnubg_path.text()
        if not path:
            self.lbl_gnubg_status_icon.setPixmap(qta.icon('fa6s.circle', color='#6c7086').pixmap(18, 18))
            self.lbl_gnubg_status_text.setText("Not configured")
            self.lbl_gnubg_status_text.setStyleSheet("")
            return

        # Show loading state
        self.lbl_gnubg_status_icon.setPixmap(qta.icon('fa6s.spinner', color='#6c7086').pixmap(18, 18))
        self.lbl_gnubg_status_text.setText("Validating...")
        self.lbl_gnubg_status_text.setStyleSheet("color: gray;")

        # Start validation in background thread
        self.validation_worker = GnuBGValidationWorker(path)
        self.validation_worker.validation_complete.connect(self._on_validation_complete)
        self.validation_worker.start()

    def _on_validation_complete(self, status_text: str, status_type: str):
        """Handle validation completion."""
        # Determine icon based on status type
        if status_type == "valid":
            icon = qta.icon('fa6s.circle-check', color='#a6e3a1')
        elif status_type == "warning":
            icon = qta.icon('fa6s.triangle-exclamation', color='#fab387')
        elif status_type == "error":
            icon = qta.icon('fa6s.circle-xmark', color='#f38ba8')
        else:
            icon = None

        # Set icon and text separately
        if icon:
            self.lbl_gnubg_status_icon.setPixmap(icon.pixmap(18, 18))
        self.lbl_gnubg_status_text.setText(status_text)
        self.lbl_gnubg_status_text.setStyleSheet("")

    def _on_show_options_toggled_preview(self, checked: bool):
        """Enable/disable preview checkbox based on show options checkbox."""
        self.chk_preview_moves.setEnabled(checked)

        # Add visual feedback for disabled state - gray out text and indicator
        if checked:
            self.chk_preview_moves.setStyleSheet("")
        else:
            # Gray out text and change checkbox indicator color to gray
            self.chk_preview_moves.setStyleSheet("""
                QCheckBox {
                    color: #6c7086;
                }
                QCheckBox::indicator:checked:disabled {
                    background-color: #6c7086;
                    border-color: #6c7086;
                }
                QCheckBox::indicator:unchecked:disabled {
                    border-color: #6c7086;
                }
            """)

    def accept(self):
        """Save settings and close dialog."""
        # Update settings object
        self.settings.deck_name = self.txt_deck_name.text()
        self.settings.use_subdecks_by_type = self.chk_use_subdecks.isChecked()
        self.settings.clear_positions_after_export = self.chk_clear_after_export.isChecked()
        self.settings.export_method = (
            "ankiconnect" if self.cmb_export_method.currentIndex() == 0 else "apkg"
        )
        self.settings.color_scheme = self.cmb_color_scheme.currentText()
        self.settings.swap_checker_colors = self.chk_swap_checker_colors.isChecked()
        self.settings.board_orientation = self.cmb_board_orientation.currentData()
        self.settings.show_options = self.chk_show_options.isChecked()
        self.settings.show_pip_count = self.chk_show_pip_count.isChecked()
        self.settings.score_format = self.cmb_score_format.currentData()
        self.settings.interactive_moves = self.chk_interactive_moves.isChecked()
        self.settings.preview_moves_before_submit = self.chk_preview_moves.isChecked()
        self.settings.max_moves = self.cmb_max_moves.currentIndex() + 2
        self.settings.gnubg_path = self.txt_gnubg_path.text() or None
        self.settings.gnubg_analysis_ply = self.cmb_gnubg_ply.currentIndex()
        self.settings.generate_score_matrix = self.chk_generate_score_matrix.isChecked()
        self.settings.generate_move_score_matrix = self.chk_generate_move_score_matrix.isChecked()

        # Emit signal
        self.settings_changed.emit(self.settings)

        super().accept()

    def reject(self):
        """Restore original settings and close dialog."""
        # Clean up validation worker
        if self.validation_worker and self.validation_worker.isRunning():
            self.validation_worker.quit()
            self.validation_worker.wait()
        # Don't modify settings object
        super().reject()

    def closeEvent(self, event):
        """Clean up when dialog is closed."""
        # Clean up validation worker
        if self.validation_worker and self.validation_worker.isRunning():
            self.validation_worker.quit()
            self.validation_worker.wait()
        super().closeEvent(event)
