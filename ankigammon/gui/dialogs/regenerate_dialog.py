"""
Dialog for regenerating existing AnkiGammon cards in Anki.

Two modes:

* Re-render only (default): reads the saved Decision (AnalysisData field)
  from each note, re-renders with the current cosmetic settings, and writes
  back the new HTML. Never re-analyzes the position, so rollouts and other
  high-precision analyses are preserved. Score matrices are not stored in
  the blob, so an engine is still started to rebuild those.

* Re-analyze: queries the analyzer for fresh results before re-rendering.
  This replaces any rollout data with the engine's standard analysis.
"""

from dataclasses import replace
from pathlib import Path
from typing import List, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar,
    QPushButton, QTextEdit, QDialogButtonBox,
    QRadioButton, QButtonGroup, QFrame, QCheckBox
)
from PySide6.QtCore import Qt, QThread, Signal, Slot

from ankigammon.utils.analysis_debug import record_failed_analysis
from ankigammon.anki.ankiconnect import AnkiConnect
from ankigammon.anki.card_styles import MODEL_NAME
from ankigammon.anki.decision_serialize import carry_user_metadata, decision_from_json
from ankigammon.anki.optional_analysis import (
    is_cube_xgid,
    lost_optional_blocks,
    missing_optional_blocks,
)
from ankigammon.models import DecisionType
from ankigammon.settings import Settings


