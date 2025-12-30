"""
Smart input dialog for adding positions via paste.

Supports:
- Position IDs (XGID/OGID/GNUID) - analyzed with GnuBG
- Full XG analysis text - parsed directly
"""

from typing import List
from pathlib import Path

import qtawesome as qta

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QFrame, QSplitter, QWidget, QProgressDialog, QMenu,
    QAbstractItemView
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QAction, QKeyEvent
from PySide6.QtWebEngineWidgets import QWebEngineView

from ankigammon.settings import Settings
from ankigammon.models import Decision, Position, Player, CubeState, DecisionType
from ankigammon.parsers.xg_text_parser import XGTextParser
from ankigammon.gui.dialogs.settings_dialog import SettingsDialog
from ankigammon.gui import silent_messagebox
from ankigammon.utils.gnuid import parse_gnuid
from ankigammon.utils.ogid import parse_ogid
from ankigammon.utils.xgid import parse_xgid
from ankigammon.renderer.svg_board_renderer import SVGBoardRenderer
from ankigammon.renderer.color_schemes import get_scheme
from ankigammon.gui.format_detector import InputFormat
from ankigammon.gui.dialogs.note_dialog import NoteEditDialog


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

        # Icon based on analysis status
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

        # Add note if present
        if self.decision.note:
            tooltip += f"\n\nNote: {self.decision.note}"

        self.setToolTip(tooltip)


