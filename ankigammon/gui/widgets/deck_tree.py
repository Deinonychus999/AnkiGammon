"""Tree widget for organizing positions into decks with drag-and-drop support."""

from typing import List, Optional

from PySide6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QWidget, QMenu, QAbstractItemView,
    QDialog, QMessageBox, QInputDialog
)
from PySide6.QtCore import Qt, Signal, Slot, QMimeData, QPoint
from PySide6.QtGui import QAction, QKeyEvent, QFont, QColor, QBrush
import qtawesome as qta

from ankigammon.models import Decision
from ankigammon.settings import Settings
from ankigammon.gui.deck_manager import DeckManager
from ankigammon.gui.dialogs.note_dialog import NoteEditDialog
from ankigammon.gui import silent_messagebox

MIME_TYPE = "application/x-ankigammon-positions"


class DeckTreeItem(QTreeWidgetItem):
    """Tree item representing a deck (may be nested under a parent deck)."""

    ITEM_TYPE = QTreeWidgetItem.UserType + 1

    def __init__(self, deck_name: str, count: int, is_virtual: bool = False):
        super().__init__(None, self.ITEM_TYPE)
        self.deck_name = deck_name
        self.is_virtual = is_virtual

        self._update_display(count)

        # All deck items accept drops (auto-creates the deck if virtual)
        self.setFlags(
            Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDropEnabled
        )

    def _update_display(self, count: int) -> None:
        """Update the display text with deck name and count."""
        # Show short name (last segment after ::) for subdecks
        display_name = self.deck_name.split("::")[-1].strip()
        self.setText(0, f"{display_name}  ({count})")
        self.setToolTip(0, self.deck_name)

        # Bold font for deck headers to distinguish from position items
        font = QFont()
        font.setBold(True)
        self.setFont(0, font)

        # Folder icon
        if count > 0:
            self.setIcon(0, qta.icon('fa6s.folder-open', color='#f9e2af'))
        else:
            self.setIcon(0, qta.icon('fa6s.folder', color='#7f849c'))


class PositionTreeItem(QTreeWidgetItem):
    """Child tree item representing a position within a deck."""

    ITEM_TYPE = QTreeWidgetItem.UserType + 2

    def __init__(self, decision: Decision, index: int, score_format: str = "absolute"):
        super().__init__(None, self.ITEM_TYPE)
        self.decision = decision
        self.index = index
        self.score_format = score_format

        self.setText(0, f"#{index + 1}: {decision.get_short_display_text(score_format)}")

        tooltip = decision.get_metadata_text(score_format)
        if decision.note:
            tooltip += f"\n\nNote: {decision.note}"
        self.setToolTip(0, tooltip)

        # Position items are draggable but do NOT accept drops
        self.setFlags(
            Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled
        )


