"""
Main application window.
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QMessageBox
)
from PySide6.QtCore import Qt, Signal, Slot, QUrl, QSettings, QSize
from PySide6.QtGui import QAction, QKeySequence, QDesktopServices
from PySide6.QtWebEngineWidgets import QWebEngineView
import qtawesome as qta

from flashgammon.settings import Settings
from flashgammon.parsers.xg_text_parser import XGTextParser
from flashgammon.renderer.svg_board_renderer import SVGBoardRenderer
from flashgammon.renderer.color_schemes import get_scheme
from flashgammon.models import Decision
from flashgammon.gui.widgets import PositionListWidget
from flashgammon.gui.dialogs import SettingsDialog, ExportDialog, InputDialog


class MainWindow(QMainWindow):
    """Main application window for FlashGammon."""

    # Signals
    decisions_parsed = Signal(list)  # List[Decision]

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.current_decisions = []
        self.parser = XGTextParser()
        self.renderer = SVGBoardRenderer(color_scheme=get_scheme(settings.color_scheme))
        self.color_scheme_actions = {}  # Store references to color scheme menu actions

        self._setup_ui()
        self._setup_menu_bar()
        self._setup_connections()
        self._restore_window_state()

    def _setup_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("FlashGammon - Backgammon Analysis to Anki")
        self.setMinimumSize(1000, 700)

        # Central widget with horizontal layout
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Left panel: Controls
        left_panel = self._create_left_panel()
        layout.addWidget(left_panel, stretch=1)

        # Right panel: Preview
        self.preview = QWebEngineView()
        self.preview.setContextMenuPolicy(Qt.NoContextMenu)  # Disable browser context menu
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
        title = QLabel("<h2>FlashGammon</h2>")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Add Positions button (primary) - blue background needs dark icons
        self.btn_add_positions = QPushButton("  Add Positions...")
        self.btn_add_positions.setIcon(qta.icon('fa6s.clipboard-list', color='#1e1e2e'))
        self.btn_add_positions.setIconSize(QSize(18, 18))
        self.btn_add_positions.clicked.connect(self.on_add_positions_clicked)
        self.btn_add_positions.setToolTip("Paste position IDs or full XG analysis")
        layout.addWidget(self.btn_add_positions)

        # Position list widget
        self.position_list = PositionListWidget()
        self.position_list.position_selected.connect(self.show_decision)
        self.position_list.position_deleted.connect(self.on_position_deleted)
        layout.addWidget(self.position_list, stretch=1)

        # Spacer
        layout.addSpacing(8)

        # Settings button
        self.btn_settings = QPushButton("  Settings")
        self.btn_settings.setIcon(qta.icon('fa6s.gear', color='#cdd6f4'))
        self.btn_settings.setIconSize(QSize(18, 18))
        self.btn_settings.setObjectName("btn_settings")
        self.btn_settings.clicked.connect(self.on_settings_clicked)
        layout.addWidget(self.btn_settings)

        # Export button - blue background needs dark icons
        self.btn_export = QPushButton("  Export to Anki")
        self.btn_export.setIcon(qta.icon('fa6s.file-export', color='#1e1e2e'))
        self.btn_export.setIconSize(QSize(18, 18))
        self.btn_export.setEnabled(False)
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
        from flashgammon.renderer.color_schemes import list_schemes
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

        act_about = QAction("&About FlashGammon", self)
        act_about.triggered.connect(self.show_about_dialog)
        help_menu.addAction(act_about)

    def _setup_connections(self):
        """Connect signals and slots."""
        self.decisions_parsed.connect(self.on_decisions_loaded)

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

    @Slot()
    def on_add_positions_clicked(self):
        """Handle add positions button click."""
        dialog = InputDialog(self.settings, self)
        dialog.positions_added.connect(self._on_positions_added)

        if dialog.exec():
            pending = dialog.get_pending_decisions()
            if pending:
                self.statusBar().showMessage(
                    f"Added {len(pending)} position(s)",
                    3000
                )

    @Slot(list)
    def _on_positions_added(self, decisions):
        """Handle positions added from input dialog."""
        if not decisions:
            return

        # Append to current decisions
        self.current_decisions.extend(decisions)
        self.btn_export.setEnabled(True)

        # Update position list
        self.position_list.set_decisions(self.current_decisions)

    @Slot(int)
    def on_position_deleted(self, index: int):
        """Handle position deletion from list."""
        if 0 <= index < len(self.current_decisions):
            # Remove from decisions list
            deleted = self.current_decisions.pop(index)

            # Update position list with new indices
            self.position_list.set_decisions(self.current_decisions)

            # Disable export if no positions remain
            if not self.current_decisions:
                self.btn_export.setEnabled(False)
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

            # Update status bar
            self.statusBar().showMessage(f"Deleted position #{index + 1}", 3000)

    @Slot(list)
    def on_decisions_loaded(self, decisions):
        """Handle newly loaded decisions."""
        self.current_decisions = decisions
        self.btn_export.setEnabled(True)

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
            cube_owner=decision.cube_owner
        )

        # Wrap SVG in minimal HTML with dark theme
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    margin: 0;
                    padding: 20px;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    background: linear-gradient(135deg, #1e1e2e 0%, #181825 100%);
                }}
                svg {{
                    max-width: 100%;
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

    @Slot()
    def on_settings_clicked(self):
        """Handle settings button click."""
        dialog = SettingsDialog(self.settings, self)
        dialog.settings_changed.connect(self.on_settings_changed)
        dialog.exec()

    @Slot(Settings)
    def on_settings_changed(self, settings: Settings):
        """Handle settings changes."""
        # Update renderer with new color scheme
        self.renderer = SVGBoardRenderer(color_scheme=get_scheme(settings.color_scheme))

        # Update menu checkmarks if color scheme changed
        for scheme_name, action in self.color_scheme_actions.items():
            action.setChecked(scheme_name == settings.color_scheme)

        # Refresh current preview if a decision is displayed
        if self.current_decisions:
            selected = self.position_list.get_selected_decision()
            if selected:
                self.show_decision(selected)

        self.statusBar().showMessage("Settings saved", 3000)

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
        QDesktopServices.openUrl(QUrl("https://github.com/yourusername/flashgammon"))

    @Slot()
    def show_about_dialog(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About FlashGammon",
            """<h2>FlashGammon</h2>
            <p>Version 1.0.0</p>
            <p>Convert eXtreme Gammon (XG) backgammon analysis into Anki flashcards.</p>
            <p>Built with PySide6 and Qt.</p>
            <p><a href="https://github.com/yourusername/flashgammon">GitHub Repository</a></p>
            """
        )

    def closeEvent(self, event):
        """Save window state on close."""
        settings = QSettings()
        settings.setValue("window/geometry", self.saveGeometry())
        settings.setValue("window/state", self.saveState())

        event.accept()
