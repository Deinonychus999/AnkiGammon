"""
Export progress dialog with AnkiConnect/APKG support.
"""

from typing import List
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar,
    QPushButton, QTextEdit, QDialogButtonBox, QFileDialog
)
from PySide6.QtCore import Qt, QThread, Signal, Slot

from flashgammon.models import Decision
from flashgammon.anki.ankiconnect import AnkiConnect
from flashgammon.anki.apkg_exporter import ApkgExporter
from flashgammon.anki.card_generator import CardGenerator
from flashgammon.renderer.svg_board_renderer import SVGBoardRenderer
from flashgammon.renderer.color_schemes import SCHEMES
from flashgammon.settings import Settings


class ExportWorker(QThread):
    """
    Background thread for export operations.

    Signals:
        progress(int, int): current, total
        status_message(str): status update
        finished(bool, str): success, message
    """

    progress = Signal(int, int)
    status_message = Signal(str)
    finished = Signal(bool, str)

    def __init__(
        self,
        decisions: List[Decision],
        settings: Settings,
        export_method: str,
        output_path: str = None
    ):
        super().__init__()
        self.decisions = decisions
        self.settings = settings
        self.export_method = export_method
        self.output_path = output_path

    def run(self):
        """Execute export in background thread."""
        try:
            if self.export_method == "ankiconnect":
                self._export_ankiconnect()
            else:
                self._export_apkg()
        except Exception as e:
            self.finished.emit(False, f"Export failed: {str(e)}")

    def _export_ankiconnect(self):
        """Export via AnkiConnect."""
        self.status_message.emit("Connecting to Anki...")

        # Test connection
        client = AnkiConnect(deck_name=self.settings.deck_name)
        if not client.test_connection():
            self.finished.emit(False, "Could not connect to Anki. Is Anki running with AnkiConnect installed?")
            return

        # Create model and deck if needed
        self.status_message.emit("Setting up Anki deck...")
        try:
            client.create_model()
            client.create_deck()
        except Exception as e:
            self.finished.emit(False, f"Failed to setup Anki deck: {str(e)}")
            return

        # Generate cards
        self.status_message.emit("Generating cards...")

        # Create renderer with color scheme
        color_scheme = SCHEMES.get(self.settings.color_scheme, SCHEMES['classic'])
        renderer = SVGBoardRenderer(color_scheme=color_scheme)

        # Create card generator
        output_dir = Path.home() / '.flashgammon' / 'cards'
        card_gen = CardGenerator(
            output_dir=output_dir,
            show_options=self.settings.show_options,
            interactive_moves=self.settings.interactive_moves,
            renderer=renderer
        )

        # Export decisions
        total = len(self.decisions)
        for i, decision in enumerate(self.decisions):
            self.status_message.emit(f"Exporting position {i+1}/{total}...")
            self.progress.emit(i + 1, total)

            # Generate card
            card_data = card_gen.generate_card(decision)

            # Add to Anki
            try:
                client.add_note(
                    front=card_data['front'],
                    back=card_data['back'],
                    tags=card_data.get('tags', [])
                )
            except Exception as e:
                self.finished.emit(False, f"Failed to add card {i+1}: {str(e)}")
                return

        self.finished.emit(True, f"Successfully exported {total} card(s) to Anki")

    def _export_apkg(self):
        """Export to APKG file."""
        self.status_message.emit("Generating APKG file...")

        if not self.output_path:
            self.finished.emit(False, "No output path specified for APKG export")
            return

        try:
            # Use existing APKG exporter
            output_dir = Path.home() / '.flashgammon' / 'cards'
            exporter = ApkgExporter(
                output_dir=output_dir,
                deck_name=self.settings.deck_name
            )

            # Generate cards
            total = len(self.decisions)
            self.status_message.emit(f"Generating {total} card(s)...")
            self.progress.emit(0, total)

            exporter.export(
                decisions=self.decisions,
                output_file=self.output_path,
                color_scheme=self.settings.color_scheme,
                show_options=self.settings.show_options,
                interactive_moves=self.settings.interactive_moves
            )

            self.progress.emit(total, total)
            self.finished.emit(True, f"Successfully created {self.output_path}")
        except Exception as e:
            self.finished.emit(False, f"APKG export failed: {str(e)}")


class ExportDialog(QDialog):
    """Dialog for exporting positions to Anki."""

    def __init__(
        self,
        decisions: List[Decision],
        settings: Settings,
        parent=None
    ):
        super().__init__(parent)
        self.decisions = decisions
        self.settings = settings
        self.worker = None

        self.setWindowTitle("Export to Anki")
        self.setModal(True)
        self.setMinimumWidth(500)

        self._setup_ui()

    def _setup_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        # Info label
        info = QLabel(f"Exporting {len(self.decisions)} position(s) to Anki")
        layout.addWidget(info)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, len(self.decisions))
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Ready to export")
        layout.addWidget(self.status_label)

        # Log text (hidden initially)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.hide()
        layout.addWidget(self.log_text)

        # Buttons
        self.button_box = QDialogButtonBox()
        self.btn_export = QPushButton("Export")
        self.btn_export.clicked.connect(self.start_export)
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.reject)
        self.btn_close.setEnabled(False)

        self.button_box.addButton(self.btn_export, QDialogButtonBox.AcceptRole)
        self.button_box.addButton(self.btn_close, QDialogButtonBox.RejectRole)
        layout.addWidget(self.button_box)

    @Slot()
    def start_export(self):
        """Start export process in background thread."""
        self.btn_export.setEnabled(False)

        # Get output path for APKG if needed
        output_path = None
        if self.settings.export_method == "apkg":
            output_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save APKG File",
                str(Path.home() / f"{self.settings.deck_name}.apkg"),
                "Anki Deck Package (*.apkg)"
            )
            if not output_path:
                self.btn_export.setEnabled(True)
                return

        # Create worker thread
        self.worker = ExportWorker(
            self.decisions,
            self.settings,
            self.settings.export_method,
            output_path
        )

        # Connect signals
        self.worker.progress.connect(self.on_progress)
        self.worker.status_message.connect(self.on_status_message)
        self.worker.finished.connect(self.on_finished)

        # Start export
        self.worker.start()

    @Slot(int, int)
    def on_progress(self, current, total):
        """Update progress bar."""
        self.progress_bar.setValue(current)

    @Slot(str)
    def on_status_message(self, message):
        """Update status label."""
        self.status_label.setText(message)
        self.log_text.append(message)
        if self.log_text.isHidden():
            self.log_text.show()

    @Slot(bool, str)
    def on_finished(self, success, message):
        """Handle export completion."""
        self.status_label.setText(message)
        self.log_text.append(f"\n{'SUCCESS' if success else 'FAILED'}: {message}")

        self.btn_close.setEnabled(True)
        if success:
            self.btn_export.setEnabled(False)
        else:
            self.btn_export.setEnabled(True)  # Allow retry
