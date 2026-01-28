"""
Dialog for regenerating existing AnkiGammon cards in Anki.

Fetches all cards tagged 'ankigammon' from Anki via AnkiConnect,
re-analyzes their positions with GnuBG, regenerates card HTML
with current settings, and updates the notes in place.
"""

from pathlib import Path
from typing import List

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar,
    QPushButton, QTextEdit, QDialogButtonBox
)
from PySide6.QtCore import Qt, QThread, Signal, Slot

from ankigammon.anki.ankiconnect import AnkiConnect
from ankigammon.anki.card_styles import MODEL_NAME
from ankigammon.settings import Settings


class RegenerateWorker(QThread):
    """
    Background thread for regenerating existing AnkiGammon cards.

    Signals:
        progress(int, int): current, total
        status_message(str): status update
        finished(bool, str): success, message
    """

    progress = Signal(int, int)
    status_message = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self._cancelled = False

    def cancel(self):
        """Request cancellation."""
        self._cancelled = True

    def run(self):
        """Regenerate all AnkiGammon cards in Anki."""
        try:
            self._do_regenerate()
        except InterruptedError:
            self.finished.emit(False, "Regeneration cancelled by user")
        except Exception as e:
            self.finished.emit(False, f"Regeneration failed: {str(e)}")

    def _do_regenerate(self):
        """Core regeneration logic."""
        from ankigammon.utils.gnubg_analyzer import GNUBGAnalyzer
        from ankigammon.parsers.gnubg_parser import GNUBGParser
        from ankigammon.anki.card_generator import CardGenerator
        from ankigammon.renderer.svg_board_renderer import SVGBoardRenderer
        from ankigammon.renderer.color_schemes import SCHEMES

        # 1. Connect to AnkiConnect
        self.status_message.emit("Connecting to Anki...")
        client = AnkiConnect(deck_name=self.settings.deck_name)
        if not client.test_connection():
            self.finished.emit(
                False,
                "Could not connect to Anki. Is Anki running with AnkiConnect installed?"
            )
            return
        client.create_model()

        # 2. Find all AnkiGammon notes by tag
        if self._cancelled:
            self.finished.emit(False, "Cancelled by user")
            return
        self.status_message.emit("Finding AnkiGammon notes...")
        all_note_ids = client.invoke('findNotes', query='tag:ankigammon')
        if not all_note_ids:
            self.finished.emit(True, "No AnkiGammon notes found in Anki.")
            return

        # 3. Get note info and extract XGIDs
        self.status_message.emit(f"Reading {len(all_note_ids)} note(s)...")
        notes_data = client.notes_info(all_note_ids)

        note_xgid_pairs: List[tuple] = []
        for note_data in notes_data:
            note_id = note_data['noteId']
            xgid_field = note_data.get('fields', {}).get('XGID', {})
            xgid = xgid_field.get('value', '').strip()
            if xgid:
                note_xgid_pairs.append((note_id, xgid))

        if not note_xgid_pairs:
            self.finished.emit(True, "No notes with XGID values found. Cannot regenerate.")
            return

        total = len(note_xgid_pairs)
        self.status_message.emit(f"Found {total} note(s) with positions to regenerate.")

        # 4. Deduplicate XGIDs for efficient analysis
        unique_xgids = list(dict.fromkeys(xgid for _, xgid in note_xgid_pairs))

        # 5. Analyze with GnuBG
        if self._cancelled:
            self.finished.emit(False, "Cancelled by user")
            return

        analyzer = GNUBGAnalyzer(
            gnubg_path=self.settings.gnubg_path,
            analysis_ply=self.settings.gnubg_analysis_ply
        )

        def analysis_progress(completed: int, total_positions: int):
            if self._cancelled:
                return
            self.progress.emit(completed, total_positions * 2)
            self.status_message.emit(
                f"Analyzing position {completed}/{total_positions} with GnuBG "
                f"({self.settings.gnubg_analysis_ply}-ply)..."
            )

        self.status_message.emit(
            f"Analyzing {len(unique_xgids)} unique position(s) with GnuBG "
            f"({self.settings.gnubg_analysis_ply}-ply)..."
        )
        analysis_results = analyzer.analyze_positions_parallel(
            unique_xgids,
            progress_callback=analysis_progress
        )

        if self._cancelled:
            self.finished.emit(False, "Cancelled by user")
            return

        # 6. Parse into Decisions
        self.status_message.emit("Parsing analysis results...")
        xgid_to_decision = {}
        for xgid, (gnubg_output, decision_type) in zip(unique_xgids, analysis_results):
            decision = GNUBGParser.parse_analysis(gnubg_output, xgid, decision_type)
            ply = self.settings.gnubg_analysis_ply
            decision.source_description = f"Regenerated with GnuBG ({ply}-ply)"
            xgid_to_decision[xgid] = decision

        # 7. Regenerate card HTML and update notes
        color_scheme = SCHEMES.get(self.settings.color_scheme, SCHEMES['classic'])
        if self.settings.swap_checker_colors:
            color_scheme = color_scheme.with_swapped_checkers()
        renderer = SVGBoardRenderer(
            color_scheme=color_scheme,
            orientation=self.settings.board_orientation
        )
        output_dir = Path.home() / '.ankigammon' / 'cards'

        updated = 0
        errors = 0
        for i, (note_id, xgid) in enumerate(note_xgid_pairs):
            if self._cancelled:
                self.finished.emit(False, f"Cancelled after updating {updated} card(s)")
                return

            self.progress.emit(total + i, total * 2)
            self.status_message.emit(f"Regenerating card {i + 1}/{total}...")

            try:
                decision = xgid_to_decision[xgid]
                card_gen = CardGenerator(
                    output_dir=output_dir,
                    show_options=self.settings.show_options,
                    interactive_moves=self.settings.interactive_moves,
                    renderer=renderer,
                )
                card_data = card_gen.generate_card(decision)

                client.update_note_fields(
                    note_id,
                    card_data['front'],
                    card_data['back'],
                    card_data.get('xgid', '')
                )
                client.update_note_tags(note_id, card_data.get('tags', []))
                updated += 1
            except Exception as e:
                self.status_message.emit(f"Warning: Failed to update note {note_id}: {e}")
                errors += 1

        self.progress.emit(total * 2, total * 2)

        # 8. Summary
        msg = f"Successfully regenerated {updated} card(s) in Anki"
        if errors > 0:
            msg += f" ({errors} failed)"
        self.finished.emit(True, msg)


