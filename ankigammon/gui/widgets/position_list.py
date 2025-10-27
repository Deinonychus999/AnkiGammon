"""
Widget for displaying list of parsed positions.
"""

from typing import List, Optional
from PySide6.QtWidgets import (
    QListWidget, QListWidgetItem, QWidget, QVBoxLayout, QLabel, QMenu, QMessageBox,
    QInputDialog
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QIcon, QAction, QKeyEvent
import qtawesome as qta

from ankigammon.models import Decision, DecisionType, Player


class PositionListItem(QListWidgetItem):
    """Custom list item for a decision/position."""

    def __init__(self, decision: Decision, index: int):
        super().__init__()
        self.decision = decision
        self.index = index

        # Set display text
        self.setText(f"#{index + 1}: {decision.get_short_display_text()}")

        # Set tooltip with metadata and note (if present)
        tooltip = decision.get_metadata_text()
        if decision.note:
            tooltip += f"\n\nNote: {decision.note}"
        self.setToolTip(tooltip)


class PositionListWidget(QListWidget):
    """
    List widget for displaying parsed positions.

    Signals:
        position_selected(Decision): Emitted when user selects a position
        position_deleted(int): Emitted when user deletes a position
    """

    position_selected = Signal(Decision)
    position_deleted = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.decisions: List[Decision] = []

        # Enable smooth scrolling
        self.setVerticalScrollMode(QListWidget.ScrollPerPixel)

        # Enable context menu for delete
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Connect selection signal
        self.currentItemChanged.connect(self._on_selection_changed)

    def set_decisions(self, decisions: List[Decision]):
        """Load decisions into the list."""
        self.clear()
        self.decisions = decisions

        for i, decision in enumerate(decisions):
            item = PositionListItem(decision, i)
            self.addItem(item)

        # Select first item
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
        item = self.itemAt(pos)
        if not item or not isinstance(item, PositionListItem):
            return

        # Create context menu
        menu = QMenu(self)
        # Set cursor pointer for the menu
        menu.setCursor(Qt.PointingHandCursor)

        # Edit Note action with icon
        edit_note_action = QAction(
            qta.icon('fa6s.note-sticky', color='#f9e2af'),  # Yellow note icon
            "Edit Note...",
            self
        )
        edit_note_action.triggered.connect(lambda: self._edit_note(item))
        menu.addAction(edit_note_action)

        menu.addSeparator()

        # Delete action with icon
        delete_action = QAction(
            qta.icon('fa6s.trash', color='#f38ba8'),  # Red delete icon
            "Delete",
            self
        )
        delete_action.triggered.connect(lambda: self._delete_item(item))
        menu.addAction(delete_action)

        # Show menu at cursor position
        menu.exec(self.mapToGlobal(pos))

    def _edit_note(self, item: PositionListItem):
        """Edit the note for a position."""
        current_note = item.decision.note or ""

        # Create input dialog
        dialog = QInputDialog(self)
        dialog.setWindowTitle("Edit Note")
        dialog.setLabelText(f"Note for position #{item.index + 1}:")
        dialog.setTextValue(current_note)
        dialog.setOption(QInputDialog.UsePlainTextEditForTextInput, True)

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
        new_note = dialog.textValue()

        if ok:
            # Update the decision's note
            item.decision.note = new_note.strip() if new_note.strip() else None

            # Update tooltip to reflect the new note
            tooltip = item.decision.get_metadata_text()
            if item.decision.note:
                tooltip += f"\n\nNote: {item.decision.note}"
            item.setToolTip(tooltip)

    def _delete_item(self, item: PositionListItem):
        """Delete an item from the list with confirmation."""
        reply = QMessageBox.question(
            self,
            "Delete Position",
            f"Delete position #{item.index + 1}?\n\n{item.decision.get_short_display_text()}",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            row = self.row(item)
            self.takeItem(row)
            # Emit signal with the index to delete from parent's decision list
            self.position_deleted.emit(item.index)

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard events for deletion."""
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            item = self.currentItem()
            if item and isinstance(item, PositionListItem):
                self._delete_item(item)
        else:
            super().keyPressEvent(event)

    def get_selected_decision(self) -> Optional[Decision]:
        """Get currently selected decision."""
        item = self.currentItem()
        if isinstance(item, PositionListItem):
            return item.decision
        return None
