"""
Dialog for choosing which decks of a collection to open.
"""

from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout
)

DECK_ROLE = Qt.UserRole


class CollectionOpenDialog(QDialog):
    """Deck checklist shown before a collection replaces the loaded positions.

    Every deck starts ticked. Ticking or unticking a deck does the same to
    its subdecks; each deck can still be ticked on its own afterwards.
    """

    def __init__(
        self,
        file_name: str,
        deck_counts: Dict[str, int],
        warning: Optional[str] = None,
        notes: Optional[List[str]] = None,
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("Open Collection")
        self.setModal(True)
        self.setMinimumSize(460, 420)
        self._deck_counts = deck_counts
        self._items: Dict[str, QTreeWidgetItem] = {}

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel(f"Choose the decks to open from {file_name}:")
        title.setWordWrap(True)
        title.setStyleSheet("color: #cdd6f4; font-weight: 600;")
        layout.addWidget(title)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setStyleSheet("""
            QTreeWidget {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 2px solid #313244;
                border-radius: 6px;
                padding: 4px;
            }
        """)
        self._build_tree()
        self.tree.expandAll()
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree, stretch=1)

        self.summary = QLabel()
        self.summary.setStyleSheet("color: #a6adc8;")
        layout.addWidget(self.summary)

        for text, color in [(warning, "#f9e2af")] + [(n, "#a6adc8") for n in notes or []]:
            if not text:
                continue
            label = QLabel(text)
            label.setWordWrap(True)
            label.setStyleSheet(f"color: {color};")
            layout.addWidget(label)

        button_layout = QHBoxLayout()
        btn_all = self._small_button("Select All", lambda: self._set_all(Qt.Checked))
        btn_none = self._small_button("Select None", lambda: self._set_all(Qt.Unchecked))
        button_layout.addWidget(btn_all)
        button_layout.addWidget(btn_none)
        button_layout.addStretch()

        self.btn_open = QPushButton("Open")
        self.btn_open.setStyleSheet("""
            QPushButton {
                background-color: #89b4fa;
                color: #1e1e2e;
                border: none;
                padding: 8px 24px;
                border-radius: 6px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #a0c8fc;
            }
            QPushButton:disabled {
                background-color: #45475a;
                color: #6c7086;
            }
        """)
        self.btn_open.setCursor(Qt.PointingHandCursor)
        self.btn_open.setDefault(True)
        self.btn_open.clicked.connect(self.accept)
        button_layout.addWidget(self.btn_open)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #45475a;
                color: #cdd6f4;
                border: none;
                padding: 8px 24px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #585b70;
            }
        """)
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        button_layout.addWidget(btn_cancel)

        layout.addLayout(button_layout)
        self._update_summary()

    def _small_button(self, text: str, slot) -> QPushButton:
        button = QPushButton(text)
        button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #89b4fa;
                border: none;
                padding: 6px 8px;
            }
            QPushButton:hover {
                color: #b4befe;
            }
        """)
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(slot)
        return button

    def _build_tree(self) -> None:
        # Parents that only exist as part of a subdeck's name get a row too, so
        # a whole branch can be ticked at once; they hold no positions themselves.
        for deck in sorted(self._deck_counts, key=lambda name: name.split("::")):
            parts = deck.split("::")
            for depth in range(1, len(parts) + 1):
                name = "::".join(parts[:depth])
                if name in self._items:
                    continue
                parent = self._items.get("::".join(parts[:depth - 1])) if depth > 1 else None
                item = QTreeWidgetItem(parent or self.tree)
                count = self._deck_counts.get(name)
                item.setText(0, parts[depth - 1] if count is None else f"{parts[depth - 1]}  ({count})")
                item.setData(0, DECK_ROLE, name)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(0, Qt.Checked)
                self._items[name] = item

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        self.tree.blockSignals(True)
        try:
            state = item.checkState(0)
            stack = [item.child(i) for i in range(item.childCount())]
            while stack:
                child = stack.pop()
                child.setCheckState(0, state)
                stack.extend(child.child(i) for i in range(child.childCount()))
        finally:
            self.tree.blockSignals(False)
        self._update_summary()

    def _set_all(self, state) -> None:
        self.tree.blockSignals(True)
        try:
            for item in self._items.values():
                item.setCheckState(0, state)
        finally:
            self.tree.blockSignals(False)
        self._update_summary()

    def _update_summary(self) -> None:
        selected = self.selected_decks()
        positions = sum(self._deck_counts[d] for d in selected)
        self.summary.setText(
            f"{positions} position(s) in {len(selected)} of {len(self._deck_counts)} deck(s)"
        )
        self.btn_open.setEnabled(bool(selected))

    def selected_decks(self) -> List[str]:
        return [
            name for name, item in self._items.items()
            if name in self._deck_counts and item.checkState(0) == Qt.Checked
        ]