class PendingListWidget(QListWidget):
    """Custom list widget for pending positions with deletion support."""

    items_deleted = Signal(list)  # Emits list of indices of deleted items

    def __init__(self, parent=None):
        super().__init__(parent)

        # Enable smooth scrolling
        self.setVerticalScrollMode(QListWidget.ScrollPerPixel)

        # Enable multi-selection with Ctrl/Shift+Click
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        # Enable context menu
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Set styling
        self.setStyleSheet("""
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

    @Slot()
    def _show_context_menu(self, pos):
        """Show context menu for edit note and delete actions."""
        # Get all selected items
        selected_items = self.selectedItems()

        if not selected_items:
            return

        # Create context menu
        menu = QMenu(self)
        menu.setCursor(Qt.PointingHandCursor)

        # Edit Note action (single selection only)
        if len(selected_items) == 1:
            item = selected_items[0]
            edit_note_action = QAction(
                qta.icon('fa6s.note-sticky', color='#f9e2af'),  # Yellow note icon
                "Edit Note...",
                self
            )
            edit_note_action.triggered.connect(lambda: self._edit_note(item))
            menu.addAction(edit_note_action)

            menu.addSeparator()

        # Delete action (supports single or multiple selections)
        delete_text = "Delete" if len(selected_items) == 1 else f"Delete {len(selected_items)} Items"
        delete_action = QAction(
            qta.icon('fa6s.trash', color='#f38ba8'),  # Red delete icon
            delete_text,
            self
        )
        delete_action.triggered.connect(self._delete_selected_items)
        menu.addAction(delete_action)

        # Show menu at cursor position
        menu.exec(self.mapToGlobal(pos))

    def _edit_note(self, item: PendingPositionItem):
        """Edit the note for a pending position."""
        current_note = item.decision.note or ""

        # Create custom note edit dialog
        dialog = NoteEditDialog(current_note, "Note for pending position:", self)

        # Show dialog and get result
        if dialog.exec() == QDialog.Accepted:
            new_note = dialog.get_text()

            # Update the decision's note
            item.decision.note = new_note.strip() if new_note.strip() else None

            # Update tooltip to reflect the new note
            tooltip = item.decision.get_short_display_text()
            if item.needs_analysis:
                tooltip += "\n\nNeeds GnuBG analysis"
            else:
                tooltip += f"\n\n{len(item.decision.candidate_moves)} moves analyzed"
            if item.decision.note:
                tooltip += f"\n\nNote: {item.decision.note}"
            item.setToolTip(tooltip)

    def _delete_selected_items(self):
        """Delete all selected items from the list with confirmation."""
        selected_items = self.selectedItems()

        if not selected_items:
            return

        # Confirm deletion
        if len(selected_items) == 1:
            item = selected_items[0]
            message = f"Delete pending position?\n\n{item.decision.get_short_display_text()}"
            title = "Delete Position"
        else:
            message = f"Delete {len(selected_items)} selected pending position(s)?"
            title = "Delete Positions"

        # Show confirmation dialog
        reply = silent_messagebox.question(
            self,
            title,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            default_button=QMessageBox.StandardButton.Yes
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Delete in descending order to avoid index shifting
            rows_to_delete = sorted([self.row(item) for item in selected_items], reverse=True)
            for row in rows_to_delete:
                self.takeItem(row)

            # Emit signal with deleted indices
            self.items_deleted.emit(rows_to_delete)

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard events for deletion."""
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self._delete_selected_items()
        else:
            super().keyPressEvent(event)


class InputDialog(QDialog):
    """
    Dialog for smart position input.

    Allows users to paste:
    - Full XG analysis text (parsed directly)
    - Position IDs (XGID/OGID/GNUID) - analyzed with GnuBG

    Signals:
        positions_added(List[Decision]): Emitted when positions are added
    """

    positions_added = Signal(list)

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.pending_decisions: List[Decision] = []
        scheme = get_scheme(settings.color_scheme)
        if settings.swap_checker_colors:
            scheme = scheme.with_swapped_checkers()
        self.renderer = SVGBoardRenderer(
            color_scheme=scheme,
            orientation=settings.board_orientation
        )

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

        # Set initial splitter ratio
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
                background-color: #a0c8fc;
            }
            QPushButton:pressed {
                background-color: #74c7ec;
            }
        """)
        self.btn_done.setCursor(Qt.PointingHandCursor)
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
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)
        button_layout.addWidget(self.btn_cancel)

        layout.addLayout(button_layout)

    def _create_input_panel(self) -> QWidget:
        """Create the input panel with smart input widget."""
        # Local import to avoid circular dependency
        from ankigammon.gui.widgets import SmartInputWidget

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
        self.btn_add.setCursor(Qt.PointingHandCursor)
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
        self.btn_clear.setCursor(Qt.PointingHandCursor)
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
        self.btn_clear_all.setCursor(Qt.PointingHandCursor)
        self.btn_clear_all.clicked.connect(self._on_clear_all_clicked)
        header_layout.addWidget(self.btn_clear_all)

        layout.addLayout(header_layout)

        # Create vertical splitter for pending list and preview
        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)

        # Pending list
        self.pending_list = PendingListWidget()
        self.pending_list.currentItemChanged.connect(self._on_selection_changed)
        self.pending_list.items_deleted.connect(self._on_items_deleted)
        splitter.addWidget(self.pending_list)

        # Preview pane
        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(0, 8, 0, 0)
        preview_layout.setSpacing(8)

        preview_label = QLabel("Preview:")
        preview_label.setStyleSheet("font-weight: 600; color: #cdd6f4;")
        preview_layout.addWidget(preview_label)

        self.preview = QWebEngineView()
        self.preview.setContextMenuPolicy(Qt.NoContextMenu)
        self.preview.setMinimumHeight(400)
        self.preview.setHtml(self._get_empty_preview_html())
        preview_layout.addWidget(self.preview, stretch=1)

        splitter.addWidget(preview_container)

        # Set splitter proportions
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
            silent_messagebox.warning(
                self,
                "No Input",
                "Please paste some text first"
            )
            return

        if not result or result.format == InputFormat.UNKNOWN:
            silent_messagebox.warning(
                self,
                "Invalid Format",
                "Could not detect valid position format.\n\n"
                "Please paste XGID/OGID/GNUID or full XG analysis text."
            )
            return

        # Check for GnuBG requirement
        if result.format == InputFormat.POSITION_IDS and not self.settings.is_gnubg_available():
            reply = silent_messagebox.question(
                self,
                "GnuBG Required",
                "Position IDs require GnuBG analysis, but GnuBG is not configured.\n\n"
                "Would you like to configure GnuBG in Settings?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                # Open settings dialog to configure GnuBG
                dialog = SettingsDialog(self.settings, self)
                dialog.exec()
            return

        # Parse input
        try:
            decisions = self._parse_input(text, result.format)

            if not decisions:
                silent_messagebox.warning(
                    self,
                    "Parse Failed",
                    "Could not parse any valid positions from input."
                )
                return

            # Add to pending list
            for decision in decisions:
                # Check if decision has analysis data
                needs_analysis = not bool(decision.candidate_moves)
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
            silent_messagebox.critical(
                self,
                "Parse Error",
                f"Failed to parse input:\n{str(e)}"
            )

    def _parse_input(self, text: str, format_type: InputFormat) -> List[Decision]:
        """Parse input text into Decision objects."""
        if format_type == InputFormat.FULL_ANALYSIS:
            # Use XGTextParser for full analysis
            decisions = XGTextParser.parse_string(text)
            return decisions

        elif format_type == InputFormat.XG_BINARY:
            # Binary format should use file import
            raise ValueError(
                "XG binary format (.xg files) must be imported via File → Import.\n"
                "Binary data cannot be pasted as text."
            )

        elif format_type == InputFormat.POSITION_IDS:
            # Try parsing as position IDs (XGID, GNUID, or OGID)
            decisions = []

            # Split by lines
            lines = [line.strip() for line in text.split('\n') if line.strip()]

            for line in lines:
                decision = self._parse_position_id(line)
                if decision:
                    decisions.append(decision)

            return decisions

        return []

    def _parse_position_id(self, position_id: str) -> Decision:
        """Parse a single position ID (XGID, GNUID, or OGID) into a Decision."""
        # Try XGID
        if 'XGID=' in position_id or ':' in position_id:
            try:
                position, metadata = parse_xgid(position_id)
                return self._create_decision_from_metadata(position, metadata)
            except:
                pass

        # Try GNUID
        if ':' in position_id:
            parts = position_id.split(':')
            if len(parts) >= 2 and len(parts[0]) == 14 and len(parts[1]) == 12:
                try:
                    position, metadata = parse_gnuid(position_id)
                    return self._create_decision_from_metadata(position, metadata, original_format="GNUID")
                except:
                    pass

        # Try OGID
        if ':' in position_id:
            try:
                position, metadata = parse_ogid(position_id)
                return self._create_decision_from_metadata(position, metadata, original_format="OGID")
            except:
                pass

        return None

    def _create_decision_from_metadata(self, position: Position, metadata: dict, original_format: str = "XGID") -> Decision:
        """Create a Decision object from position and metadata."""
        from ankigammon.utils.xgid import encode_xgid

        # Determine Crawford status (only applies to match play, not money games)
        match_length = metadata.get('match_length', 0)
        crawford = False

        if match_length > 0:
            if 'crawford' in metadata and metadata['crawford']:
                crawford = True
            elif 'crawford_jacoby' in metadata and metadata['crawford_jacoby'] > 0:
                crawford = True
            elif 'match_modifier' in metadata and metadata['match_modifier'] == 'C':
                crawford = True

        # Generate XGID for GnuBG analysis
        xgid = encode_xgid(
            position=position,
            cube_value=metadata.get('cube_value', 1),
            cube_owner=metadata.get('cube_owner', CubeState.CENTERED),
            dice=metadata.get('dice'),
            on_roll=metadata.get('on_roll', Player.X),
            score_x=metadata.get('score_x', 0),
            score_o=metadata.get('score_o', 0),
            match_length=metadata.get('match_length', 0),
            crawford_jacoby=metadata.get('crawford_jacoby', 1 if crawford else 0)
        )

        return Decision(
            position=position,
            xgid=xgid,
            on_roll=metadata.get('on_roll', Player.X),
            dice=metadata.get('dice'),
            score_x=metadata.get('score_x', 0),
            score_o=metadata.get('score_o', 0),
            match_length=metadata.get('match_length', 0),
            crawford=crawford,
            cube_value=metadata.get('cube_value', 1),
            cube_owner=metadata.get('cube_owner', CubeState.CENTERED),
            decision_type=DecisionType.CUBE_ACTION if not metadata.get('dice') else DecisionType.CHECKER_PLAY,
            candidate_moves=[],  # Will be populated by GnuBG analysis
            original_position_format=original_format
        )

    @Slot()
    def _on_clear_all_clicked(self):
        """Handle Clear All button click."""
        if not self.pending_decisions:
            return

        reply = silent_messagebox.question(
            self,
            "Clear All",
            f"Remove all {len(self.pending_decisions)} pending position(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.pending_decisions.clear()
            self.pending_list.clear()
            self._update_count_label()
            self.preview.setHtml(self._get_empty_preview_html())

    @Slot(list)
    def _on_items_deleted(self, indices: list):
        """Handle deletion of multiple pending items."""
        # Delete in descending order
        for index in sorted(indices, reverse=True):
            if 0 <= index < len(self.pending_decisions):
                self.pending_decisions.pop(index)

        # Update count label
        self._update_count_label()

        # Clear preview if no items remain or no selection
        if not self.pending_decisions:
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
            cube_owner=decision.cube_owner,
            score_x=decision.score_x,
            score_o=decision.score_o,
            match_length=decision.match_length,
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
