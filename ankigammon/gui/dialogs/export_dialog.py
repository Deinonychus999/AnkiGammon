"""
Export progress dialog with AnkiConnect/APKG support.
"""

from typing import Dict, List
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar,
    QPushButton, QTextEdit, QDialogButtonBox, QFileDialog
)
from PySide6.QtCore import Qt, QThread, Signal, Slot

from ankigammon.models import Decision
from ankigammon.anki.ankiconnect import AnkiConnect
from ankigammon.anki.apkg_exporter import ApkgExporter, StableNote, _deterministic_id
from ankigammon.anki.card_generator import CardGenerator
from ankigammon.anki.deck_utils import find_duplicate_xgids
from ankigammon.gui import silent_messagebox
from ankigammon.renderer.svg_board_renderer import SVGBoardRenderer
from ankigammon.renderer.color_schemes import SCHEMES
from ankigammon.settings import Settings
from ankigammon.utils.analyzer_base import create_analyzer
from PySide6.QtWidgets import QMessageBox


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
        self._cancelled = False
        self.analyzer = None  # Preserved for reuse by CardGenerator

    def cancel(self):
        """Request cancellation of the analysis."""
        self._cancelled = True

    def run(self):
        """Analyze positions in background (parallel processing)."""
        try:
            self.analyzer = create_analyzer(self.settings)
            analyzer = self.analyzer

            # Find positions that need analysis
            positions_to_analyze = [(i, d) for i, d in enumerate(self.decisions) if not d.candidate_moves]
            total = len(positions_to_analyze)

            if total == 0:
                self.finished.emit(True, "No analysis needed", self.decisions)
                return

            analyzed_decisions = list(self.decisions)  # Copy list

            # Prepare position IDs for batch analysis
            position_ids = [d.xgid for _, d in positions_to_analyze]

            # Progress callback for parallel analysis
            def progress_callback(completed: int, total_positions: int):
                if self._cancelled:
                    return
                self.progress.emit(completed, total_positions)
                if completed < total_positions:
                    self.status_message.emit(
                        f"Analyzing position {completed + 1} of {total_positions}..."
                    )

            # Analyze all positions
            self.status_message.emit(
                f"Starting analysis of {total} position(s)..."
            )
            analysis_results = analyzer.analyze_positions_parallel(
                position_ids,
                progress_callback=progress_callback,
                cancellation_callback=lambda: self._cancelled,
            )

            # Check for cancellation after batch completes
            if self._cancelled:
                self.finished.emit(False, "Analysis cancelled by user", self.decisions)
                return

            # Parse results and update decisions
            for idx, (pos_idx, decision) in enumerate(positions_to_analyze):
                raw_output, decision_type = analysis_results[idx]

                analyzed_decision = analyzer.parse_analysis(
                    raw_output,
                    decision.xgid,
                    decision_type
                )

                # Preserve user-added metadata from original decision
                analyzed_decision.note = decision.note
                analyzed_decision.source_file = decision.source_file
                analyzed_decision.game_number = decision.game_number
                analyzed_decision.move_number = decision.move_number
                analyzed_decision.position_image_path = decision.position_image_path
                analyzed_decision.original_position_format = decision.original_position_format

                # Set source description
                analyzer_type = getattr(self.settings, 'analyzer_type', 'gnubg')
                if analyzer_type == "xg":
                    level = self.settings.xg_analysis_level
                    engine_name = f"eXtreme Gammon ({level})"
                else:
                    ply_level = self.settings.gnubg_analysis_ply
                    engine_name = f"GnuBG ({ply_level}-ply)"
                format_name = decision.original_position_format or "XGID"
                analyzed_decision.source_description = f"Analyzed with {engine_name} from {format_name}"

                analyzed_decisions[pos_idx] = analyzed_decision

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
        grouped_decisions: Dict[str, List[Decision]],
        settings: Settings,
        export_method: str,
        output_path: str = None,
        import_mode: str = "add",
        analyzer=None,
    ):
        super().__init__()
        self.grouped_decisions = grouped_decisions
        self.all_decisions = [d for decs in grouped_decisions.values() for d in decs]
        self.settings = settings
        self.export_method = export_method
        self.output_path = output_path
        self.import_mode = import_mode
        self._cancelled = False
        self._analyzer = analyzer

    def cancel(self):
        """Request cancellation of the export."""
        self._cancelled = True

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

        # Apply type subdecks if enabled
        from ankigammon.anki.deck_utils import apply_type_subdecks
        export_groups = self.grouped_decisions
        if self.settings.use_subdecks_by_type:
            export_groups = apply_type_subdecks(export_groups)

        # Create model and decks if needed
        self.status_message.emit("Setting up Anki deck(s)...")
        try:
            client.create_model()

            # Create all needed decks upfront
            for deck_name in export_groups.keys():
                client.create_deck(deck_name)
        except Exception as e:
            self.finished.emit(False, f"Failed to setup Anki deck: {str(e)}")
            return

        # Generate cards
        self.status_message.emit("Generating cards...")

        # Create renderer with color scheme and orientation
        color_scheme = SCHEMES.get(self.settings.color_scheme, SCHEMES['classic'])
        if self.settings.swap_checker_colors:
            color_scheme = color_scheme.with_swapped_checkers()
        renderer = SVGBoardRenderer(
            color_scheme=color_scheme,
            orientation=self.settings.board_orientation
        )

        # Export decisions across all deck groups
        total = len(self.all_decisions)
        card_index = 0
        output_dir = Path.home() / '.ankigammon' / 'cards'
        card_gen = CardGenerator(
            output_dir=output_dir,
            show_options=self.settings.show_options,
            interactive_moves=self.settings.interactive_moves,
            renderer=renderer,
            cancellation_callback=lambda: self._cancelled,
            analyzer=self._analyzer,
        )

        for deck_name, deck_decisions in export_groups.items():
            for decision in deck_decisions:
                i = card_index
                card_index += 1

                # Check for cancellation
                if self._cancelled:
                    self.finished.emit(False, "Export cancelled by user")
                    return

                # Calculate base progress for this position
                base_progress = i / total
                position_progress_range = 1.0 / total

                # Calculate sub-steps for progress tracking
                analyzer_available = (
                    self.settings.is_xg_available() if getattr(self.settings, 'analyzer_type', 'gnubg') == 'xg'
                    else self.settings.is_gnubg_available()
                )
                has_cube_score_matrix = (
                    decision.decision_type.name == 'CUBE_ACTION' and
                    decision.match_length > 0 and
                    self.settings.get('generate_score_matrix', False) and
                    analyzer_available
                )
                has_move_score_matrix = (
                    decision.decision_type.name == 'CHECKER_PLAY' and
                    decision.dice and
                    self.settings.get('generate_move_score_matrix', False) and
                    analyzer_available
                )
                cube_matrix_steps = (decision.match_length - 1) ** 2 if has_cube_score_matrix else 0
                move_matrix_steps = 4 if has_move_score_matrix else 0
                total_substeps = 2 + cube_matrix_steps + move_matrix_steps

                current_substep = [0]

                def progress_callback(message: str, _i=i, _total_substeps=total_substeps,
                                      _base_progress=base_progress, _range=position_progress_range):
                    current_substep[0] += 1
                    substep_progress = min(current_substep[0] / _total_substeps, 0.95)
                    overall_progress = _base_progress + (substep_progress * _range)
                    self.progress.emit(overall_progress)
                    self.status_message.emit(f"Position {_i+1}/{total}: {message}")

                card_gen.progress_callback = progress_callback

                self.progress.emit(base_progress)

                try:
                    card_data = card_gen.generate_card(decision)
                except InterruptedError:
                    self.finished.emit(False, "Export cancelled by user")
                    return
                except Exception as e:
                    raise RuntimeError(
                        f"Failed to render position {i+1}/{total} "
                        f"(xgid={decision.xgid!r}, dice={decision.dice}, "
                        f"type={decision.decision_type.name}): {e}"
                    ) from e

                # Add to Anki with the deck name from our grouped structure
                self.status_message.emit(f"Position {i+1}/{total}: Adding to Anki...")
                self.progress.emit(base_progress + (0.95 * position_progress_range))
                try:
                    if self.import_mode == "upsert":
                        client.upsert_note(
                            front=card_data['front'],
                            back=card_data['back'],
                            tags=card_data.get('tags', []),
                            deck_name=deck_name,
                            xgid=card_data.get('xgid', ''),
                            analysis_data=card_data.get('analysis_data', '')
                        )
                    else:
                        client.add_note(
                            front=card_data['front'],
                            back=card_data['back'],
                            tags=card_data.get('tags', []),
                            deck_name=deck_name,
                            xgid=card_data.get('xgid', ''),
                            analysis_data=card_data.get('analysis_data', '')
                        )
                except Exception as e:
                    self.finished.emit(False, f"Failed to add card {i+1}: {str(e)}")
                    return

                self.progress.emit((i + 1) / total)

        unique_xgids = len({d.xgid for d in self.all_decisions if d.xgid})
        if unique_xgids and unique_xgids < total:
            self.finished.emit(
                True,
                f"Exported {unique_xgids} unique card(s) to Anki "
                f"({total - unique_xgids} duplicate(s) merged by XGID)"
            )
        else:
            self.finished.emit(True, f"Successfully exported {total} card(s) to Anki")

    def _export_apkg(self):
        """Export to APKG file."""
        self.status_message.emit("Generating APKG file...")
        self.progress.emit(0.0)

        if not self.output_path:
            self.finished.emit(False, "No output path specified for APKG export")
            return

        try:
            # Use existing APKG exporter for model creation
            output_dir = Path.home() / '.ankigammon' / 'cards'
            exporter = ApkgExporter(
                output_dir=output_dir,
                deck_name=self.settings.deck_name
            )

            # Custom export loop with progress tracking
            from ankigammon.renderer.color_schemes import get_scheme
            from ankigammon.renderer.svg_board_renderer import SVGBoardRenderer
            from ankigammon.anki.card_generator import CardGenerator
            from ankigammon.anki.deck_utils import apply_type_subdecks
            import genanki

            scheme = get_scheme(self.settings.color_scheme)
            if self.settings.swap_checker_colors:
                scheme = scheme.with_swapped_checkers()
            renderer = SVGBoardRenderer(
                color_scheme=scheme,
                orientation=self.settings.board_orientation
            )

            # Apply type subdecks if enabled
            export_groups = self.grouped_decisions
            if self.settings.use_subdecks_by_type:
                export_groups = apply_type_subdecks(export_groups)

            # Create deck objects for each group
            decks_dict = {}
            for deck_name in export_groups.keys():
                deck_id = _deterministic_id(f"deck:{deck_name}")
                decks_dict[deck_name] = genanki.Deck(deck_id, deck_name)

            # Generate cards and add to appropriate decks
            total = len(self.all_decisions)
            card_index = 0
            card_gen = CardGenerator(
                output_dir=output_dir,
                show_options=self.settings.show_options,
                interactive_moves=self.settings.interactive_moves,
                renderer=renderer,
                cancellation_callback=lambda: self._cancelled,
                analyzer=self._analyzer,
            )

            for deck_name, deck_decisions in export_groups.items():
                deck = decks_dict[deck_name]

                for decision in deck_decisions:
                    # Check for cancellation
                    if self._cancelled:
                        self.finished.emit(False, "Export cancelled by user")
                        return

                    # Calculate base progress for this position
                    base_progress = card_index / total
                    position_progress_range = 1.0 / total

                    # Calculate sub-steps for progress tracking
                    apkg_analyzer_available = (
                        self.settings.is_xg_available() if getattr(self.settings, 'analyzer_type', 'gnubg') == 'xg'
                        else self.settings.is_gnubg_available()
                    )
                    has_cube_score_matrix = (
                        decision.decision_type.name == 'CUBE_ACTION' and
                        decision.match_length > 0 and
                        self.settings.get('generate_score_matrix', False) and
                        apkg_analyzer_available
                    )
                    has_move_score_matrix = (
                        decision.decision_type.name == 'CHECKER_PLAY' and
                        decision.dice and
                        self.settings.get('generate_move_score_matrix', False) and
                        apkg_analyzer_available
                    )
                    cube_matrix_steps = (decision.match_length - 1) ** 2 if has_cube_score_matrix else 0
                    move_matrix_steps = 4 if has_move_score_matrix else 0  # 4 score types analyzed
                    total_substeps = 2 + cube_matrix_steps + move_matrix_steps  # render + matrices + generate card

                    current_substep = [0]
                    current_card_index = card_index  # Capture for closure

                    # Update progress callback for this position's sub-steps
                    def make_progress_callback(idx):
                        def apkg_progress_callback(message: str):
                            current_substep[0] += 1
                            substep_progress = min(current_substep[0] / total_substeps, 0.95)
                            overall_progress = base_progress + (substep_progress * position_progress_range)
                            self.progress.emit(overall_progress)
                            self.status_message.emit(f"Position {idx+1}/{total}: {message}")
                        return apkg_progress_callback

                    card_gen.progress_callback = make_progress_callback(current_card_index)

                    self.progress.emit(base_progress)

                    # Generate card
                    try:
                        card_data = card_gen.generate_card(decision, card_id=f"card_{card_index}")
                    except InterruptedError:
                        self.finished.emit(False, "Export cancelled by user")
                        return
                    except Exception as e:
                        raise RuntimeError(
                            f"Failed to render position {card_index+1}/{total} "
                            f"(xgid={decision.xgid!r}, dice={decision.dice}, "
                            f"type={decision.decision_type.name}): {e}"
                        ) from e

                    # Create note
                    note = StableNote(
                        model=exporter.model,
                        fields=[
                            card_data.get('xgid', ''),
                            card_data['front'],
                            card_data['back'],
                            card_data.get('analysis_data', ''),
                        ],
                        tags=card_data['tags']
                    )

                    # Add to appropriate deck
                    deck.add_note(note)

                    # Update progress after card added
                    card_index += 1
                    self.progress.emit(card_index / total)

            # Write APKG file with all decks
            self.status_message.emit("Writing APKG file...")
            package = genanki.Package(list(decks_dict.values()))
            package.write_to_file(str(self.output_path))

            self.progress.emit(1.0)
            unique_xgids = len({d.xgid for d in self.all_decisions if d.xgid})
            total = len(self.all_decisions)
            if unique_xgids and unique_xgids < total:
                self.finished.emit(
                    True,
                    f"Created {self.output_path} with {unique_xgids} unique "
                    f"card(s) ({total - unique_xgids} duplicate(s) will be "
                    f"merged by Anki on import)"
                )
            else:
                self.finished.emit(True, f"Successfully created {self.output_path}")
        except Exception as e:
            self.finished.emit(False, f"APKG export failed: {str(e)}")