MODE_RENDER_ONLY = "render_only"
MODE_REANALYZE = "reanalyze"


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

    def __init__(self, settings: Settings, mode: str, only_missing: bool = False):
        super().__init__()
        self.settings = settings
        self.mode = mode
        self.only_missing = only_missing
        self._cancelled = False
        self._analyzer = None
        self._card_gen = None

    def cancel(self):
        """Request cancellation."""
        self._cancelled = True

    def run(self):
        """Regenerate all AnkiGammon cards in Anki."""
        try:
            if self.mode == MODE_RENDER_ONLY:
                self._do_render_only()
            else:
                self._do_reanalyze()
        except InterruptedError:
            self.finished.emit(False, "Regeneration cancelled by user")
        except Exception as e:
            self.finished.emit(False, f"Regeneration failed: {str(e)}")
        finally:
            self._terminate_engines()

    def _terminate_engines(self) -> None:
        """Shut down every engine this run started, each exactly once.

        For XG this closes the process AnkiGammon launched; leaving one
        running is what stranded xg2 in the background. A re-render never
        creates an analyzer of its own unless a score matrix needs one, and
        that one is the CardGenerator's, not the worker's.
        """
        engines = []
        for candidate in (self._analyzer, getattr(self._card_gen, '_analyzer', None)):
            if candidate is not None and not any(candidate is e for e in engines):
                engines.append(candidate)
        self._analyzer = None
        self._card_gen = None

        for engine in engines:
            try:
                engine.terminate()
            except Exception:
                pass

    def _connect_and_load_notes(self, client: AnkiConnect) -> Optional[List[dict]]:
        """Connect to Anki and return notes_info for all ankigammon-tagged notes.

        Returns None if the operation should abort (failed connection, no notes,
        or cancellation). The worker will already have emitted finished() in
        those cases.
        """
        self.status_message.emit("Connecting to Anki...")
        if not client.test_connection():
            self.finished.emit(
                False,
                "Could not connect to Anki. Is Anki running with AnkiConnect installed?"
            )
            return None
        client.create_model()

        if self._cancelled:
            self.finished.emit(False, "Cancelled by user")
            return None

        self.status_message.emit("Finding AnkiGammon notes...")
        all_note_ids = client.invoke('findNotes', query='tag:ankigammon')
        if not all_note_ids:
            self.finished.emit(True, "No AnkiGammon notes found in Anki.")
            return None

        self.status_message.emit(f"Reading {len(all_note_ids)} note(s)...")
        notes_data = client.notes_info(all_note_ids)

        if self.only_missing:
            notes_data = self._notes_missing_optional_analysis(notes_data)
            if not notes_data:
                self.finished.emit(True, "No cards are missing optional analysis.")
                return None
            self.status_message.emit(
                f"{len(notes_data)} of {len(all_note_ids)} card(s) are missing "
                "optional analysis."
            )
        return notes_data

    def _notes_missing_optional_analysis(self, notes_data: List[dict]) -> List[dict]:
        """Notes whose card lacks a block the current settings call for.

        Card type and match length come from the saved blob; a legacy card
        without one is typed from its XGID. A card that cannot be typed at
        all is left alone rather than regenerated on a guess.
        """
        selected = []
        for note_data in notes_data:
            fields = note_data.get('fields', {})
            back = fields.get('Back', {}).get('value', '')
            blob = fields.get('AnalysisData', {}).get('value', '').strip()
            xgid = fields.get('XGID', {}).get('value', '').strip()

            is_cube, match_length = None, None
            if blob:
                try:
                    saved = decision_from_json(blob)
                    is_cube = saved.decision_type == DecisionType.CUBE_ACTION
                    match_length = saved.match_length
                except Exception:
                    pass
            if is_cube is None:
                is_cube = is_cube_xgid(xgid)
            if is_cube is None:
                continue

            if missing_optional_blocks(back, is_cube, self.settings, match_length):
                selected.append(note_data)
        return selected

    def _keeps_previous_card(
        self, card_gen, warnings_before: int, old_back: str, new_back: str, note_id: int
    ) -> bool:
        """True when the card must be left as it is.

        An optional block the card already had failed to rebuild this run.
        Writing the new render would trade a table the user has for nothing,
        which is what a regenerate did before this check existed.
        """
        if len(card_gen.generation_warnings) == warnings_before:
            return False
        lost = lost_optional_blocks(old_back, new_back)
        if not lost:
            return False
        self.status_message.emit(
            f"Kept note {note_id} unchanged: its {', '.join(lost)} failed to "
            "rebuild and the card already had it"
        )
        return True

    def _build_card_generator(self, analyzer=None):
        """Create a CardGenerator configured from current settings.

        Score matrices need an engine, so a CardGenerator without one builds
        its own. Passing the analyzer already in use keeps that to a single
        connection: a second headless XG kills the first as a stale instance,
        which silently drops the matrix from the card.
        """
        from ankigammon.anki.card_generator import CardGenerator
        from ankigammon.renderer.svg_board_renderer import SVGBoardRenderer
        from ankigammon.renderer.color_schemes import SCHEMES

        color_scheme = SCHEMES.get(self.settings.color_scheme, SCHEMES['classic'])
        if self.settings.swap_checker_colors:
            color_scheme = color_scheme.with_swapped_checkers()
        renderer = SVGBoardRenderer(
            color_scheme=color_scheme,
            orientation=self.settings.board_orientation
        )
        output_dir = Path.home() / '.ankigammon' / 'cards'
        self._card_gen = CardGenerator(
            output_dir=output_dir,
            show_options=self.settings.show_options,
            interactive_moves=self.settings.interactive_moves,
            renderer=renderer,
            analyzer=analyzer,
        )
        return self._card_gen

    def _do_render_only(self):
        """Re-render cards using the saved Decision (no analyzer involved)."""
        client = AnkiConnect(deck_name=self.settings.deck_name)
        notes_data = self._connect_and_load_notes(client)
        if notes_data is None:
            return

        # Pull out (note_id, AnalysisData blob) for notes that have one.
        # Notes lacking AnalysisData are pre-feature legacy cards and are
        # reported to the user rather than silently re-analyzed.
        rerender_targets = []
        legacy_skipped = 0
        for note_data in notes_data:
            note_id = note_data['noteId']
            fields = note_data.get('fields', {})
            blob = fields.get('AnalysisData', {}).get('value', '').strip()
            old_back = fields.get('Back', {}).get('value', '')
            if blob:
                rerender_targets.append((note_id, blob, old_back))
            else:
                legacy_skipped += 1

        if not rerender_targets:
            msg = "No cards have saved analysis data — re-render unavailable."
            if legacy_skipped:
                msg += (
                    f" {legacy_skipped} legacy card(s) were exported before "
                    "this feature existed; use Re-analyze to update them."
                )
            self.finished.emit(True, msg)
            return

        total = len(rerender_targets)
        self.status_message.emit(f"Re-rendering {total} card(s) with current settings...")

        card_gen = self._build_card_generator()

        updated = 0
        errors = 0
        kept = 0
        for i, (note_id, blob, old_back) in enumerate(rerender_targets):
            if self._cancelled:
                self.finished.emit(False, f"Cancelled after re-rendering {updated} card(s)")
                return

            self.progress.emit(i, total)
            self.status_message.emit(f"Re-rendering card {i + 1}/{total}...")

            try:
                decision = decision_from_json(blob)
                warnings_before = len(card_gen.generation_warnings)
                card_data = card_gen.generate_card(decision)
                if self._keeps_previous_card(
                    card_gen, warnings_before, old_back, card_data['back'], note_id
                ):
                    kept += 1
                    continue
                # Pass analysis_data=None: AnalysisData is unchanged because
                # we deserialized FROM it. Only Front/Back/XGID need updating.
                client.update_note_fields(
                    note_id,
                    card_data['front'],
                    card_data['back'],
                    card_data.get('xgid', ''),
                    analysis_data=None,
                )
                client.update_note_tags(note_id, card_data.get('tags', []))
                updated += 1
            except Exception as e:
                self.status_message.emit(f"Warning: Failed to re-render note {note_id}: {e}")
                errors += 1

        self.progress.emit(total, total)

        msg = f"Successfully re-rendered {updated} card(s)"
        if errors:
            msg += f" ({errors} failed)"
        if kept:
            msg += (
                f". Kept {kept} card(s) unchanged because their optional "
                "analysis failed this run"
            )
        if card_gen.generation_warnings:
            msg += (
                f". {len(card_gen.generation_warnings)} card(s) rendered "
                "without optional analysis (see log for details)"
            )
            for warning in card_gen.generation_warnings:
                self.status_message.emit(f"Warning: {warning}")
        if legacy_skipped:
            msg += (
                f". Skipped {legacy_skipped} legacy card(s) without saved "
                "analysis — use Re-analyze for those."
            )
        self.finished.emit(True, msg)

    def _restore_user_metadata(self, decision, blob: str, note_id: int) -> None:
        """Carry the note and source info from a card's saved blob onto its
        freshly analyzed Decision.

        A card written before AnalysisData existed, or one whose blob is
        unreadable, simply has nothing to restore — that must not cost the
        user the rest of the regeneration.
        """
        if not blob:
            return
        try:
            carry_user_metadata(decision_from_json(blob), decision)
        except Exception as e:
            self.status_message.emit(
                f"Warning: Could not read saved note for note {note_id}: {e}"
            )

    def _do_reanalyze(self):
        """Re-analyze positions, then re-render. Mirrors the legacy behavior."""
        from ankigammon.utils.analyzer_base import create_analyzer

        client = AnkiConnect(deck_name=self.settings.deck_name)
        notes_data = self._connect_and_load_notes(client)
        if notes_data is None:
            return

        # The saved blob rides along: re-analysis produces a Decision built
        # from engine output alone, so the user's note lives nowhere else and
        # would be overwritten in both Back and AnalysisData (issue #58).
        note_xgid_pairs: List[tuple] = []
        for note_data in notes_data:
            note_id = note_data['noteId']
            fields = note_data.get('fields', {})
            xgid = fields.get('XGID', {}).get('value', '').strip()
            blob = fields.get('AnalysisData', {}).get('value', '').strip()
            old_back = fields.get('Back', {}).get('value', '')
            if xgid:
                note_xgid_pairs.append((note_id, xgid, blob, old_back))

        if not note_xgid_pairs:
            self.finished.emit(True, "No notes with XGID values found. Cannot regenerate.")
            return

        total = len(note_xgid_pairs)
        self.status_message.emit(f"Found {total} note(s) with positions to regenerate.")

        # Deduplicate XGIDs for efficient analysis
        unique_xgids = list(dict.fromkeys(xgid for _, xgid, _, _ in note_xgid_pairs))

        if self._cancelled:
            self.finished.emit(False, "Cancelled by user")
            return

        analyzer = self._analyzer = create_analyzer(self.settings)

        def analysis_progress(completed: int, total_positions: int):
            if self._cancelled:
                return
            self.progress.emit(completed, total_positions * 2)
            # The engine reports how many are done; the user reads which one
            # is in progress, so "0/5" looked like nothing was happening.
            if completed < total_positions:
                self.status_message.emit(
                    f"Analyzing position {completed + 1}/{total_positions}..."
                )
            else:
                self.status_message.emit(
                    f"Analyzed {total_positions}/{total_positions} position(s)."
                )

        self.status_message.emit(
            f"Analyzing {len(unique_xgids)} unique position(s)..."
        )
        analysis_results = analyzer.analyze_positions_parallel(
            unique_xgids,
            progress_callback=analysis_progress
        )

        if self._cancelled:
            self.finished.emit(False, "Cancelled by user")
            return

        self.status_message.emit("Parsing analysis results...")
        analyzer_type = getattr(self.settings, 'analyzer_type', 'gnubg')
        if analyzer_type == "xg":
            engine_desc = f"eXtreme Gammon ({self.settings.xg_analysis_level})"
        else:
            engine_desc = f"GnuBG ({self.settings.gnubg_analysis_ply}-ply)"

        xgid_to_decision = {}
        for xgid, (raw_output, decision_type) in zip(unique_xgids, analysis_results):
            # An unparseable position leaves its xgid unmapped; the per-note
            # loop below reports it and keeps the rest of the batch going.
            try:
                decision = analyzer.parse_analysis(raw_output, xgid, decision_type)
            except Exception as e:
                record_failed_analysis(xgid, raw_output, e)
                self.status_message.emit(f"Warning: Skipping {xgid}: {e}")
                continue
            decision.source_description = f"Regenerated with {engine_desc}"
            xgid_to_decision[xgid] = decision

        card_gen = self._build_card_generator(analyzer=analyzer)

        updated = 0
        errors = 0
        kept = 0
        for i, (note_id, xgid, blob, old_back) in enumerate(note_xgid_pairs):
            if self._cancelled:
                self.finished.emit(False, f"Cancelled after updating {updated} card(s)")
                return

            self.progress.emit(total + i, total * 2)
            self.status_message.emit(f"Regenerating card {i + 1}/{total}...")

            try:
                # Copy first: notes sharing an XGID share one analysis result
                # but each carry their own annotations.
                decision = replace(xgid_to_decision[xgid])
                self._restore_user_metadata(decision, blob, note_id)
                warnings_before = len(card_gen.generation_warnings)
                card_data = card_gen.generate_card(decision)
                if self._keeps_previous_card(
                    card_gen, warnings_before, old_back, card_data['back'], note_id
                ):
                    kept += 1
                    continue
                # Re-analyze path overwrites AnalysisData with the fresh blob
                client.update_note_fields(
                    note_id,
                    card_data['front'],
                    card_data['back'],
                    card_data.get('xgid', ''),
                    analysis_data=card_data.get('analysis_data', ''),
                )
                client.update_note_tags(note_id, card_data.get('tags', []))
                updated += 1
            except Exception as e:
                self.status_message.emit(f"Warning: Failed to update note {note_id}: {e}")
                errors += 1

        self.progress.emit(total * 2, total * 2)

        msg = f"Successfully regenerated {updated} card(s) in Anki"
        if errors > 0:
            msg += f" ({errors} failed)"
        if kept:
            msg += (
                f". Kept {kept} card(s) unchanged because their optional "
                "analysis failed this run"
            )
        if card_gen.generation_warnings:
            msg += (
                f". {len(card_gen.generation_warnings)} card(s) rendered "
                "without optional analysis (see log for details)"
            )
            for warning in card_gen.generation_warnings:
                self.status_message.emit(f"Warning: {warning}")
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
        self.setMinimumWidth(560)

        self._setup_ui()

    def _setup_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        info = QLabel("Regenerate AnkiGammon cards in Anki")
        info.setStyleSheet("font-size: 13px; color: #a6adc8; margin-bottom: 4px;")
        layout.addWidget(info)

        # Mode selection — radio buttons in a styled frame
        mode_frame = QFrame()
        mode_frame.setStyleSheet(
            "QFrame { padding: 12px 16px; background-color: rgba(137, 180, 250, 0.08); "
            "border-radius: 8px; }"
        )
        mode_layout = QVBoxLayout(mode_frame)
        mode_layout.setSpacing(8)

        self.mode_group = QButtonGroup(self)

        self.radio_render_only = QRadioButton("Re-render cards only (recommended)")
        self.radio_render_only.setChecked(True)
        self.radio_render_only.setStyleSheet("font-weight: 600; color: #cdd6f4;")
        render_desc = QLabel(
            "Use saved analysis. Applies your current visual settings — board "
            "colors, pip counter, checker direction. Fast; no analyzer needed; "
            "rollout data is preserved."
        )
        render_desc.setWordWrap(True)
        render_desc.setStyleSheet("color: #a6adc8; padding-left: 22px;")

        self.radio_reanalyze = QRadioButton("Re-analyze and re-render")
        self.radio_reanalyze.setStyleSheet("font-weight: 600; color: #cdd6f4;")
        reanalyze_desc = QLabel(
            "Run fresh analysis with the configured engine before re-rendering. "
            "<b>Replaces any rollout data with the engine's standard analysis.</b>"
        )
        reanalyze_desc.setWordWrap(True)
        reanalyze_desc.setStyleSheet("color: #a6adc8; padding-left: 22px;")

        self.mode_group.addButton(self.radio_render_only)
        self.mode_group.addButton(self.radio_reanalyze)

        mode_layout.addWidget(self.radio_render_only)
        mode_layout.addWidget(render_desc)
        mode_layout.addWidget(self.radio_reanalyze)
        mode_layout.addWidget(reanalyze_desc)

        self.chk_only_missing = QCheckBox(
            "Only cards missing a score matrix or cube comparison"
        )
        self.chk_only_missing.setStyleSheet(
            "font-weight: 600; color: #cdd6f4; margin-top: 6px;"
        )
        self.chk_only_missing.setToolTip(
            "Skips cards that already carry every optional block your settings "
            "ask for. A missing cube-position comparison can only be detected on "
            "cards made from this version on."
        )
        mode_layout.addWidget(self.chk_only_missing)

        layout.addWidget(mode_frame)

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

    def _selected_mode(self) -> str:
        return MODE_RENDER_ONLY if self.radio_render_only.isChecked() else MODE_REANALYZE

    @Slot()
    def start_regenerate(self):
        """Start regeneration in background thread."""
        mode = self._selected_mode()

        # Re-analyze path requires a working analyzer; render-only does not.
        if mode == MODE_REANALYZE:
            analyzer_type = getattr(self.settings, 'analyzer_type', 'gnubg')
            if analyzer_type == "xg":
                analyzer_available = self.settings.is_xg_available()
                engine_name = "eXtreme Gammon"
            else:
                analyzer_available = self.settings.is_gnubg_available()
                engine_name = "GnuBG"
            if not analyzer_available:
                self.status_label.setText(
                    f"{engine_name} is required for re-analyze. "
                    "Configure it in Settings, or pick 'Re-render cards only'."
                )
                return

        # Lock the mode selection while running
        self.radio_render_only.setEnabled(False)
        self.radio_reanalyze.setEnabled(False)
        self.chk_only_missing.setEnabled(False)
        self.btn_regenerate.setEnabled(False)
        self.status_label.setText("Starting regeneration...")

        self.worker = RegenerateWorker(
            self.settings, mode, only_missing=self.chk_only_missing.isChecked()
        )
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
            self.radio_render_only.setEnabled(True)
            self.radio_reanalyze.setEnabled(True)
