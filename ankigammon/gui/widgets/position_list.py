"""
Widget for displaying list of parsed positions.
"""

from typing import List, Optional
from PySide6.QtWidgets import (
    QListWidget, QListWidgetItem, QWidget, QVBoxLayout, QLabel, QMenu, QMessageBox,
    QDialog, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QIcon, QAction, QKeyEvent
import qtawesome as qta

from ankigammon.models import Decision, DecisionType, Player
from ankigammon.gui.dialogs.note_dialog import NoteEditDialog


class PositionListItem(QListWidgetItem):
    """Custom list item for a decision/position."""

    def __init__(self, decision: Decision, index: int):
        super().__init__()
        self.decision = decision
        self.index = index

        self.setText(f"#{index + 1}: {decision.get_short_display_text()}")

        tooltip = decision.get_metadata_text()
        if decision.note:
            tooltip += f"\n\nNote: {decision.note}"
        self.setToolTip(tooltip)


class PositionListWidget(QListWidget):
    """
    List widget for displaying parsed positions.

    Signals:
        position_selected(Decision): Emitted when user selects a position
        positions_deleted(list): Emitted when user deletes position(s) - List[int] of indices
    """

    position_selected = Signal(Decision)
    positions_deleted = Signal(list)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.decisions: List[Decision] = []

        self.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.currentItemChanged.connect(self._on_selection_changed)

    def set_decisions(self, decisions: List[Decision]):
        """Load decisions into the list."""
        self.clear()
        self.decisions = decisions

        for i, decision in enumerate(decisions):
            item = PositionListItem(decision, i)
            self.addItem(item)

        if decisions:
            self.setCurrentRow(0)

    @Slot(QListWidgetItem, QListWidgetItem)
    def _on_selection_changed(self, current, previous):
        """Handle selection change."""
        if current and isinstance(current, PositionListItem):
            self.position_selected.emit(current.decision)

    @Slot()
    def _show_context_menu(self, pos):
        """Show context menu for delete action."""
        selected_items = self.selectedItems()

        if not selected_items:
            return

        menu = QMenu(self)
        menu.setCursor(Qt.PointingHandCursor)

        if len(selected_items) == 1:
            item = selected_items[0]
            edit_note_action = QAction(
                qta.icon('fa6s.note-sticky', color='#f9e2af'),
                "Edit Note...",
                self
            )
            edit_note_action.triggered.connect(lambda: self._edit_note(item))
            menu.addAction(edit_note_action)

            menu.addSeparator()

        delete_text = "Delete" if len(selected_items) == 1 else f"Delete {len(selected_items)} Items"
        delete_action = QAction(
            qta.icon('fa6s.trash', color='#f38ba8'),
            delete_text,
            self
        )
        delete_action.triggered.connect(self._delete_selected_items)
        menu.addAction(delete_action)

        menu.exec(self.mapToGlobal(pos))

    def _edit_note(self, item: PositionListItem):
        """Edit the note for a position."""
        current_note = item.decision.note or ""

        dialog = NoteEditDialog(current_note, f"Note for position #{item.index + 1}:", self)

        if dialog.exec() == QDialog.Accepted:
            new_note = dialog.get_text()

            item.decision.note = new_note.strip() if new_note.strip() else None

            tooltip = item.decision.get_metadata_text()
            if item.decision.note:
                tooltip += f"\n\nNote: {item.decision.note}"
            item.setToolTip(tooltip)

    def _delete_selected_items(self):
        """Delete selected items with confirmation."""
        selected_items = self.selectedItems()

        if not selected_items:
            return

        if len(selected_items) == 1:
            item = selected_items[0]
            message = f"Delete position #{item.index + 1}?\n\n{item.decision.get_short_display_text()}"
            title = "Delete Position"
        else:
            message = f"Delete {len(selected_items)} selected position(s)?"
            title = "Delete Positions"

        reply = QMessageBox.question(
            self,
            title,
            message,
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            indices_to_delete = sorted([item.index for item in selected_items], reverse=True)
            rows_to_delete = sorted([self.row(item) for item in selected_items], reverse=True)
            for row in rows_to_delete:
                self.takeItem(row)

            self.positions_deleted.emit(indices_to_delete)

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard shortcuts for deletion."""
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self._delete_selected_items()
        else:
            super().keyPressEvent(event)

    def get_selected_decision(self) -> Optional[Decision]:
        """Get currently selected decision."""
        item = self.currentItem()
        if isinstance(item, PositionListItem):
            return item.decision
        return None