class ExportDialog(QDialog):
    """Dialog for exporting positions to Anki."""

    # Signal emitted when export completes successfully
    export_succeeded = Signal()

    def __init__(
        self,
        grouped_decisions: Dict[str, List[Decision]],
        settings: Settings,
        parent=None
    ):
        super().__init__(parent)
        self.grouped_decisions = grouped_decisions
        self.all_decisions = [d for decs in grouped_decisions.values() for d in decs]
        self.settings = settings
        self.worker = None
        self.analysis_worker = None
        self._closing = False  # Flag to track if user requested close

        self.setWindowTitle("Export to Anki")
        self.setModal(True)
        self.setMinimumWidth(500)

        self._setup_ui()

    def _setup_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        # Info label with position count and deck breakdown
        num_decks = len(self.grouped_decisions)
        total_positions = len(self.all_decisions)
        if num_decks == 1:
            deck_name = next(iter(self.grouped_decisions))
            info_text = f"Exporting {total_positions} position(s)"
            deck_display = deck_name
        else:
            info_text = f"Exporting {total_positions} position(s) across {num_decks} decks"
            deck_display = ", ".join(self.grouped_decisions.keys())

        info = QLabel(info_text)
        info.setStyleSheet("font-size: 13px; color: #a6adc8; margin-bottom: 4px;")
        layout.addWidget(info)

        # Deck name label (modern styling)
        deck_label = QLabel(f"<span style='font-size: 16px; font-weight: 600; color: #cdd6f4;'>{deck_display}</span>")
        deck_label.setWordWrap(True)
        deck_label.setStyleSheet("padding: 12px 16px; background-color: rgba(137, 180, 250, 0.08); border-radius: 8px;")
        layout.addWidget(deck_label)

        # Progress bar (use percentage-based progress)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel(f"Ready to export {len(self.all_decisions)} position(s)")
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
        self.btn_close = QPushButton("Cancel")
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.clicked.connect(self.close_dialog)

        self.button_box.addButton(self.btn_export, QDialogButtonBox.AcceptRole)
        self.button_box.addButton(self.btn_close, QDialogButtonBox.RejectRole)
        layout.addWidget(self.button_box)

    def closeEvent(self, event):
        """Handle window close event (X button, ESC key, etc)."""
        analysis_running = self.analysis_worker and self.analysis_worker.isRunning()
        export_running = self.worker and self.worker.isRunning()

        if analysis_running or export_running:
            self._cancel_workers()
            event.ignore()  # Don't close yet — finished signal will close
            return

        event.accept()

    @Slot()
    def close_dialog(self):
        """Handle close button click - cancel any running operations."""
        analysis_running = self.analysis_worker and self.analysis_worker.isRunning()
        export_running = self.worker and self.worker.isRunning()

        if analysis_running or export_running:
            self._cancel_workers()
            return

        self.reject()

    def _cancel_workers(self):
        """Cancel running workers and kill the headless XG process.

        Sets the cancellation flag AND immediately terminates the XG
        process so blocking Win32 calls in the worker thread fail fast
        instead of waiting for a 600s timeout.
        """
        self._closing = True
        self.btn_close.setEnabled(False)
        self.status_label.setText("Cancelling...")

        if self.analysis_worker and self.analysis_worker.isRunning():
            self.analysis_worker.cancel()
        if self.worker and self.worker.isRunning():
            self.worker.cancel()

        # Kill the headless XG process immediately.  PostMessageW(WM_CLOSE)
        # is thread-safe, so the worker thread's next Win32 call on the
        # now-dead handle will raise an exception and unwind cleanly.
        self._cleanup_analyzer()

    def _cleanup_analyzer(self):
        """Terminate the headless XG process if one was started."""
        analyzer = getattr(self.analysis_worker, 'analyzer', None) if self.analysis_worker else None
        if analyzer is not None:
            try:
                analyzer.terminate()
            except Exception:
                pass
            self.analysis_worker.analyzer = None

    @Slot()
    def start_export(self):
        """Start export process in background thread."""
        # Anki dedupes notes by GUID (computed from XGID) at import time,
        # so duplicate XGIDs in the input result in fewer cards than expected.
        # Surface them up front rather than letting the user discover the
        # silent loss after import.
        duplicates = find_duplicate_xgids(self.all_decisions)
        if duplicates:
            total = len(self.all_decisions)
            duplicate_count = sum(n - 1 for n in duplicates.values())
            unique_count = total - duplicate_count

            sample_lines = []
            for xgid, n in list(duplicates.items())[:5]:
                sample_lines.append(f"  - {xgid}  (×{n})")
            if len(duplicates) > 5:
                sample_lines.append(f"  - ...and {len(duplicates) - 5} more")
            sample = "\n".join(sample_lines)

            reply = silent_messagebox.question(
                self,
                "Duplicate XGIDs Detected",
                f"{duplicate_count} duplicate position(s) detected among "
                f"{total} input(s). Anki will keep only one card per unique "
                f"XGID, so {unique_count} card(s) will end up in your deck.\n\n"
                f"Duplicates:\n{sample}\n\n"
                f"Continue with the export?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

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

        # Check if any positions need analysis
        needs_analysis = [d for d in self.all_decisions if not d.candidate_moves]

        if needs_analysis:
            # Verify the configured analyzer is available
            analyzer_type = getattr(self.settings, 'analyzer_type', 'gnubg')
            if analyzer_type == "xg":
                analyzer_available = self.settings.is_xg_available()
                engine_name = "eXtreme Gammon"
            else:
                analyzer_available = self.settings.is_gnubg_available()
                engine_name = "GnuBG"

            if not analyzer_available:
                self.status_label.setText(
                    f"Cannot export: {len(needs_analysis)} position(s) need analysis "
                    f"but {engine_name} is not configured.\n"
                    "Please configure an analysis engine in Settings, or import an analyzed file."
                )
                self.btn_export.setEnabled(True)
                return

            # Run analysis first (flat list — analysis doesn't care about deck grouping)
            self.status_label.setText(f"Analyzing {len(needs_analysis)} position(s) with {engine_name}...")
            self.analysis_worker = AnalysisWorker(self.all_decisions, self.settings)
            self.analysis_worker.progress.connect(self.on_analysis_progress)
            self.analysis_worker.status_message.connect(self.on_status_message)
            self.analysis_worker.finished.connect(self.on_analysis_finished)
            self.analysis_worker.start()
        else:
            # No analysis needed, proceed with export
            self._start_export_worker()

    def _start_export_worker(self):
        """Start the actual export worker (after analysis if needed)."""
        # AnkiConnect uses upsert to update existing cards by XGID
        import_mode = "upsert" if self.settings.export_method == "ankiconnect" else "add"

        # Reuse the analyzer from the analysis phase so the score matrix
        # doesn't launch a second headless XG instance.
        analyzer = getattr(self.analysis_worker, 'analyzer', None) if hasattr(self, 'analysis_worker') else None

        # Create worker thread
        self.worker = ExportWorker(
            self.grouped_decisions,
            self.settings,
            self.settings.export_method,
            self.output_path,
            import_mode=import_mode,
            analyzer=analyzer,
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
        # Check if user requested to close
        if self._closing:
            self._cleanup_analyzer()
            self.reject()
            return

        if success:
            # Rebuild grouped_decisions with the analyzed Decision objects.
            # parse_analysis() creates NEW Decision objects, so the old
            # references in grouped_decisions must be replaced.
            self.all_decisions = analyzed_decisions
            idx = 0
            for deck_name in self.grouped_decisions:
                count = len(self.grouped_decisions[deck_name])
                self.grouped_decisions[deck_name] = analyzed_decisions[idx:idx + count]
                idx += count
            self.status_label.setText(f"{message} - Starting export...")
            # Proceed with export
            self._start_export_worker()
        else:
            # Analysis failed — clean up headless XG process
            self._cleanup_analyzer()
            self.status_label.setText(f"Analysis failed: {message}")
            self.log_text.append(f"ERROR: {message}")
            self.btn_export.setEnabled(True)

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
        # Clean up the headless XG process (if any)
        self._cleanup_analyzer()

        # Check if user requested to close
        if self._closing:
            self.reject()
            return

        self.status_label.setText(message)
        self.log_text.append(f"\n{'SUCCESS' if success else 'FAILED'}: {message}")

        if success:
            self.btn_export.hide()
            self.btn_close.setText("Done")
            # Emit signal to notify main window of successful export
            self.export_succeeded.emit()
        else:
            self.btn_export.setEnabled(True)  # Allow retry
