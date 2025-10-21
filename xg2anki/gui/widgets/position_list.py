"""
Widget for displaying list of parsed positions.
"""

from typing import List, Optional
from PySide6.QtWidgets import (
    QListWidget, QListWidgetItem, QWidget, QVBoxLayout, QLabel
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QIcon

from xg2anki.models import Decision, DecisionType, Player


class PositionListItem(QListWidgetItem):
    """Custom list item for a decision/position."""

    def __init__(self, decision: Decision, index: int):
        super().__init__()
        self.decision = decision
        self.index = index

        # Set display text
        decision_type = "Checker" if decision.decision_type == DecisionType.CHECKER_PLAY else "Cube"
        on_roll = "White" if decision.on_roll == Player.X else "Black"
        dice_str = f"{decision.dice[0]}{decision.dice[1]}" if decision.dice else "—"

        self.setText(f"#{index + 1}: {decision_type} | {on_roll} | {dice_str}")

        # Set tooltip with metadata
        self.setToolTip(decision.get_metadata_text())


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
        # TODO: Implement context menu in Phase 3
        pass

    def get_selected_decision(self) -> Optional[Decision]:
        """Get currently selected decision."""
        item = self.currentItem()
        if isinstance(item, PositionListItem):
            return item.decision
        return None
