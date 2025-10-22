"""
Smart input dialog for adding positions via paste.

Supports:
- Position IDs (XGID/GNUID) - analyzed with GnuBG
- Full XG analysis text - parsed directly
"""

from typing import List
from pathlib import Path

import qtawesome as qta

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QFrame, QSplitter, QWidget, QProgressDialog
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWebEngineWidgets import QWebEngineView

from flashgammon.settings import Settings
from flashgammon.models import Decision
from flashgammon.parsers.xg_text_parser import XGTextParser
from flashgammon.renderer.svg_board_renderer import SVGBoardRenderer
from flashgammon.renderer.color_schemes import get_scheme
from flashgammon.gui.widgets import SmartInputWidget
from flashgammon.gui.format_detector import InputFormat


class PendingPositionItem(QListWidgetItem):
    """List item for a pending position."""

    def __init__(self, decision: Decision, needs_analysis: bool = False):
        super().__init__()
        self.decision = decision
        self.needs_analysis = needs_analysis

        # Set display text
        self._update_display()

    def _update_display(self):
        """Update display text based on decision."""
        # Use consistent display format
        self.setText(self.decision.get_short_display_text())

        # Icon based on status - use semantic colors
        if self.needs_analysis:
            self.setIcon(qta.icon('fa6s.magnifying-glass', color='#89b4fa'))  # Info blue
        else:
            self.setIcon(qta.icon('fa6s.circle-check', color='#a6e3a1'))  # Success green

        # Tooltip with metadata + analysis status
        tooltip = self.decision.get_metadata_text()
        if self.needs_analysis:
            tooltip += "\n\nNeeds GnuBG analysis"
        else:
            tooltip += f"\n\n{len(self.decision.candidate_moves)} moves analyzed"

        self.setToolTip(tooltip)


