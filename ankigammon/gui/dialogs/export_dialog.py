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

from ankigammon.models import Decision
from ankigammon.anki.ankiconnect import AnkiConnect
from ankigammon.anki.apkg_exporter import ApkgExporter
from ankigammon.anki.card_generator import CardGenerator
from ankigammon.renderer.svg_board_renderer import SVGBoardRenderer
from ankigammon.renderer.color_schemes import SCHEMES
from ankigammon.settings import Settings
from ankigammon.utils.gnubg_analyzer import GNUBGAnalyzer
from ankigammon.parsers.gnubg_parser import GNUBGParser


class AnalysisWorker(QThread):
    """
    Background thread for GnuBG analysis of positions.

    Signals:
        progress(int, int): current, total
        status_message(str): status update
        finished(bool, str, List[Decision]): success, message, analyzed_decisions
    """

    progress = Signal(int, int)
    status_message = Signal(str)
    finished = Signal(bool, str, list)

    def __init__(self, decisions: List[Decision], settings: Settings):
        super().__init__()
        self.decisions = decisions
        self.settings = settings

    def run(self):
        """Analyze positions with GnuBG in background."""
        try:
            analyzer = GNUBGAnalyzer(
                gnubg_path=self.settings.gnubg_path,
                analysis_ply=self.settings.gnubg_analysis_ply
            )

            # Find positions that need analysis
            positions_to_analyze = [(i, d) for i, d in enumerate(self.decisions) if not d.candidate_moves]
            total = len(positions_to_analyze)

            if total == 0:
                self.finished.emit(True, "No analysis needed", self.decisions)
                return

            analyzed_decisions = list(self.decisions)  # Copy list

            for idx, (pos_idx, decision) in enumerate(positions_to_analyze):
                self.progress.emit(idx, total)  # Emit current progress before starting
                self.status_message.emit(
                    f"Analyzing position {idx + 1} of {total} with GnuBG ({self.settings.gnubg_analysis_ply}-ply)..."
                )

                # Analyze with GnuBG
                gnubg_output, decision_type = analyzer.analyze_position(decision.xgid)
                analyzed_decision = GNUBGParser.parse_analysis(
                    gnubg_output,
                    decision.xgid,
                    decision_type
                )

                # Preserve user-added metadata from original decision
                analyzed_decision.note = decision.note
                analyzed_decision.source_file = decision.source_file
                analyzed_decision.game_number = decision.game_number
                analyzed_decision.move_number = decision.move_number
                analyzed_decision.position_image_path = decision.position_image_path

                analyzed_decisions[pos_idx] = analyzed_decision

                # Emit progress after completing this position
                self.progress.emit(idx + 1, total)

            self.finished.emit(True, f"Analyzed {total} position(s)", analyzed_decisions)

        except Exception as e:
            self.finished.emit(False, f"Analysis failed: {str(e)}", self.decisions)


