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
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QCheckBox, QLineEdit, QPushButton,
    QGroupBox, QFileDialog, QLabel, QDialogButtonBox
)
from PySide6.QtCore import Qt, Signal, QThread

from flashgammon.settings import Settings
from flashgammon.renderer.color_schemes import list_schemes


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

            # Try to run gnubg with -t (text mode) and -c (command file)
            result = subprocess.run(
                [str(self.gnubg_path), "-t", "-c", command_file],
                capture_output=True,
                text=True,
                timeout=5
            )

            # Check if it's actually GNU Backgammon
            output = result.stdout + result.stderr
            if "GNU Backgammon" in output or result.returncode == 0:
                # Check if it's the GUI version (which may not work properly on Windows)
                # Use stem to get filename without extension (works cross-platform)
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
        self.original_settings.deck_name = settings.deck_name
        self.original_settings.show_options = settings.show_options
        self.original_settings.interactive_moves = settings.interactive_moves
        self.original_settings.export_method = settings.export_method
        self.original_settings.gnubg_path = settings.gnubg_path
        self.original_settings.gnubg_analysis_ply = settings.gnubg_analysis_ply
        self.original_settings.generate_score_matrix = settings.generate_score_matrix

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

        # Anki settings group
        anki_group = self._create_anki_group()
        layout.addWidget(anki_group)

        # Card settings group
        card_group = self._create_card_group()
        layout.addWidget(card_group)

        # GnuBG settings group
        gnubg_group = self._create_gnubg_group()
        layout.addWidget(gnubg_group)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
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
        form.addRow("Default Export Method:", self.cmb_export_method)

        return group

    def _create_card_group(self) -> QGroupBox:
        """Create card settings group."""
        group = QGroupBox("Card Appearance")
        form = QFormLayout(group)

        # Board theme
        self.cmb_color_scheme = QComboBox()
        self.cmb_color_scheme.addItems(list_schemes())
        form.addRow("Board Theme:", self.cmb_color_scheme)

        # Show options
        self.chk_show_options = QCheckBox("Show multiple choice options on card front")
        form.addRow(self.chk_show_options)

        # Interactive moves
        self.chk_interactive_moves = QCheckBox("Enable interactive move visualization")
        form.addRow(self.chk_interactive_moves)

        return group

    def _create_gnubg_group(self) -> QGroupBox:
        """Create GnuBG settings group."""
        group = QGroupBox("GnuBG Integration (Optional)")
        form = QFormLayout(group)

        # GnuBG path
        path_layout = QHBoxLayout()
        self.txt_gnubg_path = QLineEdit()
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse_gnubg)
        path_layout.addWidget(self.txt_gnubg_path)
        path_layout.addWidget(btn_browse)
        form.addRow("GnuBG Path:", path_layout)

        # Analysis depth
        self.cmb_gnubg_ply = QComboBox()
        self.cmb_gnubg_ply.addItems(["0", "1", "2", "3"])
        form.addRow("Analysis Depth (ply):", self.cmb_gnubg_ply)

        # Score matrix generation
        self.chk_generate_score_matrix = QCheckBox("Generate score matrix for cube decisions")
        form.addRow(self.chk_generate_score_matrix)

        # Status label
        self.lbl_gnubg_status = QLabel()
        form.addRow("Status:", self.lbl_gnubg_status)

        return group

    def _load_settings(self):
        """Load current settings into widgets."""
        self.txt_deck_name.setText(self.settings.deck_name)

        # Export method
        method_index = 0 if self.settings.export_method == "ankiconnect" else 1
        self.cmb_export_method.setCurrentIndex(method_index)

        # Color scheme
        scheme_index = list_schemes().index(self.settings.color_scheme)
        self.cmb_color_scheme.setCurrentIndex(scheme_index)

        self.chk_show_options.setChecked(self.settings.show_options)
        self.chk_interactive_moves.setChecked(self.settings.interactive_moves)

        # GnuBG
        if self.settings.gnubg_path:
            self.txt_gnubg_path.setText(self.settings.gnubg_path)
        self.cmb_gnubg_ply.setCurrentIndex(self.settings.gnubg_analysis_ply)
        self.chk_generate_score_matrix.setChecked(self.settings.generate_score_matrix)
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
            self.lbl_gnubg_status.setText("  Not configured")
            self.lbl_gnubg_status.setStyleSheet("")
            self.lbl_gnubg_status.setPixmap(qta.icon('fa6s.circle', color='#6c7086').pixmap(18, 18))
            return

        # Show loading state
        self.lbl_gnubg_status.setText("    Validating...")
        self.lbl_gnubg_status.setStyleSheet("color: gray;")
        self.lbl_gnubg_status.setPixmap(qta.icon('fa6s.spinner', color='#6c7086').pixmap(18, 18))

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

        # Set icon and text
        if icon:
            self.lbl_gnubg_status.setPixmap(icon.pixmap(18, 18))
        self.lbl_gnubg_status.setText(f"    {status_text}")
        self.lbl_gnubg_status.setStyleSheet("")

    def accept(self):
        """Save settings and close dialog."""
        # Update settings object
        self.settings.deck_name = self.txt_deck_name.text()
        self.settings.export_method = (
            "ankiconnect" if self.cmb_export_method.currentIndex() == 0 else "apkg"
        )
        self.settings.color_scheme = self.cmb_color_scheme.currentText()
        self.settings.show_options = self.chk_show_options.isChecked()
        self.settings.interactive_moves = self.chk_interactive_moves.isChecked()
        self.settings.gnubg_path = self.txt_gnubg_path.text() or None
        self.settings.gnubg_analysis_ply = self.cmb_gnubg_ply.currentIndex()
        self.settings.generate_score_matrix = self.chk_generate_score_matrix.isChecked()

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