class RegenerateDialog(QDialog):
    """Dialog for regenerating existing AnkiGammon cards in Anki."""

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.worker = None
        self._closing = False

        self.setWindowTitle("Regenerate Cards in Anki")
        self.setModal(True)
        self.setMinimumWidth(500)

        self._setup_ui()

    def _setup_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        # Info label
        info = QLabel("Regenerate all AnkiGammon cards in Anki")
        info.setStyleSheet("font-size: 13px; color: #a6adc8; margin-bottom: 4px;")
        layout.addWidget(info)

        # Description
        desc = QLabel(
            "All notes tagged <b>ankigammon</b> will be re-analyzed with GnuBG "
            "and updated with the current settings (color scheme, card layout, etc.)."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(
            "padding: 12px 16px; background-color: rgba(137, 180, 250, 0.08); "
            "border-radius: 8px; color: #cdd6f4;"
        )
        layout.addWidget(desc)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Ready to regenerate cards.")
        layout.addWidget(self.status_label)

        # Log text (hidden initially)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.log_text.hide()
        layout.addWidget(self.log_text)

        # Buttons
        self.button_box = QDialogButtonBox()
        self.btn_regenerate = QPushButton("Regenerate")
        self.btn_regenerate.setCursor(Qt.PointingHandCursor)
        self.btn_regenerate.clicked.connect(self.start_regenerate)
        self.btn_close = QPushButton("Cancel")
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.clicked.connect(self.close_dialog)

        self.button_box.addButton(self.btn_regenerate, QDialogButtonBox.AcceptRole)
        self.button_box.addButton(self.btn_close, QDialogButtonBox.RejectRole)
        layout.addWidget(self.button_box)

    def closeEvent(self, event):
        """Handle window close event."""
        if self.worker and self.worker.isRunning():
            self._closing = True
            self.btn_close.setEnabled(False)
            self.worker.cancel()
            self.status_label.setText("Cancelling...")
            event.ignore()
            return
        event.accept()

    @Slot()
    def close_dialog(self):
        """Handle close button click."""
        if self.worker and self.worker.isRunning():
            self._closing = True
            self.btn_close.setEnabled(False)
            self.worker.cancel()
            self.status_label.setText("Cancelling...")
            return
        self.reject()

    @Slot()
    def start_regenerate(self):
        """Start regeneration in background thread."""
        # Check GnuBG availability
        if not self.settings.is_gnubg_available():
            self.status_label.setText(
                "GnuBG is required for regeneration. "
                "Please configure it in Settings."
            )
            return

        self.btn_regenerate.setEnabled(False)
        self.status_label.setText("Starting regeneration...")

        self.worker = RegenerateWorker(self.settings)
        self.worker.progress.connect(self.on_progress)
        self.worker.status_message.connect(self.on_status_message)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    @Slot(int, int)
    def on_progress(self, current, total):
        """Update progress bar."""
        if total > 0:
            self.progress_bar.setValue(int((current / total) * 100))

    @Slot(str)
    def on_status_message(self, message):
        """Update status label and log."""
        self.status_label.setText(message)
        self.log_text.append(message)
        if self.log_text.isHidden():
            self.log_text.show()

    @Slot(bool, str)
    def on_finished(self, success, message):
        """Handle completion."""
        if self._closing:
            self.reject()
            return

        self.status_label.setText(message)
        self.log_text.append(f"\n{'SUCCESS' if success else 'FAILED'}: {message}")

        if success:
            self.btn_regenerate.hide()
            self.btn_close.setText("Done")
        else:
            self.btn_regenerate.setEnabled(True)