class ExportWorker(QThread):
    """
    Background thread for export operations.

    Signals:
        progress(float): progress as percentage (0.0 to 1.0)
        status_message(str): status update
        finished(bool, str): success, message
    """

    progress = Signal(float)
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
        self.progress.emit(0.0)

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

        # Create renderer with color scheme and orientation
        color_scheme = SCHEMES.get(self.settings.color_scheme, SCHEMES['classic'])
        renderer = SVGBoardRenderer(
            color_scheme=color_scheme,
            orientation=self.settings.board_orientation
        )

        # Export decisions
        total = len(self.decisions)
        for i, decision in enumerate(self.decisions):
            # Calculate base progress for this position
            base_progress = i / total
            position_progress_range = 1.0 / total  # How much progress this position represents

            # Estimate sub-steps (used for progress bar calculation)
            # Steps: render positions (1), score matrix (N cells), generate card (1)
            has_score_matrix = (
                decision.decision_type.name == 'CUBE_ACTION' and
                decision.match_length > 0 and
                self.settings.get('generate_score_matrix', False) and
                self.settings.is_gnubg_available()
            )
            matrix_steps = (decision.match_length - 1) ** 2 if has_score_matrix else 0
            total_substeps = 2 + matrix_steps  # render + matrix + generate card

            current_substep = [0]  # Use list for mutable counter in nested function

            # Progress callback for sub-steps
            def progress_callback(message: str):
                current_substep[0] += 1
                # Calculate progress within this position
                substep_progress = min(current_substep[0] / total_substeps, 0.95)  # Cap at 95% until Anki add
                overall_progress = base_progress + (substep_progress * position_progress_range)
                self.progress.emit(overall_progress)
                self.status_message.emit(f"Position {i+1}/{total}: {message}")

            # Create card generator with progress callback
            output_dir = Path.home() / '.ankigammon' / 'cards'
            card_gen = CardGenerator(
                output_dir=output_dir,
                show_options=self.settings.show_options,
                interactive_moves=self.settings.interactive_moves,
                renderer=renderer,
                progress_callback=progress_callback
            )

            self.progress.emit(base_progress)

            # Generate card (progress_callback will emit sub-steps and update progress)
            card_data = card_gen.generate_card(decision)

            # Add to Anki
            self.status_message.emit(f"Position {i+1}/{total}: Adding to Anki...")
            self.progress.emit(base_progress + (0.95 * position_progress_range))
            try:
                client.add_note(
                    front=card_data['front'],
                    back=card_data['back'],
                    tags=card_data.get('tags', [])
                )
            except Exception as e:
                self.finished.emit(False, f"Failed to add card {i+1}: {str(e)}")
                return

            # Update progress after card is successfully added
            self.progress.emit((i + 1) / total)

        self.finished.emit(True, f"Successfully exported {total} card(s) to Anki")

    def _export_apkg(self):
        """Export to APKG file."""
        self.status_message.emit("Generating APKG file...")
        self.progress.emit(0.0)

        if not self.output_path:
            self.finished.emit(False, "No output path specified for APKG export")
            return

        try:
            # Use existing APKG exporter
            output_dir = Path.home() / '.ankigammon' / 'cards'
            exporter = ApkgExporter(
                output_dir=output_dir,
                deck_name=self.settings.deck_name
            )

            # Custom export loop with progress tracking
            from ankigammon.renderer.color_schemes import get_scheme
            from ankigammon.renderer.svg_board_renderer import SVGBoardRenderer
            from ankigammon.anki.card_generator import CardGenerator
            import genanki

            scheme = get_scheme(self.settings.color_scheme)
            renderer = SVGBoardRenderer(
                color_scheme=scheme,
                orientation=self.settings.board_orientation
            )

            # Generate cards
            total = len(self.decisions)
            for i, decision in enumerate(self.decisions):
                # Calculate base progress for this position
                base_progress = i / total
                position_progress_range = 1.0 / total

                # Estimate sub-steps (same logic as AnkiConnect)
                has_score_matrix = (
                    decision.decision_type.name == 'CUBE_ACTION' and
                    decision.match_length > 0 and
                    self.settings.get('generate_score_matrix', False) and
                    self.settings.is_gnubg_available()
                )
                matrix_steps = (decision.match_length - 1) ** 2 if has_score_matrix else 0
                total_substeps = 2 + matrix_steps  # render + matrix + generate card

                current_substep = [0]

                # Progress callback for sub-steps
                def apkg_progress_callback(message: str):
                    current_substep[0] += 1
                    substep_progress = min(current_substep[0] / total_substeps, 0.95)
                    overall_progress = base_progress + (substep_progress * position_progress_range)
                    self.progress.emit(overall_progress)
                    self.status_message.emit(f"Position {i+1}/{total}: {message}")

                # Create card generator with progress callback
                card_gen = CardGenerator(
                    output_dir=output_dir,
                    show_options=self.settings.show_options,
                    interactive_moves=self.settings.interactive_moves,
                    renderer=renderer,
                    progress_callback=apkg_progress_callback
                )

                self.progress.emit(base_progress)

                # Generate card
                card_data = card_gen.generate_card(decision, card_id=f"card_{i}")

                # Create note
                note = genanki.Note(
                    model=exporter.model,
                    fields=[card_data['front'], card_data['back']],
                    tags=card_data['tags']
                )

                # Add to deck
                exporter.deck.add_note(note)

                # Update progress after card added
                self.progress.emit((i + 1) / total)

            # Write APKG file
            self.status_message.emit("Writing APKG file...")
            package = genanki.Package(exporter.deck)
            package.write_to_file(str(self.output_path))

            self.progress.emit(1.0)
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
        self.analysis_worker = None

        self.setWindowTitle("Export to Anki")
        self.setModal(True)
        self.setMinimumWidth(500)

        self._setup_ui()

    def _setup_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        # Info label with deck name
        info = QLabel(f"Exporting {len(self.decisions)} position(s)")
        info.setStyleSheet("font-size: 13px; color: #a6adc8; margin-bottom: 4px;")
        layout.addWidget(info)

        # Deck name label (modern styling)
        deck_label = QLabel(f"<span style='font-size: 16px; font-weight: 600; color: #cdd6f4;'>{self.settings.deck_name}</span>")
        deck_label.setStyleSheet("padding: 12px 16px; background-color: rgba(137, 180, 250, 0.08); border-radius: 8px;")
        layout.addWidget(deck_label)

        # Progress bar (use percentage-based progress)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel(f"Ready to export {len(self.decisions)} position(s) to deck {self.settings.deck_name}")
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
        self.btn_export = QPushButton("Export")
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.clicked.connect(self.start_export)
        self.btn_close = QPushButton("Close")
        self.btn_close.setCursor(Qt.PointingHandCursor)
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
        self.output_path = None
        if self.settings.export_method == "apkg":
            # Use last directory if available, otherwise use home directory
            if self.settings.last_apkg_directory:
                default_path = Path(self.settings.last_apkg_directory) / f"{self.settings.deck_name}.apkg"
            else:
                default_path = Path.home() / f"{self.settings.deck_name}.apkg"

            self.output_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save APKG File",
                str(default_path),
                "Anki Deck Package (*.apkg)"
            )
            if not self.output_path:
                self.btn_export.setEnabled(True)
                return

            # Save the directory for next time
            self.settings.last_apkg_directory = str(Path(self.output_path).parent)

        # Check if any positions need GnuBG analysis
        needs_analysis = [d for d in self.decisions if not d.candidate_moves]

        if needs_analysis:
            # Run analysis first
            self.status_label.setText(f"Analyzing {len(needs_analysis)} position(s) with GnuBG...")
            self.analysis_worker = AnalysisWorker(self.decisions, self.settings)
            self.analysis_worker.progress.connect(self.on_analysis_progress)
            self.analysis_worker.status_message.connect(self.on_status_message)
            self.analysis_worker.finished.connect(self.on_analysis_finished)
            self.analysis_worker.start()
        else:
            # No analysis needed, proceed with export
            self._start_export_worker()

    def _start_export_worker(self):
        """Start the actual export worker (after analysis if needed)."""
        # Create worker thread
        self.worker = ExportWorker(
            self.decisions,
            self.settings,
            self.settings.export_method,
            self.output_path
        )

        # Connect signals
        self.worker.progress.connect(self.on_progress)
        self.worker.status_message.connect(self.on_status_message)
        self.worker.finished.connect(self.on_finished)

        # Start export
        self.worker.start()

    @Slot(int, int)
    def on_analysis_progress(self, current, total):
        """Update progress bar for analysis (0-50% of total progress)."""
        # Analysis takes first half of progress bar (0-50%)
        self.progress_bar.setValue(int((current / total) * 50))

    @Slot(bool, str, list)
    def on_analysis_finished(self, success, message, analyzed_decisions):
        """Handle analysis completion."""
        if success:
            # Update decisions with analyzed versions
            self.decisions = analyzed_decisions
            self.status_label.setText(f"{message} - Starting export...")
            # Proceed with export
            self._start_export_worker()
        else:
            # Analysis failed
            self.status_label.setText(f"Analysis failed: {message}")
            self.log_text.append(f"ERROR: {message}")
            self.btn_export.setEnabled(True)
            self.btn_close.setEnabled(True)

    @Slot(float)
    def on_progress(self, progress_fraction):
        """Update progress bar for export (50-100% of total progress).

        Args:
            progress_fraction: Progress as a fraction from 0.0 to 1.0
        """
        # Export takes second half of progress bar (50-100%)
        # If no analysis was needed, this will go from 0-100% as expected
        # If analysis was performed, this will go from 50-100%
        if hasattr(self, 'analysis_worker') and self.analysis_worker is not None:
            # Analysis was performed, map 0.0-1.0 to 50-100%
            self.progress_bar.setValue(50 + int(progress_fraction * 50))
        else:
            # No analysis, map 0.0-1.0 to 0-100%
            self.progress_bar.setValue(int(progress_fraction * 100))

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
