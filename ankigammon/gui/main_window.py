"""
Main application window.
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QMessageBox, QInputDialog
)
from PySide6.QtCore import Qt, Signal, Slot, QUrl, QSettings, QSize
from PySide6.QtGui import QAction, QKeySequence, QDesktopServices
from PySide6.QtWebEngineWidgets import QWebEngineView
import qtawesome as qta
import base64

from ankigammon.settings import Settings
from ankigammon.renderer.svg_board_renderer import SVGBoardRenderer
from ankigammon.renderer.color_schemes import get_scheme
from ankigammon.models import Decision
from ankigammon.gui.widgets import PositionListWidget
from ankigammon.gui.dialogs import SettingsDialog, ExportDialog, InputDialog, ImportOptionsDialog
from ankigammon.gui.resources import get_resource_path


class MainWindow(QMainWindow):
    """Main application window for AnkiGammon."""

    # Signals
    decisions_parsed = Signal(list)  # List[Decision]

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.current_decisions = []
        self.renderer = SVGBoardRenderer(
            color_scheme=get_scheme(settings.color_scheme),
            orientation=settings.board_orientation
        )
        self.color_scheme_actions = {}  # Store references to color scheme menu actions

        # Enable drag and drop
        self.setAcceptDrops(True)

        self._setup_ui()
        self._setup_menu_bar()
        self._setup_connections()
        self._restore_window_state()

        # Create drop overlay (will be shown during drag operations)
        self._create_drop_overlay()

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

        welcome_html = f"""
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
        self.preview.setHtml(welcome_html)
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

        # Button row: Add Positions and Import File
        btn_row = QWidget()
        btn_row_layout = QHBoxLayout(btn_row)
        btn_row_layout.setContentsMargins(0, 0, 0, 0)
        btn_row_layout.setSpacing(8)

        # Add Positions button (primary) - blue background needs dark icons
        self.btn_add_positions = QPushButton("  Add Positions...")
        self.btn_add_positions.setIcon(qta.icon('fa6s.clipboard-list', color='#1e1e2e'))
        self.btn_add_positions.setIconSize(QSize(18, 18))
        self.btn_add_positions.clicked.connect(self.on_add_positions_clicked)
        self.btn_add_positions.setToolTip("Paste position IDs or full XG analysis")
        self.btn_add_positions.setCursor(Qt.PointingHandCursor)
        btn_row_layout.addWidget(self.btn_add_positions, stretch=1)

        # Import File button (equal primary) - full-sized with text + icon
        self.btn_import_file = QPushButton("  Import File...")
        self.btn_import_file.setIcon(qta.icon('fa6s.file-import', color='#1e1e2e'))
        self.btn_import_file.setIconSize(QSize(18, 18))
        self.btn_import_file.clicked.connect(self.on_import_file_clicked)
        self.btn_import_file.setToolTip("Import .xg file")
        self.btn_import_file.setCursor(Qt.PointingHandCursor)
        btn_row_layout.addWidget(self.btn_import_file, stretch=1)

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
        self.position_list = PositionListWidget()
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

        act_import_file = QAction("&Import File...", self)
        act_import_file.setShortcut("Ctrl+O")
        act_import_file.triggered.connect(self.on_import_file_clicked)
        file_menu.addAction(act_import_file)

        file_menu.addSeparator()

        act_export = QAction("&Export to Anki...", self)
        act_export.setShortcut("Ctrl+E")
        act_export.triggered.connect(self.on_export_clicked)
        file_menu.addAction(act_export)

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

        # Help menu
        help_menu = menubar.addMenu("&Help")

        act_docs = QAction("&Documentation", self)
        act_docs.triggered.connect(self.show_documentation)
        help_menu.addAction(act_docs)

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
        text_label = QLabel("Drop .xg file to import")
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

        # Refresh list ONCE (more efficient)
        self.position_list.set_decisions(self.current_decisions)

        # Disable export and hide clear all if no positions remain
        if not self.current_decisions:
            self.btn_export.setEnabled(False)
            self.list_header_row.hide()
            # Show welcome screen
            welcome_html = """
                <!DOCTYPE html>
                <html>
                <head>
                    <style>
                        body {
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
                        }
                        .welcome {
                            text-align: center;
                            padding: 40px;
                        }
                        h1 {
                            color: #f5e0dc;
                            font-size: 32px;
                            margin-bottom: 16px;
                            font-weight: 700;
                        }
                        p {
                            color: #a6adc8;
                            font-size: 16px;
                            margin: 8px 0;
                        }
                        .icon {
                            margin-bottom: 24px;
                            opacity: 0.6;
                        }
                    </style>
                </head>
                <body>
                    <div class="welcome">
                        <div class="icon">
                            <svg width="140" height="90" viewBox="-5 0 90 45" xmlns="http://www.w3.org/2000/svg">
                                <!-- First die -->
                                <g transform="translate(0, 10)">
                                    <rect x="2" y="2" width="32" height="32" rx="4"
                                          fill="#f5e0dc" stroke="#45475a" stroke-width="1.5"
                                          transform="rotate(-15 18 18)"/>
                                    <!-- Pips for 5 -->
                                    <circle cx="10" cy="10" r="2.5" fill="#1e1e2e" transform="rotate(-15 18 18)"/>
                                    <circle cx="26" cy="10" r="2.5" fill="#1e1e2e" transform="rotate(-15 18 18)"/>
                                    <circle cx="18" cy="18" r="2.5" fill="#1e1e2e" transform="rotate(-15 18 18)"/>
                                    <circle cx="10" cy="26" r="2.5" fill="#1e1e2e" transform="rotate(-15 18 18)"/>
                                    <circle cx="26" cy="26" r="2.5" fill="#1e1e2e" transform="rotate(-15 18 18)"/>
                                </g>

                                <!-- Second die -->
                                <g transform="translate(36, 0)">
                                    <rect x="2" y="2" width="32" height="32" rx="4"
                                          fill="#f5e0dc" stroke="#45475a" stroke-width="1.5"
                                          transform="rotate(12 18 18)"/>
                                    <!-- Pips for 3 -->
                                    <circle cx="10" cy="10" r="2.5" fill="#1e1e2e" transform="rotate(12 18 18)"/>
                                    <circle cx="18" cy="18" r="2.5" fill="#1e1e2e" transform="rotate(12 18 18)"/>
                                    <circle cx="26" cy="26" r="2.5" fill="#1e1e2e" transform="rotate(12 18 18)"/>
                                </g>
                            </svg>
                        </div>
                        <h1>No Position Loaded</h1>
                        <p>Add positions to get started</p>
                    </div>
                </body>
                </html>
                """
            self.preview.setHtml(welcome_html)
            self.preview.update()  # Force repaint to avoid black screen issue

    @Slot()
    def on_clear_all_clicked(self):
        """Handle clear all button click."""
        if not self.current_decisions:
            return

        # Show confirmation dialog
        reply = QMessageBox.question(
            self,
            "Clear All Positions",
            f"Are you sure you want to clear all {len(self.current_decisions)} position(s)?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # Clear all decisions
            self.current_decisions.clear()
            self.position_list.set_decisions(self.current_decisions)
            self.btn_export.setEnabled(False)
            self.list_header_row.hide()

            # Show welcome screen
            welcome_html = """
                <!DOCTYPE html>
                <html>
                <head>
                    <style>
                        body {
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
                        }
                        .welcome {
                            text-align: center;
                            padding: 40px;
                        }
                        h1 {
                            color: #f5e0dc;
                            font-size: 32px;
                            margin-bottom: 16px;
                            font-weight: 700;
                        }
                        p {
                            color: #a6adc8;
                            font-size: 16px;
                            margin: 8px 0;
                        }
                        .icon {
                            margin-bottom: 24px;
                            opacity: 0.6;
                        }
                    </style>
                </head>
                <body>
                    <div class="welcome">
                        <div class="icon">
                            <svg width="140" height="90" viewBox="-5 0 90 45" xmlns="http://www.w3.org/2000/svg">
                                <!-- First die -->
                                <g transform="translate(0, 10)">
                                    <rect x="2" y="2" width="32" height="32" rx="4"
                                          fill="#f5e0dc" stroke="#45475a" stroke-width="1.5"
                                          transform="rotate(-15 18 18)"/>
                                    <!-- Pips for 5 -->
                                    <circle cx="10" cy="10" r="2.5" fill="#1e1e2e" transform="rotate(-15 18 18)"/>
                                    <circle cx="26" cy="10" r="2.5" fill="#1e1e2e" transform="rotate(-15 18 18)"/>
                                    <circle cx="18" cy="18" r="2.5" fill="#1e1e2e" transform="rotate(-15 18 18)"/>
                                    <circle cx="10" cy="26" r="2.5" fill="#1e1e2e" transform="rotate(-15 18 18)"/>
                                    <circle cx="26" cy="26" r="2.5" fill="#1e1e2e" transform="rotate(-15 18 18)"/>
                                </g>

                                <!-- Second die -->
                                <g transform="translate(36, 0)">
                                    <rect x="2" y="2" width="32" height="32" rx="4"
                                          fill="#f5e0dc" stroke="#45475a" stroke-width="1.5"
                                          transform="rotate(12 18 18)"/>
                                    <!-- Pips for 3 -->
                                    <circle cx="10" cy="10" r="2.5" fill="#1e1e2e" transform="rotate(12 18 18)"/>
                                    <circle cx="18" cy="18" r="2.5" fill="#1e1e2e" transform="rotate(12 18 18)"/>
                                    <circle cx="26" cy="26" r="2.5" fill="#1e1e2e" transform="rotate(12 18 18)"/>
                                </g>
                            </svg>
                        </div>
                        <h1>No Position Loaded</h1>
                        <p>Add positions to get started</p>
                    </div>
                </body>
                </html>
                """
            self.preview.setHtml(welcome_html)
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
        # Generate SVG using existing renderer (zero changes!)
        svg = self.renderer.render_svg(
            decision.position,
            dice=decision.dice,
            on_roll=decision.on_roll,
            cube_value=decision.cube_value,
            cube_owner=decision.cube_owner,
            score_x=decision.score_x,
            score_o=decision.score_o,
            match_length=decision.match_length,
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
        self.renderer = SVGBoardRenderer(
            color_scheme=get_scheme(settings.color_scheme),
            orientation=settings.board_orientation
        )

        # Update menu checkmarks if color scheme changed
        for scheme_name, action in self.color_scheme_actions.items():
            action.setChecked(scheme_name == settings.color_scheme)

        # Update deck name label
        self._update_deck_label()

        # Refresh current preview if a decision is displayed
        if self.current_decisions:
            selected = self.position_list.get_selected_decision()
            if selected:
                self.show_decision(selected)

    @Slot()
    def on_export_clicked(self):
        """Handle export button click."""
        if not self.current_decisions:
            QMessageBox.warning(
                self,
                "No Positions",
                "Please add positions first"
            )
            return

        dialog = ExportDialog(self.current_decisions, self.settings, self)
        dialog.exec()

    @Slot(str)
    def change_color_scheme(self, scheme: str):
        """Change the color scheme."""
        self.settings.color_scheme = scheme

        # Update checkmarks: uncheck all, then check the selected one
        for scheme_name, action in self.color_scheme_actions.items():
            action.setChecked(scheme_name == scheme)

        self.on_settings_changed(self.settings)

    @Slot()
    def show_documentation(self):
        """Show online documentation."""
        QDesktopServices.openUrl(QUrl("https://github.com/Deinonychus999/AnkiGammon"))

    @Slot()
    def show_about_dialog(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About AnkiGammon",
            """<h2>AnkiGammon</h2>
            <p>Version 1.0.0</p>
            <p>Convert backgammon position analysis into interactive Anki flashcards.</p>
            <p>Built with PySide6 and Qt.</p>

            <h3>Special Thanks</h3>
            <p>OilSpillDuckling<br>Eran & OpenGammon</p>

            <p><a href="https://github.com/Deinonychus999/AnkiGammon">GitHub Repository</a></p>
            """
        )

    def _filter_decisions_by_import_options(
        self,
        decisions: list[Decision],
        threshold: float,
        include_player_x: bool,
        include_player_o: bool
    ) -> list[Decision]:
        """
        Filter decisions based on import options.

        Args:
            decisions: All parsed decisions
            threshold: Error threshold (positive value, e.g., 0.080)
            include_player_x: Include Player.X mistakes
            include_player_o: Include Player.O mistakes

        Returns:
            Filtered list of decisions
        """
        from ankigammon.models import Player

        filtered = []

        for decision in decisions:
            # Check player filter
            if decision.on_roll == Player.X and not include_player_x:
                continue
            if decision.on_roll == Player.O and not include_player_o:
                continue

            # Skip decisions with no moves
            if not decision.candidate_moves:
                continue

            # Find the move that was actually played in the game
            played_move = next((m for m in decision.candidate_moves if m.was_played), None)

            # Fallback: if no move is marked as played, skip this decision
            # (This should not happen with proper XG files, but handles edge cases)
            if not played_move:
                continue

            # Use xg_error if available (convert to absolute value),
            # otherwise use error (already positive)
            error_magnitude = abs(played_move.xg_error) if played_move.xg_error is not None else played_move.error

            # Only include if error is at or above threshold
            if error_magnitude >= threshold:
                filtered.append(decision)

        return filtered

    @Slot()
    def on_import_file_clicked(self):
        """Handle import file menu action."""
        from PySide6.QtWidgets import QFileDialog

        # Show file dialog
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Backgammon File",
            "",
            "XG Binary (*.xg);;All Files (*.*)"
        )

        if not file_path:
            return

        # Use the shared import logic
        self._import_file(file_path)

    def dragEnterEvent(self, event):
        """Handle drag enter event - accept if it contains valid files."""
        if event.mimeData().hasUrls():
            # Check if any of the URLs are .xg files
            urls = event.mimeData().urls()
            for url in urls:
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if file_path.endswith('.xg'):
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
        """Handle drop event - import the dropped .xg files."""
        # Hide overlay immediately
        self._hide_drop_overlay()

        if not event.mimeData().hasUrls():
            event.ignore()
            return

        # Process each dropped file
        urls = event.mimeData().urls()
        for url in urls:
            if url.isLocalFile():
                file_path = url.toLocalFile()
                if file_path.endswith('.xg'):
                    # Import the file using the existing import logic
                    self._import_file(file_path)

        event.acceptProposedAction()

    def _show_drop_overlay(self):
        """Show the drop overlay with proper sizing."""
        # Resize overlay to cover the entire parent (central widget)
        self.drop_overlay.setGeometry(self.drop_overlay.parentWidget().rect())
        self.drop_overlay.raise_()  # Bring to front
        self.drop_overlay.show()

    def _hide_drop_overlay(self):
        """Hide the drop overlay."""
        self.drop_overlay.hide()

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
                # Extract player names from XG file
                player1_name, player2_name = XGBinaryParser.extract_player_names(file_path)

                # Show import options dialog for XG binary files
                import_dialog = ImportOptionsDialog(
                    self.settings,
                    player1_name=player1_name,
                    player2_name=player2_name,
                    parent=self
                )
                if import_dialog.exec():
                    # User accepted - get options
                    threshold, include_player_x, include_player_o = import_dialog.get_options()

                    # Parse all decisions
                    all_decisions = XGBinaryParser.parse_file(file_path)
                    total_count = len(all_decisions)

                    # Filter based on user options
                    decisions = self._filter_decisions_by_import_options(
                        all_decisions,
                        threshold,
                        include_player_x,
                        include_player_o
                    )

                    logger.info(f"Filtered {len(decisions)} positions from {total_count} total")
                else:
                    # User cancelled
                    return
            else:
                QMessageBox.warning(
                    self,
                    "Unknown Format",
                    f"Could not detect file format.\n\nOnly XG binary files (.xg) are supported for file import.\n\n{result.details}"
                )
                return

            # Add to current decisions
            self.current_decisions.extend(decisions)
            self.position_list.set_decisions(self.current_decisions)
            self.btn_export.setEnabled(True)
            self.list_header_row.show()

            # Show success message
            from pathlib import Path
            filename = Path(file_path).name

            # Show filtering info
            filtered_count = len(decisions)
            message = f"Imported {filtered_count} position(s) from {filename}"
            if total_count > filtered_count:
                message += f"\n(filtered from {total_count} total positions)"

            QMessageBox.information(
                self,
                "Import Successful",
                message
            )

            logger.info(f"Successfully imported {len(decisions)} positions from {file_path}")

        except FileNotFoundError:
            QMessageBox.critical(
                self,
                "File Not Found",
                f"Could not find file: {file_path}"
            )
        except ValueError as e:
            QMessageBox.critical(
                self,
                "Invalid Format",
                f"Invalid file format:\n{str(e)}"
            )
        except Exception as e:
            logger.error(f"Failed to import file {file_path}: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Import Failed",
                f"Failed to import file:\n{str(e)}"
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