class InputDialog(QDialog):
    """
    Dialog for smart position input.

    Allows users to paste:
    - Full XG analysis text (parsed directly)
    - Position IDs (XGID/GNUID) - analyzed with GnuBG

    Signals:
        positions_added(List[Decision]): Emitted when positions are added
    """

    positions_added = Signal(list)

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.pending_decisions: List[Decision] = []
        self.renderer = SVGBoardRenderer(color_scheme=get_scheme(settings.color_scheme))

        self.setWindowTitle("Add Positions")
        self.setModal(True)
        self.setMinimumSize(1100, 850)
        self.resize(1150, 900)  # Default size - taller for better preview

        self._setup_ui()
        self._setup_connections()

    def _setup_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Title
        title = QLabel("<h2>Add Positions to Export List</h2>")
        title.setStyleSheet("color: #f5e0dc; margin-bottom: 8px;")
        layout.addWidget(title)

        # Main content area (splitter)
        splitter = QSplitter(Qt.Horizontal)

        # Left side: Input area
        left_widget = self._create_input_panel()
        splitter.addWidget(left_widget)

        # Right side: Pending list + preview
        right_widget = self._create_pending_panel()
        splitter.addWidget(right_widget)

        # Set initial splitter ratio (50/50 balanced)
        splitter.setStretchFactor(0, 50)
        splitter.setStretchFactor(1, 50)

        layout.addWidget(splitter, stretch=1)

        # Bottom buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.btn_done = QPushButton("Done")
        self.btn_done.setStyleSheet("""
            QPushButton {
                background-color: #89b4fa;
                color: #1e1e2e;
                border: none;
                padding: 10px 24px;
                border-radius: 6px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #74c7ec;
            }
        """)
        self.btn_done.clicked.connect(self.accept)
        button_layout.addWidget(self.btn_done)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #45475a;
                color: #cdd6f4;
                border: none;
                padding: 10px 24px;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #585b70;
            }
        """)
        self.btn_cancel.clicked.connect(self.reject)
        button_layout.addWidget(self.btn_cancel)

        layout.addLayout(button_layout)

    def _create_input_panel(self) -> QWidget:
        """Create the input panel with smart input widget."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Smart input widget
        self.input_widget = SmartInputWidget(self.settings)
        layout.addWidget(self.input_widget, stretch=1)

        # Buttons
        button_layout = QHBoxLayout()

        self.btn_add = QPushButton("Add to List")
        self.btn_add.setStyleSheet("""
            QPushButton {
                background-color: #a6e3a1;
                color: #1e1e2e;
                border: none;
                padding: 8px 20px;
                border-radius: 6px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #94e2d5;
            }
            QPushButton:disabled {
                background-color: #45475a;
                color: #6c7086;
            }
        """)
        self.btn_add.clicked.connect(self._on_add_clicked)
        button_layout.addWidget(self.btn_add)

        self.btn_clear = QPushButton("Clear Input")
        self.btn_clear.setStyleSheet("""
            QPushButton {
                background-color: #45475a;
                color: #cdd6f4;
                border: none;
                padding: 8px 20px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #585b70;
            }
        """)
        self.btn_clear.clicked.connect(self.input_widget.clear_text)
        button_layout.addWidget(self.btn_clear)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        return panel

    def _create_pending_panel(self) -> QWidget:
        """Create the pending positions panel."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Label with count
        header_layout = QHBoxLayout()

        label = QLabel("Pending Export:")
        label.setStyleSheet("font-weight: 600; color: #cdd6f4;")
        header_layout.addWidget(label)

        self.count_label = QLabel("0 positions")
        self.count_label.setStyleSheet("color: #a6adc8; font-size: 11px;")
        header_layout.addWidget(self.count_label)

        header_layout.addStretch()

        self.btn_clear_all = QPushButton("Clear All")
        self.btn_clear_all.setStyleSheet("""
            QPushButton {
                background-color: #45475a;
                color: #cdd6f4;
                border: none;
                padding: 4px 12px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #f38ba8;
                color: #1e1e2e;
            }
        """)
        self.btn_clear_all.clicked.connect(self._on_clear_all_clicked)
        header_layout.addWidget(self.btn_clear_all)

        layout.addLayout(header_layout)

        # Create a vertical splitter between pending list and preview
        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)  # Prevent collapsing sections

        # Top section: Pending list
        self.pending_list = QListWidget()
        self.pending_list.setStyleSheet("""
            QListWidget {
                background-color: #1e1e2e;
                border: 2px solid #313244;
                border-radius: 8px;
                padding: 8px;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 4px;
                color: #cdd6f4;
            }
            QListWidget::item:selected {
                background-color: #45475a;
            }
            QListWidget::item:hover {
                background-color: #313244;
            }
        """)
        self.pending_list.currentItemChanged.connect(self._on_selection_changed)
        splitter.addWidget(self.pending_list)

        # Bottom section: Preview pane
        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(0, 8, 0, 0)
        preview_layout.setSpacing(8)

        preview_label = QLabel("Preview:")
        preview_label.setStyleSheet("font-weight: 600; color: #cdd6f4;")
        preview_layout.addWidget(preview_label)

        self.preview = QWebEngineView()
        self.preview.setContextMenuPolicy(Qt.NoContextMenu)  # Disable browser context menu
        self.preview.setMinimumHeight(400)  # Increased for better board visibility
        self.preview.setHtml(self._get_empty_preview_html())
        preview_layout.addWidget(self.preview, stretch=1)  # Allow preview to expand

        splitter.addWidget(preview_container)

        # Set initial splitter ratio (25% pending list, 75% preview)
        splitter.setStretchFactor(0, 25)
        splitter.setStretchFactor(1, 75)

        layout.addWidget(splitter, stretch=1)

        return panel

    def _setup_connections(self):
        """Setup signal connections."""
        pass

    @Slot()
    def _on_add_clicked(self):
        """Handle Add to List button click."""
        text = self.input_widget.get_text()
        result = self.input_widget.get_last_result()

        if not text.strip():
            QMessageBox.warning(
                self,
                "No Input",
                "Please paste some text first"
            )
            return

        if not result or result.format == InputFormat.UNKNOWN:
            QMessageBox.warning(
                self,
                "Invalid Format",
                "Could not detect valid position format.\n\n"
                "Please paste XGID/GNUID or full XG analysis text."
            )
            return

        # Check for GnuBG requirement
        if result.format == InputFormat.POSITION_IDS and not self.settings.is_gnubg_available():
            reply = QMessageBox.question(
                self,
                "GnuBG Required",
                "Position IDs require GnuBG analysis, but GnuBG is not configured.\n\n"
                "Would you like to configure GnuBG in Settings?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                # TODO: Open settings dialog
                pass
            return

        # Parse the input
        try:
            decisions = self._parse_input(text, result.format)

            if not decisions:
                QMessageBox.warning(
                    self,
                    "Parse Failed",
                    "Could not parse any valid positions from input."
                )
                return

            # Add to pending list
            for decision in decisions:
                needs_analysis = (result.format == InputFormat.POSITION_IDS)
                self.pending_decisions.append(decision)

                item = PendingPositionItem(decision, needs_analysis)
                self.pending_list.addItem(item)

            # Update count
            self._update_count_label()

            # Clear input
            self.input_widget.clear_text()

            # Select first new item
            if decisions:
                self.pending_list.setCurrentRow(len(self.pending_decisions) - len(decisions))

        except Exception as e:
            QMessageBox.critical(
                self,
                "Parse Error",
                f"Failed to parse input:\n{str(e)}"
            )

    def _parse_input(self, text: str, format_type: InputFormat) -> List[Decision]:
        """Parse input text into Decision objects."""
        if format_type == InputFormat.FULL_ANALYSIS or format_type == InputFormat.POSITION_IDS:
            # Use XGTextParser for full analysis
            decisions = XGTextParser.parse_string(text)

            # For position IDs, decisions will have empty candidate_moves
            # We'll mark them for GnuBG analysis later
            return decisions

        return []

    @Slot()
    def _on_clear_all_clicked(self):
        """Handle Clear All button click."""
        if not self.pending_decisions:
            return

        reply = QMessageBox.question(
            self,
            "Clear All",
            f"Remove all {len(self.pending_decisions)} pending position(s)?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.pending_decisions.clear()
            self.pending_list.clear()
            self._update_count_label()
            self.preview.setHtml(self._get_empty_preview_html())

    @Slot(QListWidgetItem, QListWidgetItem)
    def _on_selection_changed(self, current, previous):
        """Handle selection change in pending list."""
        if not current:
            self.preview.setHtml(self._get_empty_preview_html())
            return

        if isinstance(current, PendingPositionItem):
            self._show_preview(current.decision)

    def _show_preview(self, decision: Decision):
        """Show preview of a decision."""
        svg = self.renderer.render_svg(
            decision.position,
            dice=decision.dice,
            on_roll=decision.on_roll,
            cube_value=decision.cube_value,
            cube_owner=decision.cube_owner
        )

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    margin: 0;
                    padding: 10px;
                    background: #1e1e2e;
                    display: flex;
                    justify-content: center;
                }}
                svg {{
                    max-width: 100%;
                    height: auto;
                }}
            </style>
        </head>
        <body>
            {svg}
        </body>
        </html>
        """

        self.preview.setHtml(html)

    def _update_count_label(self):
        """Update the pending count label."""
        count = len(self.pending_decisions)
        self.count_label.setText(f"{count} position{'s' if count != 1 else ''}")

    def _get_empty_preview_html(self) -> str:
        """Get HTML for empty preview state."""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {
                    margin: 0;
                    padding: 20px;
                    background: #1e1e2e;
                    color: #6c7086;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    text-align: center;
                }
            </style>
        </head>
        <body>
            <p>Select a position to preview</p>
        </body>
        </html>
        """

    def accept(self):
        """Handle dialog acceptance."""
        if self.pending_decisions:
            self.positions_added.emit(self.pending_decisions)
        super().accept()

    def get_pending_decisions(self) -> List[Decision]:
        """Get list of pending decisions."""
        return self.pending_decisions
