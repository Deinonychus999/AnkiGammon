"""
Settings configuration dialog.
"""

from typing import Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QCheckBox, QLineEdit, QPushButton,
    QGroupBox, QFileDialog, QLabel, QDialogButtonBox
)
from PySide6.QtCore import Qt, Signal

from xg2anki.settings import Settings
from xg2anki.renderer.color_schemes import list_schemes


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

        # Color scheme
        self.cmb_color_scheme = QComboBox()
        self.cmb_color_scheme.addItems(list_schemes())
        form.addRow("Board Color Scheme:", self.cmb_color_scheme)

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
        self._update_gnubg_status()

    def _browse_gnubg(self):
        """Browse for GnuBG executable."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select GnuBG Executable",
            "",
            "Executables (*.exe);;All Files (*)"
        )
        if file_path:
            self.txt_gnubg_path.setText(file_path)
            self._update_gnubg_status()

    def _update_gnubg_status(self):
        """Update GnuBG status label."""
        # TODO: Validate GnuBG path
        path = self.txt_gnubg_path.text()
        if path:
            self.lbl_gnubg_status.setText("Not validated")
        else:
            self.lbl_gnubg_status.setText("Not configured")

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

        # Emit signal
        self.settings_changed.emit(self.settings)

        super().accept()

    def reject(self):
        """Restore original settings and close dialog."""
        # Don't modify settings object
        super().reject()