class DeckTreeWidget(QTreeWidget):
    """Tree widget showing decks with positions as children.

    Supports drag-and-drop of positions between decks, context menus
    for deck/position management, and inline deck renaming.

    Signals:
        position_selected(Decision): Emitted when user selects a position
        positions_changed(): Emitted when positions are added/removed/moved
        deck_structure_changed(): Emitted when decks are created/renamed/deleted
        sync_from_anki_requested(): Emitted when user requests deck sync from Anki
    """

    position_selected = Signal(Decision)
    positions_changed = Signal()
    deck_structure_changed = Signal()
    sync_from_anki_requested = Signal()

    def __init__(self, deck_manager: DeckManager, settings: Settings, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.deck_manager = deck_manager
        self.settings = settings
        self._drop_target_item: Optional[DeckTreeItem] = None

        # Single column tree
        self.setHeaderHidden(True)
        self.setColumnCount(1)
        self.setIndentation(20)

        # Override palette highlight to prevent Windows system blue bleeding
        # into the branch/gutter area (QSS ::branch rules don't fully override
        # palette-based branch painting on Windows)
        pal = self.palette()
        pal.setColor(pal.ColorRole.Highlight, QColor(0, 0, 0, 0))
        self.setPalette(pal)

        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAnimated(True)
        self.setExpandsOnDoubleClick(False)  # We handle double-click for rename

        # Drag & Drop configuration
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)

        # Context menu
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Selection handling
        self.currentItemChanged.connect(self._on_selection_changed)

        # Double-click to rename decks
        self.itemDoubleClicked.connect(self._on_item_double_clicked)

        # Build initial tree
        self.rebuild_tree()

    def rebuild_tree(self) -> None:
        """Rebuild the entire tree from DeckManager state.

        Builds hierarchical tree structure from ::-separated deck names.
        Preserves expansion state and tries to re-select the previously selected item.
        """
        # Remember state before rebuild
        expanded_decks: set = set()
        self._collect_expanded_state(expanded_decks)

        selected_decision = None
        selected_deck = None
        current = self.currentItem()
        if isinstance(current, PositionTreeItem):
            selected_decision = current.decision
            parent = current.parent()
            if isinstance(parent, DeckTreeItem):
                selected_deck = parent.deck_name
        elif isinstance(current, DeckTreeItem):
            selected_deck = current.deck_name

        # Clear and rebuild
        self.clear()

        score_format = self.settings.score_format
        item_to_select = None

        # Map of full deck path -> tree item (for nesting)
        node_map: dict = {}

        # Sort deck names so parents (fewer :: separators) come before children
        deck_names = sorted(
            self.deck_manager.get_deck_names(),
            key=lambda n: n.count("::")
        )

        for deck_name in deck_names:
            decisions = self.deck_manager.get_deck_decisions(deck_name)
            deck_item = DeckTreeItem(deck_name, len(decisions))

            # Determine where to add this item in the hierarchy
            if "::" in deck_name:
                parent_path = deck_name.rsplit("::", 1)[0]
                parent_item = node_map.get(parent_path)

                if parent_item is None:
                    # Parent doesn't exist as a real deck — create virtual chain
                    parent_item = self._ensure_parent_chain(parent_path, node_map)

                parent_item.addChild(deck_item)
            else:
                self.addTopLevelItem(deck_item)

            node_map[deck_name] = deck_item

            # Add position children
            for i, decision in enumerate(decisions):
                pos_item = PositionTreeItem(decision, i, score_format)
                deck_item.addChild(pos_item)

                # Try to re-select the same decision
                if (selected_decision is not None
                        and decision is selected_decision
                        and deck_name == selected_deck):
                    item_to_select = pos_item

            # Restore expansion state.
            # Expand if: previously expanded, has positions, or has child subdecks.
            has_subdecks = any(
                dn != deck_name and dn.startswith(deck_name + "::")
                for dn in deck_names
            )
            if deck_name in expanded_decks or decisions or has_subdecks:
                deck_item.setExpanded(True)
            else:
                deck_item.setExpanded(False)

            # If we had a deck selected, re-select it
            if selected_deck == deck_name and item_to_select is None and selected_decision is None:
                item_to_select = deck_item

        # Update parent deck icons based on recursive position counts
        self._update_parent_icons()

        # Restore selection
        if item_to_select:
            self.setCurrentItem(item_to_select)
        elif self.topLevelItemCount() > 0:
            first_deck = self.topLevelItem(0)
            if first_deck.childCount() > 0:
                first_child = first_deck.child(0)
                if isinstance(first_child, PositionTreeItem):
                    self.setCurrentItem(first_child)
                else:
                    self.setCurrentItem(first_deck)
            else:
                self.setCurrentItem(first_deck)

    def _collect_expanded_state(self, expanded_decks: set) -> None:
        """Recursively collect expanded deck names from the tree."""
        def _walk(item):
            if isinstance(item, DeckTreeItem):
                if item.isExpanded():
                    expanded_decks.add(item.deck_name)
                for j in range(item.childCount()):
                    child = item.child(j)
                    if isinstance(child, DeckTreeItem):
                        _walk(child)

        for i in range(self.topLevelItemCount()):
            _walk(self.topLevelItem(i))

    def _update_parent_icons(self) -> None:
        """Update deck icons and counts so parents reflect all descendant positions.

        A parent deck shows the total count across itself and all subdecks,
        and the 'has content' icon if any descendant contains positions.
        """
        def _count_positions_recursive(item: QTreeWidgetItem) -> int:
            """Count all PositionTreeItem descendants (direct + nested subdecks)."""
            total = 0
            for i in range(item.childCount()):
                child = item.child(i)
                if isinstance(child, PositionTreeItem):
                    total += 1
                elif isinstance(child, DeckTreeItem):
                    total += _count_positions_recursive(child)
            return total

        def _update(item: QTreeWidgetItem) -> None:
            if isinstance(item, DeckTreeItem):
                # Recurse into children first (bottom-up)
                for i in range(item.childCount()):
                    _update(item.child(i))
                # Update display with recursive count
                total = _count_positions_recursive(item)
                item._update_display(total)

        for i in range(self.topLevelItemCount()):
            _update(self.topLevelItem(i))

    def _expand_and_select_deck(self, deck_name: str) -> None:
        """Find a deck item by name, expand its ancestors, and select it."""
        def _walk(item: QTreeWidgetItem) -> Optional[DeckTreeItem]:
            if isinstance(item, DeckTreeItem) and item.deck_name == deck_name:
                return item
            for i in range(item.childCount()):
                found = _walk(item.child(i))
                if found:
                    return found
            return None

        for i in range(self.topLevelItemCount()):
            found = _walk(self.topLevelItem(i))
            if found:
                # Expand all ancestors so the item is visible
                parent = found.parent()
                while parent:
                    parent.setExpanded(True)
                    parent = parent.parent()
                self.setCurrentItem(found)
                self.scrollToItem(found)
                return

    def _ensure_parent_chain(self, path: str, node_map: dict) -> 'DeckTreeItem':
        """Ensure all ancestor nodes exist, creating virtual ones as needed.

        Returns the DeckTreeItem for the given path.
        """
        if path in node_map:
            return node_map[path]

        parts = path.split("::")
        current_path = ""
        parent_item = None

        for part in parts:
            current_path = f"{current_path}::{part}" if current_path else part

            if current_path in node_map:
                parent_item = node_map[current_path]
                continue

            # Create virtual parent node (not a real deck in DeckManager)
            virtual_item = DeckTreeItem(current_path, 0, is_virtual=True)
            virtual_item.setExpanded(True)

            if parent_item is not None:
                parent_item.addChild(virtual_item)
            else:
                self.addTopLevelItem(virtual_item)

            node_map[current_path] = virtual_item
            parent_item = virtual_item

        return parent_item

    def get_selected_decision(self) -> Optional[Decision]:
        """Get currently selected decision, or None if a deck is selected."""
        item = self.currentItem()
        if isinstance(item, PositionTreeItem):
            return item.decision
        return None

    def get_active_deck_name(self) -> str:
        """Get the deck name of the currently selected item.

        If a position is selected, returns its parent deck.
        If a real deck is selected, returns that deck.
        Virtual deck nodes (hierarchy-only) fall back to the default deck.
        """
        item = self.currentItem()
        if isinstance(item, PositionTreeItem):
            parent = item.parent()
            if isinstance(parent, DeckTreeItem) and not parent.is_virtual:
                return parent.deck_name
        elif isinstance(item, DeckTreeItem) and not item.is_virtual:
            return item.deck_name
        return self.deck_manager.default_deck_name

    # -- Selection handling --

    @Slot(QTreeWidgetItem, QTreeWidgetItem)
    def _on_selection_changed(self, current, previous):
        """Handle selection change — emit position_selected for position items."""
        if isinstance(current, PositionTreeItem):
            self.position_selected.emit(current.decision)

    @Slot(QTreeWidgetItem, int)
    def _on_item_double_clicked(self, item, column):
        """Handle double-click: rename for deck items."""
        if isinstance(item, DeckTreeItem):
            self._rename_deck_dialog(item)

    # -- Drag & Drop --

    def mimeData(self, items: list) -> QMimeData:
        """Provide MIME data for dragged position items."""
        data = QMimeData()
        # We just set our custom type as a marker; actual data is
        # retrieved from selectedItems() in dropEvent
        data.setData(MIME_TYPE, b"positions")
        return data

    def mimeTypes(self) -> list:
        return [MIME_TYPE]

    def dragMoveEvent(self, event) -> None:
        """Highlight valid drop targets during drag."""
        item = self.itemAt(event.position().toPoint())

        # Resolve to deck item
        target_deck = None
        if isinstance(item, DeckTreeItem):
            target_deck = item
        elif isinstance(item, PositionTreeItem):
            parent = item.parent()
            if isinstance(parent, DeckTreeItem):
                target_deck = parent

        # Clear previous highlight
        if self._drop_target_item and self._drop_target_item is not target_deck:
            self._drop_target_item.setBackground(0, QBrush())
            self._drop_target_item = None

        if target_deck:
            # Check that we're not dropping onto the same deck
            source_decks = set()
            for sel in self.selectedItems():
                if isinstance(sel, PositionTreeItem):
                    parent = sel.parent()
                    if isinstance(parent, DeckTreeItem):
                        source_decks.add(parent.deck_name)

            if len(source_decks) == 1 and target_deck.deck_name in source_decks:
                # Dropping back to same deck — don't highlight
                event.ignore()
                return

            # Highlight target deck
            target_deck.setBackground(0, QBrush(QColor(137, 180, 250, 38)))
            self._drop_target_item = target_deck
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        """Handle drop: move positions to target deck."""
        # Use the validated target from dragMoveEvent — re-querying itemAt()
        # can return a different item if Qt's drag machinery shifted the layout
        target_deck_item = self._drop_target_item

        # Clear highlight
        if self._drop_target_item:
            self._drop_target_item.setBackground(0, QBrush())
            self._drop_target_item = None

        if not event.mimeData().hasFormat(MIME_TYPE):
            event.ignore()
            return

        # Resolve target deck from the stored drop target
        target_deck_name = None
        if isinstance(target_deck_item, DeckTreeItem):
            target_deck_name = target_deck_item.deck_name

        if not target_deck_name:
            event.ignore()
            return

        # Auto-create the deck if dropping on a virtual (hierarchy-only) node
        if not self.deck_manager.has_deck(target_deck_name):
            self.deck_manager.create_deck(target_deck_name)
            self.deck_structure_changed.emit()

        # Collect selected position items
        decisions_to_move = []
        for sel in self.selectedItems():
            if isinstance(sel, PositionTreeItem):
                decisions_to_move.append(sel.decision)

        if not decisions_to_move:
            event.ignore()
            return

        # Move in DeckManager
        self.deck_manager.move_decisions(decisions_to_move, target_deck_name)

        # Use CopyAction so Qt's startDrag() doesn't call clearOrRemove()
        # after we've already rebuilt the tree (which would corrupt it)
        event.setDropAction(Qt.CopyAction)
        event.accept()
        self.rebuild_tree()
        self.positions_changed.emit()

    def dragLeaveEvent(self, event) -> None:
        """Clear drop target highlight when drag leaves the widget."""
        if self._drop_target_item:
            self._drop_target_item.setBackground(0, QBrush())
            self._drop_target_item = None
        super().dragLeaveEvent(event)

    # -- Context menus --

    @Slot()
    def _show_context_menu(self, pos: QPoint) -> None:
        """Show context menu appropriate for the clicked item."""
        item = self.itemAt(pos)
        menu = QMenu(self)
        menu.setCursor(Qt.PointingHandCursor)

        if isinstance(item, DeckTreeItem):
            self._build_deck_context_menu(menu, item)
        elif isinstance(item, PositionTreeItem):
            self._build_position_context_menu(menu)
        else:
            # Empty area
            self._build_empty_context_menu(menu)

        if menu.actions():
            menu.exec(self.mapToGlobal(pos))

    def _build_deck_context_menu(self, menu: QMenu, deck_item: DeckTreeItem) -> None:
        """Build context menu for a deck node."""
        # New Subdeck
        new_subdeck_action = QAction(
            qta.icon('fa6s.folder-plus', color='#a6e3a1'),
            "New Subdeck...",
            self
        )
        new_subdeck_action.triggered.connect(lambda: self._create_subdeck_dialog(deck_item))
        menu.addAction(new_subdeck_action)

        # Virtual nodes (hierarchy-only) don't support rename/delete
        if deck_item.is_virtual:
            return

        menu.addSeparator()

        # Rename
        rename_action = QAction(
            qta.icon('fa6s.pencil', color='#89b4fa'),
            "Rename Deck...",
            self
        )
        rename_action.triggered.connect(lambda: self._rename_deck_dialog(deck_item))
        menu.addAction(rename_action)

        # Delete (only if more than one deck exists)
        if len(self.deck_manager.get_deck_names()) > 1:
            selected_decks = [
                s for s in self.selectedItems()
                if isinstance(s, DeckTreeItem) and not s.is_virtual
            ]
            deck_count = max(len(selected_decks), 1)
            delete_text = "Delete Deck..." if deck_count == 1 else f"Delete {deck_count} Decks..."
            delete_action = QAction(
                qta.icon('fa6s.trash', color='#f38ba8'),
                delete_text,
                self
            )
            delete_action.triggered.connect(self._delete_selected_decks)
            menu.addAction(delete_action)

    def _build_position_context_menu(self, menu: QMenu) -> None:
        """Build context menu for position item(s)."""
        selected_items = [s for s in self.selectedItems() if isinstance(s, PositionTreeItem)]
        if not selected_items:
            return

        # Edit Note (single selection only)
        if len(selected_items) == 1:
            edit_note_action = QAction(
                qta.icon('fa6s.note-sticky', color='#f9e2af'),
                "Edit Note...",
                self
            )
            edit_note_action.triggered.connect(lambda: self._edit_note(selected_items[0]))
            menu.addAction(edit_note_action)
            menu.addSeparator()

        # Move to Deck submenu (only if multiple decks exist)
        deck_names = self.deck_manager.get_deck_names()
        if len(deck_names) > 1:
            move_menu = QMenu("Move to Deck", self)
            move_menu.setIcon(qta.icon('fa6s.arrow-right', color='#89b4fa'))

            # Determine current deck of selected items
            current_deck = None
            if selected_items:
                parent = selected_items[0].parent()
                if isinstance(parent, DeckTreeItem):
                    current_deck = parent.deck_name

            for deck_name in deck_names:
                if deck_name == current_deck:
                    continue
                display_name = deck_name.split("::")[-1].strip()
                action = QAction(
                    qta.icon('fa6s.folder', color='#7f849c'),
                    display_name,
                    self
                )
                action.setToolTip(deck_name)
                action.triggered.connect(
                    lambda checked=False, dn=deck_name: self._move_selected_to_deck(dn)
                )
                move_menu.addAction(action)

            menu.addMenu(move_menu)
            menu.addSeparator()

        # Delete
        delete_text = "Delete" if len(selected_items) == 1 else f"Delete {len(selected_items)} Items"
        delete_action = QAction(
            qta.icon('fa6s.trash', color='#f38ba8'),
            delete_text,
            self
        )
        delete_action.triggered.connect(self._delete_selected_positions)
        menu.addAction(delete_action)

    def _build_empty_context_menu(self, menu: QMenu) -> None:
        """Build context menu for empty area."""
        new_deck_action = QAction(
            qta.icon('fa6s.folder-plus', color='#a6e3a1'),
            "New Deck...",
            self
        )
        new_deck_action.triggered.connect(self.create_new_deck_dialog)
        menu.addAction(new_deck_action)

        menu.addSeparator()

        sync_action = QAction(
            qta.icon('fa6s.rotate', color='#89b4fa'),
            "Sync Decks from Anki",
            self
        )
        sync_action.triggered.connect(self.sync_from_anki_requested.emit)
        menu.addAction(sync_action)

    # -- Deck operations --

    def create_new_deck_dialog(self) -> None:
        """Show dialog to create a new deck."""
        name, ok = QInputDialog.getText(
            self, "New Deck", "Deck name:",
            text=""
        )
        if ok and name and name.strip():
            if self.deck_manager.create_deck(name.strip()):
                self.rebuild_tree()
                self.deck_structure_changed.emit()
            else:
                silent_messagebox.warning(
                    self, "Deck Exists",
                    f"A deck named \"{name.strip()}\" already exists."
                )

    def _create_subdeck_dialog(self, parent_item: DeckTreeItem) -> None:
        """Show dialog to create a subdeck."""
        name, ok = QInputDialog.getText(
            self, "New Subdeck",
            f"Subdeck name (under {parent_item.deck_name}):",
            text=""
        )
        if ok and name and name.strip():
            full_name = self.deck_manager.create_subdeck(parent_item.deck_name, name.strip())
            if full_name:
                self.rebuild_tree()
                self._expand_and_select_deck(full_name)
                self.deck_structure_changed.emit()
            else:
                silent_messagebox.warning(
                    self, "Subdeck Exists",
                    f"A deck named \"{parent_item.deck_name}::{name.strip()}\" already exists."
                )

    def _rename_deck_dialog(self, deck_item: DeckTreeItem) -> None:
        """Show dialog to rename a deck."""
        old_name = deck_item.deck_name
        # For subdecks, suggest editing just the last segment
        if "::" in old_name:
            prefix = old_name.rsplit("::", 1)[0]
            current_short = old_name.rsplit("::", 1)[1]
            new_short, ok = QInputDialog.getText(
                self, "Rename Deck",
                f"Rename subdeck (under {prefix}):",
                text=current_short
            )
            if ok and new_short and new_short.strip():
                new_name = f"{prefix}::{new_short.strip()}"
                if self.deck_manager.rename_deck(old_name, new_name):
                    self.rebuild_tree()
                    self.deck_structure_changed.emit()
                else:
                    silent_messagebox.warning(
                        self, "Rename Failed",
                        f"A deck named \"{new_name}\" already exists."
                    )
        else:
            new_name, ok = QInputDialog.getText(
                self, "Rename Deck", "New deck name:",
                text=old_name
            )
            if ok and new_name and new_name.strip():
                if self.deck_manager.rename_deck(old_name, new_name.strip()):
                    self.rebuild_tree()
                    self.deck_structure_changed.emit()
                else:
                    silent_messagebox.warning(
                        self, "Rename Failed",
                        f"A deck named \"{new_name.strip()}\" already exists."
                    )

    def _delete_deck_dialog(self, deck_item: DeckTreeItem) -> None:
        """Show dialog to delete a deck, optionally moving its positions."""
        deck_name = deck_item.deck_name
        decisions = self.deck_manager.get_deck_decisions(deck_name)
        other_decks = [n for n in self.deck_manager.get_deck_names() if n != deck_name]

        if not other_decks:
            return

        if decisions:
            # Ask where to move positions (or discard them)
            DELETE_SENTINEL = "⛔ Delete positions"
            display_names = [n.split("::")[-1].strip() for n in other_decks]
            choices = display_names + [DELETE_SENTINEL]
            choice, ok = QInputDialog.getItem(
                self, "Delete Deck",
                f"Deck \"{deck_name}\" has {len(decisions)} position(s).\n"
                f"Move them to:",
                choices, 0, False
            )
            if not ok:
                return
            if choice == DELETE_SENTINEL:
                move_to = None
            else:
                move_to = other_decks[display_names.index(choice)]
        else:
            reply = silent_messagebox.question(
                self, "Delete Deck",
                f"Delete empty deck \"{deck_name}\"?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                default_button=QMessageBox.StandardButton.Yes
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            move_to = None

        if self.deck_manager.delete_deck(deck_name, move_to=move_to):
            self.rebuild_tree()
            self.positions_changed.emit()
            self.deck_structure_changed.emit()

    # -- Position operations --

    def _edit_note(self, item: PositionTreeItem) -> None:
        """Edit the note for a position."""
        current_note = item.decision.note or ""
        dialog = NoteEditDialog(current_note, f"Note for position #{item.index + 1}:", self)

        if dialog.exec() == QDialog.Accepted:
            new_note = dialog.get_text()
            item.decision.note = new_note.strip() if new_note.strip() else None

            tooltip = item.decision.get_metadata_text(self.settings.score_format)
            if item.decision.note:
                tooltip += f"\n\nNote: {item.decision.note}"
            item.setToolTip(0, tooltip)

    def _move_selected_to_deck(self, target_deck: str) -> None:
        """Move selected positions to a target deck."""
        selected = [s for s in self.selectedItems() if isinstance(s, PositionTreeItem)]
        if not selected:
            return

        decisions = [item.decision for item in selected]
        self.deck_manager.move_decisions(decisions, target_deck)
        self.rebuild_tree()
        self.positions_changed.emit()

    def _delete_selected_positions(self) -> None:
        """Delete selected position items with confirmation."""
        selected = [s for s in self.selectedItems() if isinstance(s, PositionTreeItem)]
        if not selected:
            return

        if len(selected) == 1:
            item = selected[0]
            message = (
                f"Delete position #{item.index + 1}?\n\n"
                f"{item.decision.get_short_display_text(self.settings.score_format)}"
            )
            title = "Delete Position"
        else:
            message = f"Delete {len(selected)} selected position(s)?"
            title = "Delete Positions"

        reply = silent_messagebox.question(
            self, title, message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            default_button=QMessageBox.StandardButton.Yes
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Build removal list: (deck_name, decision) pairs
            removals = []
            for item in selected:
                parent = item.parent()
                if isinstance(parent, DeckTreeItem):
                    removals.append((parent.deck_name, item.decision))

            self.deck_manager.remove_decisions_by_identity(removals)
            self.rebuild_tree()
            self.positions_changed.emit()

    # -- Keyboard shortcuts --

    def _delete_selected_decks(self) -> None:
        """Delete all selected deck items with a single confirmation."""
        selected_decks = [
            s for s in self.selectedItems()
            if isinstance(s, DeckTreeItem) and not s.is_virtual
        ]
        if not selected_decks:
            return

        all_deck_names = self.deck_manager.get_deck_names()
        names_to_delete = {item.deck_name for item in selected_decks}

        # Must keep at least one deck
        remaining = [n for n in all_deck_names if n not in names_to_delete]
        if not remaining:
            silent_messagebox.warning(
                self, "Cannot Delete",
                "Cannot delete all decks. At least one deck must remain."
            )
            return

        # Single deck selected — use the existing detailed dialog
        if len(selected_decks) == 1:
            self._delete_deck_dialog(selected_decks[0])
            return

        # Collect total positions across all decks being deleted
        total_positions = sum(
            len(self.deck_manager.get_deck_decisions(name))
            for name in names_to_delete
        )

        if total_positions > 0:
            DELETE_SENTINEL = "⛔ Delete positions"
            display_names = [n.split("::")[-1].strip() for n in remaining]
            choices = display_names + [DELETE_SENTINEL]
            choice, ok = QInputDialog.getItem(
                self, "Delete Decks",
                f"Delete {len(selected_decks)} decks with {total_positions} position(s).\n"
                f"Move positions to:",
                choices, 0, False
            )
            if not ok:
                return
            if choice == DELETE_SENTINEL:
                move_to = None
            else:
                move_to = remaining[display_names.index(choice)]
        else:
            reply = silent_messagebox.question(
                self, "Delete Decks",
                f"Delete {len(selected_decks)} empty decks?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                default_button=QMessageBox.StandardButton.Yes
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            move_to = None

        for name in names_to_delete:
            self.deck_manager.delete_deck(name, move_to=move_to)

        self.rebuild_tree()
        self.positions_changed.emit()
        self.deck_structure_changed.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle keyboard shortcuts."""
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            # Check if any selected items are positions or decks
            selected = self.selectedItems()
            has_positions = any(isinstance(s, PositionTreeItem) for s in selected)
            has_decks = any(
                isinstance(s, DeckTreeItem) and not s.is_virtual for s in selected
            )

            if has_positions:
                self._delete_selected_positions()
            if has_decks:
                self._delete_selected_decks()
        elif event.key() == Qt.Key_F2:
            current = self.currentItem()
            if isinstance(current, DeckTreeItem) and not current.is_virtual:
                self._rename_deck_dialog(current)
        else:
            super().keyPressEvent(event)
