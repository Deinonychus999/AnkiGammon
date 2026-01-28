"""
Main application window.
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QMessageBox, QInputDialog, QApplication
)
from PySide6.QtCore import Qt, Signal, Slot, QUrl, QSettings, QSize, QThread, QTimer
from PySide6.QtGui import QAction, QKeySequence, QDesktopServices
from PySide6.QtWebEngineWidgets import QWebEngineView
import qtawesome as qta
import base64
import subprocess
import sys
from typing import List, Tuple

from ankigammon import __version__
from ankigammon.settings import Settings
from ankigammon.renderer.svg_board_renderer import SVGBoardRenderer
from ankigammon.renderer.color_schemes import get_scheme
from ankigammon.models import Decision, Move
from ankigammon.gui.widgets import PositionListWidget
from ankigammon.gui.dialogs import SettingsDialog, ExportDialog, InputDialog, ImportOptionsDialog, ShortcutsDialog
from ankigammon.gui.dialogs.update_dialog import UpdateDialog, CheckingUpdateDialog, NoUpdateDialog, UpdateCheckFailedDialog
from ankigammon.gui.update_checker import VersionCheckerThread
from ankigammon.gui.resources import get_resource_path
from ankigammon.gui import silent_messagebox


class MatchAnalysisWorker(QThread):
    """
    Background thread for GnuBG match file analysis.

    Signals:
        status_message(str): status update message
        finished(bool, str, list, int): success, message, decisions, total_count
    """

    status_message = Signal(str)
    finished = Signal(bool, str, list, int)

    def __init__(self, file_path: str, settings: Settings, checker_threshold: float,
                 cube_threshold: float, include_player_x: bool, include_player_o: bool,
                 filter_func, max_mcq_options: int):
        super().__init__()
        self.file_path = file_path
        self.settings = settings
        self.checker_threshold = checker_threshold
        self.cube_threshold = cube_threshold
        self.include_player_x = include_player_x
        self.include_player_o = include_player_o
        self.filter_func = filter_func
        self.max_mcq_options = max_mcq_options
        self._cancelled = False
        self._analyzer = None

    def cancel(self):
        """Request cancellation of analysis."""
        self._cancelled = True
        # Terminate GnuBG process if analyzer is running
        if self._analyzer is not None:
            self._analyzer.terminate()

    def run(self):
        """Analyze match file in background thread."""
        from ankigammon.utils.gnubg_analyzer import GNUBGAnalyzer
        from ankigammon.parsers.gnubg_match_parser import parse_gnubg_match_files
        import logging
        import shutil
        from pathlib import Path
        import subprocess

        logger = logging.getLogger(__name__)

        try:
            # Check for cancellation before starting
            if self._cancelled:
                self.finished.emit(False, "Cancelled", [], 0)
                return

            # Create analyzer
            self.status_message.emit(f"Analyzing match with GnuBG ({self.settings.gnubg_analysis_ply}-ply)...")

            self._analyzer = GNUBGAnalyzer(
                self.settings.gnubg_path,
                self.settings.gnubg_analysis_ply
            )

            # Analyze match
            def progress_callback(status: str):
                if self._cancelled:
                    return
                self.status_message.emit(status)

            exported_files = self._analyzer.analyze_match_file(
                self.file_path,
                max_moves=self.max_mcq_options,
                progress_callback=progress_callback
            )

            # Check for cancellation after analysis
            if self._cancelled:
                # Cleanup temp files before returning
                for temp_file in exported_files:
                    try:
                        temp_dir = Path(temp_file).parent
                        shutil.rmtree(temp_dir)
                        break
                    except:
                        pass
                self.finished.emit(False, "Cancelled", [], 0)
                return

            logger.info(f"GnuBG exported {len(exported_files)} file(s)")

            # Parse exported files
            self.status_message.emit(f"Parsing analysis from {len(exported_files)} game(s)...")

            # Detect if source was SGF file (need to swap scores)
            is_sgf_source = self.file_path.endswith('.sgf')

            # Extract original filename for source description
            original_filename = Path(self.file_path).name

            all_decisions = parse_gnubg_match_files(
                exported_files,
                is_sgf_source=is_sgf_source,
                ply_level=self.settings.gnubg_analysis_ply,
                source_filename=original_filename
            )
            total_count = len(all_decisions)

            # Check for cancellation after parsing
            if self._cancelled:
                # Cleanup temp files before returning
                for temp_file in exported_files:
                    try:
                        temp_dir = Path(temp_file).parent
                        shutil.rmtree(temp_dir)
                        break
                    except:
                        pass
                self.finished.emit(False, "Cancelled", [], 0)
                return

            logger.info(f"Parsed {total_count} positions from match")

            # Filter based on user options
            self.status_message.emit("Filtering positions by error thresholds...")

            decisions = self.filter_func(
                all_decisions,
                self.checker_threshold,
                self.cube_threshold,
                self.include_player_x,
                self.include_player_o
            )

            logger.info(f"Filtered to {len(decisions)} positions (checker: {self.checker_threshold}, cube: {self.cube_threshold})")

            # Cleanup temp files
            self.status_message.emit("Cleaning up temporary files...")
            for temp_file in exported_files:
                try:
                    temp_dir = Path(temp_file).parent
                    shutil.rmtree(temp_dir)
                    break  # Only need to remove directory once
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp files: {e}")

            # Final cancellation check
            if self._cancelled:
                self.finished.emit(False, "Cancelled", [], 0)
                return

            self.finished.emit(True, "Success", decisions, total_count)

        except subprocess.CalledProcessError as e:
            if self._cancelled:
                self.finished.emit(False, "Cancelled", [], 0)
            else:
                logger.error(f"GnuBG analysis failed: {e}")
                error_msg = f"GnuBG analysis failed:\n\n{e.stderr if e.stderr else str(e)}"
                self.finished.emit(False, error_msg, [], 0)

        except Exception as e:
            if self._cancelled:
                self.finished.emit(False, "Cancelled", [], 0)
            else:
                logger.error(f"Match import failed: {e}", exc_info=True)
                error_msg = f"Failed to import match file:\n\n{str(e)}"
                self.finished.emit(False, error_msg, [], 0)


class MainWindow(QMainWindow):
    """Main application window for AnkiGammon."""

    # Signals
    decisions_parsed = Signal(list)  # List[Decision]

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.current_decisions = []
        scheme = get_scheme(settings.color_scheme)
        if settings.swap_checker_colors:
            scheme = scheme.with_swapped_checkers()
        self.renderer = SVGBoardRenderer(
            color_scheme=scheme,
            orientation=settings.board_orientation
        )
        self.color_scheme_actions = {}  # Store references to color scheme menu actions
        self._gnubg_check_shown = False  # Track if we've shown GnuBG config dialog in current import batch
        self._import_queue = []  # Queue for sequential file imports
        self._import_in_progress = False  # Track if an import is currently being processed
        self._batch_import_results = []  # Accumulate results from batch imports (for combined success message)
        self._in_batch_import = False  # Flag to track if we're currently in a batch import of .xgp files
        self._version_checker_thread = None  # Version checker thread

        # Enable drag and drop
        self.setAcceptDrops(True)

        self._setup_ui()
        self._setup_menu_bar()
        self._setup_connections()
        self._restore_window_state()

        # Create drop overlay (will be shown during drag operations)
        self._create_drop_overlay()

        # Start background version check if enabled
        if self.settings.check_for_updates:
            QTimer.singleShot(2000, self._check_for_updates_background)

    def _setup_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("AnkiGammon - Backgammon Analysis to Anki")
        self.setMinimumSize(1000, 700)
        self.resize(1300, 720)  # Optimal default size for board display

        # Hide the status bar for a cleaner, modern look
        self.statusBar().hide()

        # Central widget with horizontal layout
        central = QWidget()
        central.setAcceptDrops(False)  # Let drag events propagate to main window
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Left panel: Controls
        left_panel = self._create_left_panel()
        left_panel.setAcceptDrops(False)  # Let drag events propagate to main window
        layout.addWidget(left_panel, stretch=1)

        # Right panel: Preview
        self.preview = QWebEngineView()
        self.preview.setContextMenuPolicy(Qt.NoContextMenu)  # Disable browser context menu
        self.preview.setAcceptDrops(False)  # Let drag events propagate to main window

        # Load icon and convert to base64 for embedding in HTML
        icon_path = get_resource_path("ankigammon/gui/resources/icon.png")
        icon_data_url = ""
        if icon_path.exists():
            with open(icon_path, "rb") as f:
                icon_bytes = f.read()
                icon_b64 = base64.b64encode(icon_bytes).decode('utf-8')
                icon_data_url = f"data:image/png;base64,{icon_b64}"

        self.welcome_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    margin: 0;
                    padding: 0;
                    display: flex;
                    flex-direction: column;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    background: linear-gradient(135deg, #1e1e2e 0%, #181825 100%);
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    color: #cdd6f4;
                }}
                .welcome {{
                    text-align: center;
                    padding: 40px;
                }}
                h1 {{
                    color: #f5e0dc;
                    font-size: 32px;
                    margin-bottom: 16px;
                    font-weight: 700;
                }}
                p {{
                    color: #a6adc8;
                    font-size: 16px;
                    margin: 8px 0;
                }}
                .icon {{
                    margin-bottom: 24px;
                    opacity: 0.6;
                }}
                .icon img {{
                    width: 140px;
                    height: auto;
                }}
            </style>
        </head>
        <body>
            <div class="welcome">
                <div class="icon">
                    <img src="{icon_data_url}" alt="AnkiGammon Icon" />
                </div>
                <h1>No Position Loaded</h1>
                <p>Add positions to get started</p>
            </div>
        </body>
        </html>
        """
        self.preview.setHtml(self.welcome_html)
        layout.addWidget(self.preview, stretch=2)

        # Status bar
        self.statusBar().showMessage("Ready")

    def _create_left_panel(self) -> QWidget:
        """Create the left control panel."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Title
        title = QLabel("<h2>AnkiGammon</h2>")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Button row: Import File and Add Positions
        btn_row = QWidget()
        btn_row_layout = QHBoxLayout(btn_row)
        btn_row_layout.setContentsMargins(0, 0, 0, 0)
        btn_row_layout.setSpacing(8)

        # Import File button (equal primary) - full-sized with text + icon
        self.btn_import_file = QPushButton("  Import Files...")
        self.btn_import_file.setIcon(qta.icon('fa6s.file-import', color='#1e1e2e'))
        self.btn_import_file.setIconSize(QSize(18, 18))
        self.btn_import_file.clicked.connect(self.on_import_file_clicked)
        self.btn_import_file.setToolTip("Import .xg, .xgp, .mat, .txt, or .sgf files (supports multi-select)")
        self.btn_import_file.setCursor(Qt.PointingHandCursor)
        btn_row_layout.addWidget(self.btn_import_file, stretch=1)

        # Add Positions button (primary) - blue background needs dark icons
        self.btn_add_positions = QPushButton("  Add Positions...")
        self.btn_add_positions.setIcon(qta.icon('fa6s.clipboard-list', color='#1e1e2e'))
        self.btn_add_positions.setIconSize(QSize(18, 18))
        self.btn_add_positions.clicked.connect(self.on_add_positions_clicked)
        self.btn_add_positions.setToolTip("Add position IDs (XGID/OGID/GNUID) or full XG analysis")
        self.btn_add_positions.setCursor(Qt.PointingHandCursor)
        btn_row_layout.addWidget(self.btn_add_positions, stretch=1)

        layout.addWidget(btn_row)

        # Position list with integrated Clear All button
        list_container = QWidget()
        list_container_layout = QVBoxLayout(list_container)
        list_container_layout.setContentsMargins(0, 0, 0, 0)
        list_container_layout.setSpacing(0)

        # Clear All button positioned at top-right
        self.btn_clear_all = QPushButton("  Clear All")
        self.btn_clear_all.setIcon(qta.icon('fa6s.trash-can', color='#a6adc8'))
        self.btn_clear_all.setIconSize(QSize(11, 11))
        self.btn_clear_all.setCursor(Qt.PointingHandCursor)
        self.btn_clear_all.clicked.connect(self.on_clear_all_clicked)
        self.btn_clear_all.setToolTip("Clear all positions")
        self.btn_clear_all.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #6c7086;
                border: none;
                padding: 6px 10px;
                font-size: 11px;
                font-weight: 500;
                border-radius: 4px;
            }
            QPushButton:hover:enabled {
                background-color: rgba(243, 139, 168, 0.15);
                color: #f38ba8;
            }
            QPushButton:pressed:enabled {
                background-color: rgba(243, 139, 168, 0.25);
            }
        """)

        # Create header row with clear button aligned right (initially hidden)
        self.list_header_row = QWidget()
        header_layout = QHBoxLayout(self.list_header_row)
        header_layout.setContentsMargins(0, 0, 0, 4)
        header_layout.setSpacing(0)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_clear_all)
        self.list_header_row.hide()  # Hidden until positions are added
        list_container_layout.addWidget(self.list_header_row)

        # Position list widget
        self.position_list = PositionListWidget(self.settings)
        self.position_list.position_selected.connect(self.show_decision)
        self.position_list.positions_deleted.connect(self.on_positions_deleted)
        list_container_layout.addWidget(self.position_list, stretch=1)

        layout.addWidget(list_container, stretch=1)

        # Spacer
        layout.addSpacing(12)

        # Deck name indicator with edit button
        deck_container = QWidget()
        deck_layout = QHBoxLayout(deck_container)
        deck_layout.setContentsMargins(18, 16, 18, 16)
        deck_layout.setSpacing(14)
        deck_container.setStyleSheet("""
            QWidget {
                background-color: rgba(137, 180, 250, 0.08);
                border-radius: 12px;
            }
        """)

        self.lbl_deck_name = QLabel()
        self.lbl_deck_name.setWordWrap(True)
        self.lbl_deck_name.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.lbl_deck_name.setTextFormat(Qt.RichText)
        self.lbl_deck_name.setStyleSheet("""
            QLabel {
                color: #cdd6f4;
                padding: 2px 0px;
                background: transparent;
            }
        """)
        self._update_deck_label()
        deck_layout.addWidget(self.lbl_deck_name, stretch=1)

        # Edit button for deck name
        self.btn_edit_deck = QPushButton()
        self.btn_edit_deck.setIcon(qta.icon('fa6s.pencil', color='#a6adc8'))
        self.btn_edit_deck.setIconSize(QSize(16, 16))
        self.btn_edit_deck.setFixedSize(32, 32)
        self.btn_edit_deck.setToolTip("Edit deck name")
        self.btn_edit_deck.setStyleSheet("""
            QPushButton {
                background-color: rgba(205, 214, 244, 0.05);
                border: none;
                border-radius: 8px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: rgba(205, 214, 244, 0.12);
            }
            QPushButton:pressed {
                background-color: rgba(205, 214, 244, 0.18);
            }
        """)
        self.btn_edit_deck.setCursor(Qt.PointingHandCursor)
        self.btn_edit_deck.clicked.connect(self.on_edit_deck_name)
        deck_layout.addWidget(self.btn_edit_deck, alignment=Qt.AlignVCenter)

        layout.addWidget(deck_container)

        layout.addSpacing(12)

        # Settings button
        self.btn_settings = QPushButton("  Settings")
        self.btn_settings.setIcon(qta.icon('fa6s.gear', color='#cdd6f4'))
        self.btn_settings.setIconSize(QSize(18, 18))
        self.btn_settings.setObjectName("btn_settings")
        self.btn_settings.setCursor(Qt.PointingHandCursor)
        self.btn_settings.clicked.connect(self.on_settings_clicked)
        layout.addWidget(self.btn_settings)

        # Export button - blue background needs dark icons
        self.btn_export = QPushButton("  Export to Anki")
        self.btn_export.setIcon(qta.icon('fa6s.file-export', color='#1e1e2e'))
        self.btn_export.setIconSize(QSize(18, 18))
        self.btn_export.setEnabled(False)
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.clicked.connect(self.on_export_clicked)
        layout.addWidget(self.btn_export)

        return panel

    def _setup_menu_bar(self):
        """Create application menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        act_add_positions = QAction("&Add Positions...", self)
        act_add_positions.setShortcut("Ctrl+N")
        act_add_positions.triggered.connect(self.on_add_positions_clicked)
        file_menu.addAction(act_add_positions)

        act_import_file = QAction("&Import Files...", self)
        act_import_file.setShortcut("Ctrl+O")
        act_import_file.triggered.connect(self.on_import_file_clicked)
        file_menu.addAction(act_import_file)

        file_menu.addSeparator()

        act_export = QAction("&Export to Anki...", self)
        act_export.setShortcut("Ctrl+E")
        act_export.triggered.connect(self.on_export_clicked)
        file_menu.addAction(act_export)

        act_regenerate = QAction("&Regenerate Cards in Anki...", self)
        act_regenerate.setShortcut("Ctrl+R")
        act_regenerate.triggered.connect(self.on_regenerate_clicked)
        file_menu.addAction(act_regenerate)

        file_menu.addSeparator()

        act_quit = QAction("&Quit", self)
        act_quit.setShortcut(QKeySequence.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")

        act_settings = QAction("&Settings...", self)
        act_settings.setShortcut("Ctrl+,")
        act_settings.triggered.connect(self.on_settings_clicked)
        edit_menu.addAction(act_settings)

        # Board Theme menu
        board_theme_menu = menubar.addMenu("&Board Theme")

        # Add theme options directly (no submenu)
        from ankigammon.renderer.color_schemes import list_schemes
        for scheme in list_schemes():
            act_scheme = QAction(scheme.title(), self)
            act_scheme.setCheckable(True)
            act_scheme.setChecked(scheme == self.settings.color_scheme)
            act_scheme.triggered.connect(
                lambda checked, s=scheme: self.change_color_scheme(s)
            )
            board_theme_menu.addAction(act_scheme)
            self.color_scheme_actions[scheme] = act_scheme  # Store reference

        # Add separator and swap checker colors option
        board_theme_menu.addSeparator()
        self.act_swap_checkers = QAction("Swap Checker Colors", self)
        self.act_swap_checkers.setCheckable(True)
        self.act_swap_checkers.setChecked(self.settings.swap_checker_colors)
        self.act_swap_checkers.triggered.connect(self.toggle_swap_checker_colors)
        board_theme_menu.addAction(self.act_swap_checkers)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        act_shortcuts = QAction("&Tips && Shortcuts", self)
        act_shortcuts.setShortcut("Ctrl+/")
        act_shortcuts.triggered.connect(self.show_shortcuts_dialog)
        help_menu.addAction(act_shortcuts)

        help_menu.addSeparator()

        act_check_updates = QAction("&Check for Updates...", self)
        act_check_updates.triggered.connect(self.check_for_updates_manual)
        help_menu.addAction(act_check_updates)

        help_menu.addSeparator()

        act_website = QAction("&Visit Website", self)
        act_website.triggered.connect(self.show_website)
        help_menu.addAction(act_website)

        act_about = QAction("&About AnkiGammon", self)
        act_about.triggered.connect(self.show_about_dialog)
        help_menu.addAction(act_about)

    def _setup_connections(self):
        """Connect signals and slots."""
        self.decisions_parsed.connect(self.on_decisions_loaded)

    def _update_deck_label(self):
        """Update the deck name label with current settings."""
        export_method = "AnkiConnect" if self.settings.export_method == "ankiconnect" else "APKG"
        self.lbl_deck_name.setText(
            f"<div style='line-height: 1.5;'>"
            f"<div style='color: #a6adc8; font-size: 12px; font-weight: 500; margin-bottom: 6px;'>Exporting to</div>"
            f"<div style='font-size: 18px; font-weight: 600; color: #cdd6f4;'>{self.settings.deck_name} <span style='color: #6c7086; font-size: 13px; font-weight: 400;'>· {export_method}</span></div>"
            f"</div>"
        )

    def _restore_window_state(self):
        """Restore window size and position from QSettings."""
        settings = QSettings()

        # Window geometry
        geometry = settings.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)

        # Window state (splitter positions, etc.)
        state = settings.value("window/state")
        if state:
            self.restoreState(state)

    def _create_drop_overlay(self):
        """Create a visual overlay for drag-and-drop feedback."""
        # Make overlay a child of central widget for proper positioning
        self.drop_overlay = QWidget(self.centralWidget())
        self.drop_overlay.setStyleSheet("""
            QWidget {
                background-color: rgba(137, 180, 250, 0.15);
                border: 3px dashed #89b4fa;
                border-radius: 12px;
            }
        """)

        # Create layout for overlay content
        overlay_layout = QVBoxLayout(self.drop_overlay)
        overlay_layout.setAlignment(Qt.AlignCenter)

        # Icon
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon('fa6s.file-import', color='#89b4fa').pixmap(64, 64))
        icon_label.setAlignment(Qt.AlignCenter)
        overlay_layout.addWidget(icon_label)

        # Text
        text_label = QLabel("Drop file to import")
        text_label.setStyleSheet("""
            QLabel {
                color: #89b4fa;
                font-size: 18px;
                font-weight: 600;
                background: transparent;
                border: none;
                padding: 12px;
            }
        """)
        text_label.setAlignment(Qt.AlignCenter)
        overlay_layout.addWidget(text_label)

        # Initially hidden
        self.drop_overlay.hide()
        self.drop_overlay.setAttribute(Qt.WA_TransparentForMouseEvents)  # Don't block mouse events

    @Slot()
    def on_add_positions_clicked(self):
        """Handle add positions button click."""
        dialog = InputDialog(self.settings, self)
        dialog.positions_added.connect(self._on_positions_added)

        dialog.exec()

    @Slot(list)
    def _on_positions_added(self, decisions):
        """Handle positions added from input dialog."""
        if not decisions:
            return

        # Append to current decisions
        self.current_decisions.extend(decisions)
        self.btn_export.setEnabled(True)
        self.list_header_row.show()

        # Update position list
        self.position_list.set_decisions(self.current_decisions)

    @Slot(list)
    def on_positions_deleted(self, indices: list):
        """Handle deletion of multiple positions."""
        # Sort indices in descending order and delete
        for index in sorted(indices, reverse=True):
            if 0 <= index < len(self.current_decisions):
                self.current_decisions.pop(index)

        # Refresh the position list
        self.position_list.set_decisions(self.current_decisions)

        # Disable export and hide clear all if no positions remain
        if not self.current_decisions:
            self.btn_export.setEnabled(False)
            self.list_header_row.hide()
            # Show welcome screen
            self.preview.setHtml(self.welcome_html)
            self.preview.update()  # Force repaint to avoid black screen issue

    @Slot()
    def on_clear_all_clicked(self):
        """Handle clear all button click."""
        if not self.current_decisions:
            return

        # Show confirmation dialog
        reply = silent_messagebox.question(
            self,
            "Clear All Positions",
            f"Are you sure you want to clear all {len(self.current_decisions)} position(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Clear all decisions
            self.current_decisions.clear()
            self.position_list.set_decisions(self.current_decisions)
            self.btn_export.setEnabled(False)
            self.list_header_row.hide()

            # Show welcome screen
            self.preview.setHtml(self.welcome_html)
            self.preview.update()  # Force repaint to avoid black screen issue

    @Slot(list)
    def on_decisions_loaded(self, decisions):
        """Handle newly loaded decisions."""
        self.current_decisions = decisions
        self.btn_export.setEnabled(True)
        self.list_header_row.show()

        # Update position list
        self.position_list.set_decisions(decisions)

    def show_decision(self, decision: Decision):
        """Display a decision in the preview pane."""
        # Generate SVG for the position
        svg = self.renderer.render_svg(
            decision.position,
            dice=decision.dice,
            on_roll=decision.on_roll,
            cube_value=decision.cube_value,
            cube_owner=decision.cube_owner,
            score_x=decision.score_x,
            score_o=decision.score_o,
            match_length=decision.match_length,
            score_format=self.settings.score_format,
        )

        # Wrap SVG in minimal HTML with dark theme
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                html, body {{
                    margin: 0;
                    padding: 0;
                    height: 100%;
                    overflow: hidden;
                }}
                body {{
                    padding: 20px;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    background: linear-gradient(135deg, #1e1e2e 0%, #181825 100%);
                    box-sizing: border-box;
                }}
                svg {{
                    max-width: 100%;
                    max-height: 100%;
                    height: auto;
                    filter: drop-shadow(0 10px 30px rgba(0, 0, 0, 0.5));
                    border-radius: 12px;
                }}
            </style>
        </head>
        <body>
            {svg}
        </body>
        </html>
        """

        self.preview.setHtml(html)
        self.preview.update()  # Force repaint to avoid black screen issue

    @Slot()
    def on_edit_deck_name(self):
        """Handle deck name edit button click."""
        # Create input dialog
        dialog = QInputDialog(self)
        dialog.setWindowTitle("Edit Deck Name")
        dialog.setLabelText("Enter deck name:")
        dialog.setTextValue(self.settings.deck_name)

        # Use a timer to set cursor pointers after dialog widgets are created
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QDialogButtonBox

        def set_button_cursors():
            button_box = dialog.findChild(QDialogButtonBox)
            if button_box:
                for button in button_box.buttons():
                    button.setCursor(Qt.PointingHandCursor)

        QTimer.singleShot(0, set_button_cursors)

        # Show dialog and get result
        ok = dialog.exec()
        new_name = dialog.textValue()

        if ok and new_name.strip():
            self.settings.deck_name = new_name.strip()
            self._update_deck_label()

    @Slot()
    def on_settings_clicked(self):
        """Handle settings button click."""
        dialog = SettingsDialog(self.settings, self)
        dialog.settings_changed.connect(self.on_settings_changed)
        dialog.exec()

    @Slot(Settings)
    def on_settings_changed(self, settings: Settings):
        """Handle settings changes."""
        # Update renderer with new color scheme and orientation
        scheme = get_scheme(settings.color_scheme)
        if settings.swap_checker_colors:
            scheme = scheme.with_swapped_checkers()
        self.renderer = SVGBoardRenderer(
            color_scheme=scheme,
            orientation=settings.board_orientation
        )

        # Update menu checkmarks if color scheme changed
        for scheme_name, action in self.color_scheme_actions.items():
            action.setChecked(scheme_name == settings.color_scheme)

        # Update swap checkers checkbox
        self.act_swap_checkers.setChecked(settings.swap_checker_colors)

        # Update deck name label
        self._update_deck_label()

        # Refresh position list with new score format
        if self.current_decisions:
            current_row = self.position_list.currentRow()
            self.position_list.set_decisions(self.current_decisions)
            if current_row >= 0:
                self.position_list.setCurrentRow(current_row)

        # Refresh current preview if a decision is displayed
        if self.current_decisions:
            selected = self.position_list.get_selected_decision()
            if selected:
                self.show_decision(selected)

    @Slot()
    def on_export_clicked(self):
        """Handle export button click."""
        if not self.current_decisions:
            silent_messagebox.warning(
                self,
                "No Positions",
                "Please add positions first"
            )
            return

        dialog = ExportDialog(self.current_decisions, self.settings, self)
        dialog.export_succeeded.connect(self.on_export_succeeded)
        dialog.exec()

    @Slot()
    def on_regenerate_clicked(self):
        """Handle regenerate cards menu action."""
        from ankigammon.gui.dialogs.regenerate_dialog import RegenerateDialog
        dialog = RegenerateDialog(self.settings, self)
        dialog.exec()

    @Slot()
    def on_export_succeeded(self):
        """Handle successful export by optionally clearing the positions list."""
        if not self.current_decisions:
            return

        if not self.settings.clear_positions_after_export:
            return

        # Clear all decisions
        self.current_decisions.clear()
        self.position_list.set_decisions(self.current_decisions)
        self.btn_export.setEnabled(False)
        self.list_header_row.hide()

        # Show welcome screen
        self.preview.setHtml(self.welcome_html)
        self.preview.update()  # Force repaint to avoid black screen issue

    @Slot(str)
    def change_color_scheme(self, scheme: str):
        """Change the color scheme."""
        self.settings.color_scheme = scheme

        # Update checkmarks: uncheck all, then check the selected one
        for scheme_name, action in self.color_scheme_actions.items():
            action.setChecked(scheme_name == scheme)

        self.on_settings_changed(self.settings)

    @Slot(bool)
    def toggle_swap_checker_colors(self, checked: bool):
        """Toggle the swap checker colors setting."""
        self.settings.swap_checker_colors = checked
        self.on_settings_changed(self.settings)

    @Slot()
    def show_website(self):
        """Open the project website."""
        QDesktopServices.openUrl(QUrl("https://ankigammon.com/"))

    @Slot()
    def show_shortcuts_dialog(self):
        """Show keyboard shortcuts reference dialog."""
        dialog = ShortcutsDialog(self)
        dialog.exec()

    @Slot()
    def show_about_dialog(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About AnkiGammon",
            f"""<style>
            a {{ color: #3daee9; text-decoration: none; font-weight: bold; }}
            a:hover {{ text-decoration: underline; }}
            </style>
            <h2>AnkiGammon</h2>
            <p>Version {__version__}</p>
            <p>Convert backgammon position analysis into interactive Anki flashcards.</p>
            <p>Built with PySide6 and Qt.</p>

            <h3>Special Thanks</h3>
            <p>OilSpillDuckling<br>Eran & OpenGammon<br>Orad & Backgammon101<br>HerJe</p>

            <p><a href="https://github.com/Deinonychus999/AnkiGammon">GitHub Repository</a> | <a href="https://ko-fi.com/ankigammon">Donate</a></p>
            """
        )

    def _ensure_played_move_in_candidates(self, decision: Decision, played_move: Move) -> None:
        """
        Ensure the played move is in the top N candidates for MCQ display.

        If the played move is not in the top N analyzed moves (where N is max_mcq_options),
        insert it at position N-1 (last slot) to ensure it appears as an option.

        Args:
            decision: The decision object to modify
            played_move: The move that was actually played
        """
        # Get the number of MCQ options from settings
        max_options = self.settings.max_mcq_options

        # Check if played move is already in the top N candidates
        top_n = decision.candidate_moves[:max_options]

        # If played move is already in top N, nothing to do
        if played_move in top_n:
            return

        # Move is not in top N - insert it at position N-1 (last slot)
        decision.candidate_moves.remove(played_move)
        decision.candidate_moves.insert(max_options - 1, played_move)

    def _filter_decisions_by_import_options(
        self,
        decisions: list[Decision],
        checker_threshold: float,
        cube_threshold: float,
        include_player_x: bool,
        include_player_o: bool
    ) -> list[Decision]:
        """
        Filter decisions based on import options.

        Args:
            decisions: All parsed decisions
            checker_threshold: Error threshold for checker play (positive value, e.g., 0.080)
            cube_threshold: Error threshold for cube decisions (positive value, e.g., 0.080)
            include_player_x: Include Player.X mistakes
            include_player_o: Include Player.O mistakes

        Returns:
            Filtered list of decisions
        """
        from ankigammon.models import Player, DecisionType
        import logging
        logger = logging.getLogger(__name__)

        filtered = []

        cube_decisions_found = sum(1 for d in decisions if d.decision_type == DecisionType.CUBE_ACTION)
        logger.info(f"DEBUG: Filtering {len(decisions)} total decisions ({cube_decisions_found} cube decisions)")

        for decision in decisions:
            # Skip decisions with no moves
            if not decision.candidate_moves:
                continue

            # Find the move that was actually played in the game
            played_move = next((m for m in decision.candidate_moves if m.was_played), None)

            # Skip if no move is marked as played
            if not played_move:
                continue

            # Handle cube and checker play decisions differently
            if decision.decision_type == DecisionType.CUBE_ACTION:
                # Check which player made the error
                attr = decision.get_cube_error_attribution()
                doubler = attr['doubler']
                responder = attr['responder']
                doubler_error = attr['doubler_error']
                responder_error = attr['responder_error']

                logger.info(f"DEBUG: Cube decision - doubler={doubler}, doubler_error={doubler_error}, responder={responder}, responder_error={responder_error}, cube_threshold={cube_threshold}")

                # Determine which player(s) made errors above threshold
                doubler_made_error = doubler_error is not None and abs(doubler_error) >= cube_threshold
                responder_made_error = responder_error is not None and abs(responder_error) >= cube_threshold

                logger.info(f"DEBUG: doubler_made_error={doubler_made_error}, responder_made_error={responder_made_error}")

                # Skip if no errors above threshold
                if not doubler_made_error and not responder_made_error:
                    logger.info(f"DEBUG: Skipping cube decision - no errors above threshold")
                    continue

                # Check if we should include this decision based on player filter
                include_decision = False

                if doubler == Player.X and doubler_made_error and include_player_x:
                    include_decision = True
                if doubler == Player.O and doubler_made_error and include_player_o:
                    include_decision = True
                if responder == Player.X and responder_made_error and include_player_x:
                    include_decision = True
                if responder == Player.O and responder_made_error and include_player_o:
                    include_decision = True

                logger.info(f"DEBUG: include_decision={include_decision} (include_player_x={include_player_x}, include_player_o={include_player_o})")

                if include_decision:
                    # Include the played move in MCQ candidates
                    self._ensure_played_move_in_candidates(decision, played_move)
                    filtered.append(decision)
                    logger.info(f"DEBUG: Added cube decision to filtered list")
            else:
                # For checker play from XG binary files, use XG's authoritative ErrMove field
                # Otherwise fall back to recalculated error
                if decision.xg_error_move is not None:
                    # Use XG's ErrMove field (already absolute value)
                    error_magnitude = decision.xg_error_move
                elif played_move.xg_error is not None:
                    # Use XG text parser's calculated error
                    error_magnitude = abs(played_move.xg_error)
                else:
                    # Use recalculated error (for other sources)
                    error_magnitude = played_move.error

                # Only include if error is at or above threshold
                if error_magnitude < checker_threshold:
                    continue

                # Check player filter - error belongs to the player on roll
                if decision.on_roll == Player.X and not include_player_x:
                    continue
                if decision.on_roll == Player.O and not include_player_o:
                    continue

                # Include the played move in MCQ candidates
                self._ensure_played_move_in_candidates(decision, played_move)
                filtered.append(decision)

        cube_decisions_filtered = sum(1 for d in filtered if d.decision_type == DecisionType.CUBE_ACTION)
        logger.info(f"DEBUG: After filtering: {len(filtered)} decisions ({cube_decisions_filtered} cube decisions)")

        return filtered

    def _import_match_file(self, file_path: str) -> Tuple[List[Decision], int]:
        """
        Import match file with analysis via GnuBG.

        Supports both .mat (Jellyfish) and .sgf (Smart Game Format) files.

        Args:
            file_path: Path to match file (.mat or .sgf)

        Returns:
            Tuple of (filtered_decisions, total_count) or (None, None) if cancelled/failed
        """
        from PySide6.QtWidgets import QMessageBox, QProgressDialog
        from PySide6.QtCore import Qt
        from ankigammon.gui.dialogs.import_options_dialog import ImportOptionsDialog
        import logging

        logger = logging.getLogger(__name__)

        # Check if GnuBG is configured
        if not self.settings.is_gnubg_available():
            # Only show the dialog once per import batch
            if not self._gnubg_check_shown:
                self._gnubg_check_shown = True
                result = silent_messagebox.question(
                    self,
                    "GnuBG Required",
                    "Match file analysis requires GNU Backgammon.\n\n"
                    "Would you like to configure it in Settings?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if result == QMessageBox.StandardButton.Yes:
                    self.on_settings_clicked()
            return None, None

        # Extract player names based on file type
        from ankigammon.parsers.gnubg_match_parser import GNUBGMatchParser
        from pathlib import Path

        file_ext = Path(file_path).suffix.lower()
        if file_ext == '.sgf':
            # Extract from SGF file
            from ankigammon.parsers.sgf_parser import extract_player_names_from_sgf
            player1_name, player2_name = extract_player_names_from_sgf(file_path)
        else:
            # Extract from .mat file
            player1_name, player2_name = GNUBGMatchParser.extract_player_names_from_mat(file_path)

        # Show import options dialog with actual player names
        import_dialog = ImportOptionsDialog(
            self.settings,
            player1_name=player1_name,
            player2_name=player2_name,
            parent=self
        )

        if not import_dialog.exec():
            # User cancelled
            return None, None

        # Get filter options
        checker_threshold, cube_threshold, include_player_x, include_player_o = import_dialog.get_options()

        # Create progress dialog with spinner
        progress = QProgressDialog(
            f"Analyzing match with GnuBG ({self.settings.gnubg_analysis_ply}-ply)...",
            "Cancel",
            0,
            0,
            self
        )
        progress.setWindowTitle("Analyzing Match")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)  # Show immediately
        progress.setMinimumWidth(500)

        # Store results
        self._analysis_results = None

        # Create and configure worker thread
        self._analysis_worker = MatchAnalysisWorker(
            file_path=file_path,
            settings=self.settings,
            checker_threshold=checker_threshold,
            cube_threshold=cube_threshold,
            include_player_x=include_player_x,
            include_player_o=include_player_o,
            filter_func=self._filter_decisions_by_import_options,
            max_mcq_options=self.settings.max_mcq_options
        )

        # Connect signals
        self._analysis_worker.status_message.connect(
            lambda msg: progress.setLabelText(msg)
        )
        self._analysis_worker.finished.connect(
            lambda success, message, decisions, total: self._on_analysis_finished(
                success, message, decisions, total, progress
            )
        )
        progress.canceled.connect(self._analysis_worker.cancel)

        # Start worker
        self._analysis_worker.start()

        # Show progress dialog (blocks until worker emits finished signal or user cancels)
        result = progress.exec()

        # Check if user cancelled
        if progress.wasCanceled() or self._analysis_results is None:
            logger.info("Analysis cancelled by user")
            # Wait for worker to finish cleanup
            if hasattr(self, '_analysis_worker'):
                self._analysis_worker.wait(2000)
            return None, None

        # Return results
        return self._analysis_results

    @Slot(bool, str, list, int, object)
    def _on_analysis_finished(self, success: bool, message: str,
                             decisions: List[Decision], total_count: int,
                             progress_dialog):
        """Handle completion of match analysis worker."""
        from PySide6.QtWidgets import QMessageBox
        import logging

        logger = logging.getLogger(__name__)

        if success:
            logger.info(f"Analysis completed: {len(decisions)} positions filtered from {total_count} total")
            self._analysis_results = (decisions, total_count)
            progress_dialog.accept()
        else:
            # Show error message unless user cancelled
            if message != "Cancelled":
                silent_messagebox.critical(
                    self,
                    "Analysis Failed",
                    message
                )
            self._analysis_results = (None, None)
            progress_dialog.close()

        # Cleanup worker
        if hasattr(self, '_analysis_worker'):
            self._analysis_worker.deleteLater()
            del self._analysis_worker

    @Slot()
    def on_import_file_clicked(self):
        """Handle import file menu action."""
        from PySide6.QtWidgets import QFileDialog

        # Show file dialog (allow multiple file selection)
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Import Backgammon File(s)",
            "",
            "All Supported Files (*.xg *.xgp *.mat *.txt *.sgf);;XG Files (*.xg *.xgp);;Match Files (*.mat *.txt *.sgf);;All Files (*)"
        )

        if not file_paths:
            return

        # Reset GnuBG check flag for this batch of imports
        self._gnubg_check_shown = False

        # Track if this is a batch import (multiple .xgp files)
        xgp_files = [f for f in file_paths if f.lower().endswith('.xgp')]
        if len(xgp_files) > 1:
            # Set flag to accumulate results for .xgp files
            self._in_batch_import = True

        # Add to import queue and start processing
        self._import_queue.extend(file_paths)
        self._process_import_queue()

    def dragEnterEvent(self, event):
        """Handle drag enter event - accept if it contains valid files."""
        if event.mimeData().hasUrls():
            # Accept any file - format detector will validate
            urls = event.mimeData().urls()
            for url in urls:
                if url.isLocalFile():
                    # Show visual overlay
                    self._show_drop_overlay()
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragLeaveEvent(self, event):
        """Handle drag leave event - hide overlay when drag leaves the window."""
        self._hide_drop_overlay()
        event.accept()

    def dropEvent(self, event):
        """Handle drop event - import the dropped backgammon files."""
        # Hide overlay immediately
        self._hide_drop_overlay()

        if not event.mimeData().hasUrls():
            event.ignore()
            return

        # Collect file paths to import
        file_paths = []
        urls = event.mimeData().urls()
        for url in urls:
            if url.isLocalFile():
                file_paths.append(url.toLocalFile())

        # Accept the drop event immediately
        event.acceptProposedAction()

        # Reset GnuBG check flag for this batch of imports
        self._gnubg_check_shown = False

        # Add files to import queue
        self._import_queue.extend(file_paths)

        # Track if this is a batch import (multiple .xgp files)
        xgp_files = [f for f in file_paths if f.lower().endswith('.xgp')]
        if len(xgp_files) > 1:
            # Set flag to accumulate results for .xgp files
            self._in_batch_import = True

        # Start processing the queue
        self._process_import_queue()

    def _show_drop_overlay(self):
        """Show the drop overlay with proper sizing."""
        # Resize overlay to cover the entire parent (central widget)
        self.drop_overlay.setGeometry(self.drop_overlay.parentWidget().rect())
        self.drop_overlay.raise_()  # Bring to front
        self.drop_overlay.show()

    def _hide_drop_overlay(self):
        """Hide the drop overlay."""
        self.drop_overlay.hide()

    def _process_import_queue(self):
        """Process files from the import queue sequentially."""
        # If already processing, do nothing
        if self._import_in_progress:
            return

        # If queue is empty, show accumulated batch results and return
        if not self._import_queue:
            self._show_batch_import_results()
            return

        # Mark as in progress
        self._import_in_progress = True

        # Get next file from queue
        file_path = self._import_queue.pop(0)

        # Use QTimer to defer processing to avoid blocking the UI
        # This also ensures the dialog from the previous import has fully closed
        def process_file():
            try:
                self._import_file(file_path)
            finally:
                # Mark as not in progress and process next file
                self._import_in_progress = False
                # Use QTimer to ensure UI updates properly between imports
                QTimer.singleShot(100, self._process_import_queue)

        QTimer.singleShot(0, process_file)

    def _show_batch_import_results(self):
        """Show combined success message for batch imports."""
        if not self._batch_import_results:
            # Reset batch flag even if no results
            self._in_batch_import = False
            return

        # Calculate total positions imported
        total_positions = sum(self._batch_import_results)
        file_count = len(self._batch_import_results)

        # Build message - simple summary without listing files
        message = f"Imported {total_positions} position(s) from {file_count} file(s)"

        # Show the dialog
        silent_messagebox.information(
            self,
            "Import Successful",
            message
        )

        # Clear accumulated results and reset batch flag
        self._batch_import_results.clear()
        self._in_batch_import = False

    def _import_file(self, file_path: str):
        """
        Import a file at the given path.
        This is a helper method that can be called from both the menu action
        and the drag-and-drop handler.
        """
        from ankigammon.gui.format_detector import FormatDetector, InputFormat
        from ankigammon.parsers.xg_binary_parser import XGBinaryParser
        import logging

        logger = logging.getLogger(__name__)

        try:
            # Read file
            with open(file_path, 'rb') as f:
                data = f.read()

            # Detect format
            detector = FormatDetector(self.settings)
            result = detector.detect_binary(data)

            logger.info(f"Detected format: {result.format}, count: {result.count}")

            # Parse based on format
            decisions = []
            total_count = 0  # Track total before filtering (for XG binary)

            if result.format == InputFormat.XG_BINARY:
                # Check if this is a position file (.xgp) or match file (.xg)
                is_position_file = file_path.lower().endswith('.xgp')

                if is_position_file:
                    # Position files contain a single position - import directly without filtering
                    decisions = XGBinaryParser.parse_file(file_path)
                    total_count = len(decisions)
                    logger.info(f"Imported {len(decisions)} position(s) from .xgp file")
                else:
                    # Match files may contain many positions - show import options dialog
                    # Extract player names from XG file
                    player1_name, player2_name = XGBinaryParser.extract_player_names(file_path)

                    # Show import options dialog for XG match files
                    import_dialog = ImportOptionsDialog(
                        self.settings,
                        player1_name=player1_name,
                        player2_name=player2_name,
                        parent=self
                    )
                    if import_dialog.exec():
                        # User accepted - get options
                        checker_threshold, cube_threshold, include_player_x, include_player_o = import_dialog.get_options()

                        # Parse all decisions
                        all_decisions = XGBinaryParser.parse_file(file_path)
                        total_count = len(all_decisions)

                        # Filter based on user options
                        decisions = self._filter_decisions_by_import_options(
                            all_decisions,
                            checker_threshold,
                            cube_threshold,
                            include_player_x,
                            include_player_o
                        )

                        logger.info(f"Filtered {len(decisions)} positions from {total_count} total")
                    else:
                        # User cancelled
                        return

            elif result.format == InputFormat.MATCH_FILE or result.format == InputFormat.SGF_FILE:
                # Check if this is an SGF position file (vs a match file)
                is_sgf_position = False
                if result.format == InputFormat.SGF_FILE:
                    from ankigammon.parsers.sgf_parser import is_sgf_position_file
                    is_sgf_position = is_sgf_position_file(file_path)

                if is_sgf_position:
                    # Position files are imported directly without analysis
                    # Analysis happens later when exporting
                    from pathlib import Path
                    from ankigammon.parsers.sgf_parser import SGFParser
                    from ankigammon.models import Decision, DecisionType, Player
                    from ankigammon.utils.gnubg_analyzer import GNUBGAnalyzer
                    import tempfile
                    import subprocess

                    try:
                        # Convert SGF to .mat format using GnuBG (just to get the GNUID position)
                        analyzer = GNUBGAnalyzer(self.settings.gnubg_path, 0)
                        temp_dir = Path(tempfile.mkdtemp(prefix="sgf_import_"))
                        mat_path = temp_dir / "position.mat"

                        # Just load and export the position without analysis
                        gnubg_commands = [
                            f'load match "{Path(file_path).absolute()}"',
                            f'export match text "{mat_path.absolute()}"'
                        ]
                        cmd_file = analyzer._create_command_file_from_list(gnubg_commands)

                        kwargs = {
                            'stdout': subprocess.PIPE,
                            'stderr': subprocess.PIPE,
                            'text': True,
                        }
                        if sys.platform == 'win32':
                            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

                        gnubg_result = subprocess.run(
                            [self.settings.gnubg_path, "-t", "-q", "-c", cmd_file],
                            **kwargs,
                            timeout=30
                        )

                        if gnubg_result.returncode != 0:
                            raise RuntimeError(f"GnuBG failed: {gnubg_result.stderr}")

                        # Parse the exported match file to get position
                        with open(mat_path, 'r') as f:
                            mat_content = f.read()

                        # Extract GNUID from the exported file
                        import re
                        gnuid_match = re.search(r'Position ID:\s+([A-Za-z0-9+/=]+)', mat_content)
                        match_id_match = re.search(r'Match ID\s*:\s+([A-Za-z0-9+/=]+)', mat_content)

                        if not gnuid_match:
                            raise ValueError("Could not extract position from SGF file")

                        from ankigammon.utils.gnuid import parse_gnuid
                        gnuid_str = gnuid_match.group(1)
                        if match_id_match:
                            gnuid_str += ":" + match_id_match.group(1)

                        position, metadata = parse_gnuid(gnuid_str)

                        # Generate XGID for the position
                        xgid = position.to_xgid(
                            cube_value=metadata.get('cube_value', 1),
                            cube_owner=metadata.get('cube_owner'),
                            dice=metadata.get('dice'),
                            on_roll=metadata.get('on_roll', Player.X),
                            score_x=metadata.get('score_x', 0),
                            score_o=metadata.get('score_o', 0),
                            match_length=metadata.get('match_length', 0),
                            crawford_jacoby=1 if metadata.get('crawford', False) else 0
                        )

                        # Create a decision with no analysis
                        decision = Decision(
                            position=position,
                            on_roll=metadata.get('on_roll', Player.X),
                            dice=metadata.get('dice'),
                            decision_type=DecisionType.CHECKER_PLAY if metadata.get('dice') else DecisionType.CUBE_ACTION,
                            candidate_moves=[],  # No analysis yet
                            score_x=metadata.get('score_x', 0),
                            score_o=metadata.get('score_o', 0),
                            match_length=metadata.get('match_length', 0),
                            cube_value=metadata.get('cube_value', 1),
                            cube_owner=metadata.get('cube_owner'),
                            crawford=metadata.get('crawford', False),
                            xgid=xgid,
                            source_description=f"Position from SGF file '{Path(file_path).name}'"
                        )

                        decisions = [decision]
                        total_count = 1

                        # Cleanup
                        import shutil
                        shutil.rmtree(temp_dir, ignore_errors=True)

                        logger.info(f"Imported 1 position from SGF position file (no analysis)")

                    except Exception as e:
                        logger.error(f"Failed to import SGF position file: {e}", exc_info=True)
                        silent_messagebox.critical(
                            self,
                            "Import Failed",
                            f"Failed to import SGF position file:\n\n{str(e)}"
                        )
                        return
                else:
                    # Import match file with analysis
                    decisions, total_count = self._import_match_file(file_path)
                    if decisions is None:
                        # User cancelled or error occurred
                        return

            else:
                silent_messagebox.warning(
                    self,
                    "Unknown Format",
                    f"Could not detect file format.\n\nSupported formats:\n- XG files (.xg, .xgp)\n- Match files (.mat, .sgf)\n\n{result.details}"
                )
                return

            # Add to current decisions
            self.current_decisions.extend(decisions)
            self.position_list.set_decisions(self.current_decisions)
            self.btn_export.setEnabled(True)
            self.list_header_row.show()

            # Show success message (or accumulate for batch)
            from pathlib import Path
            filename = Path(file_path).name

            # Determine if this was a position file (.xgp or SGF position file) import
            is_position_file = file_path.lower().endswith('.xgp')
            if result.format == InputFormat.SGF_FILE:
                from ankigammon.parsers.sgf_parser import is_sgf_position_file
                is_position_file = is_position_file or is_sgf_position_file(file_path)

            if self._in_batch_import and is_position_file:
                # Accumulate results for position file batch imports
                self._batch_import_results.append(len(decisions))
                logger.info(f"Accumulated import result: {len(decisions)} positions from {file_path}")
            else:
                # Show immediate success message for single imports or .xg match files
                filtered_count = len(decisions)
                message = f"Imported {filtered_count} position(s) from {filename}"
                if total_count > filtered_count:
                    message += f"\n(filtered from {total_count} total positions)"

                silent_messagebox.information(
                    self,
                    "Import Successful",
                    message
                )
                logger.info(f"Successfully imported {len(decisions)} positions from {file_path}")

        except FileNotFoundError:
            silent_messagebox.critical(
                self,
                "File Not Found",
                f"Could not find file: {file_path}"
            )
        except ValueError as e:
            silent_messagebox.critical(
                self,
                "Invalid Format",
                f"Invalid file format:\n{str(e)}"
            )
        except Exception as e:
            logger.error(f"Failed to import file {file_path}: {e}", exc_info=True)
            silent_messagebox.critical(
                self,
                "Import Failed",
                f"Failed to import file:\n{str(e)}"
            )

    def _check_for_updates_background(self):
        """Check for updates in the background (non-blocking)."""
        from datetime import datetime

        # Check if snoozed
        snooze_until = self.settings.snooze_update_until
        if snooze_until:
            try:
                snooze_time = datetime.fromisoformat(snooze_until)
                if datetime.now() < snooze_time:
                    return  # Still snoozed
            except (ValueError, AttributeError):
                pass

        # Start background check
        self._version_checker_thread = VersionCheckerThread(
            current_version=__version__,
            force_check=False
        )
        self._version_checker_thread.update_available.connect(self._on_update_available)
        self._version_checker_thread.start()

    @Slot()
    def check_for_updates_manual(self):
        """Manually check for updates (triggered by menu item)."""
        # Show checking dialog
        checking_dialog = CheckingUpdateDialog(self)
        checking_dialog.show()
        QApplication.processEvents()

        # Start version check
        self._version_checker_thread = VersionCheckerThread(
            current_version=__version__,
            force_check=True  # Force check even if recently checked
        )

        def on_check_complete():
            checking_dialog.close()

        def on_check_failed():
            checking_dialog.close()
            failed_dialog = UpdateCheckFailedDialog(self, __version__)
            failed_dialog.exec()

        self._version_checker_thread.update_available.connect(self._on_update_available)
        self._version_checker_thread.check_failed.connect(on_check_failed)
        self._version_checker_thread.check_complete.connect(on_check_complete)
        self._version_checker_thread.finished.connect(lambda: self._on_manual_check_no_update(checking_dialog))
        self._version_checker_thread.start()

    def _on_manual_check_no_update(self, checking_dialog):
        """Handle manual check when no update is found."""
        # Only show "no update" dialog if update_available or check_failed wasn't emitted
        if not hasattr(self._version_checker_thread, '_update_emitted') and not hasattr(self._version_checker_thread, '_check_failed'):
            checking_dialog.close()
            no_update = NoUpdateDialog(self, __version__)
            no_update.exec()

    @Slot(dict)
    def _on_update_available(self, release_info: dict):
        """Handle update availability notification.

        Args:
            release_info: Release information from GitHub API
        """
        from datetime import datetime

        # Mark that update was emitted (for manual check)
        if self._version_checker_thread:
            self._version_checker_thread._update_emitted = True

        # Show update dialog
        dialog = UpdateDialog(self, release_info, __version__)
        result = dialog.exec()

        # Handle user action
        if dialog.user_action == 'snooze':
            # Snooze for 24 hours
            self.settings.snooze_update_until = dialog.get_snooze_until()
        elif dialog.user_action == 'skip':
            # Skip this version entirely (set snooze to far future)
            self.settings.snooze_update_until = (
                datetime(2099, 1, 1).isoformat()
            )

    def resizeEvent(self, event):
        """Handle window resize - update overlay size."""
        super().resizeEvent(event)
        if hasattr(self, 'drop_overlay') and hasattr(self, 'centralWidget'):
            # Update overlay to match central widget size
            self.drop_overlay.setGeometry(self.drop_overlay.parentWidget().rect())

    def closeEvent(self, event):
        """Save window state on close."""
        settings = QSettings()
        settings.setValue("window/geometry", self.saveGeometry())
        settings.setValue("window/state", self.saveState())

        event.accept()
