"""
Tips and shortcuts reference dialog.
"""

import sys
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QWidget, QGridLayout
)
from PySide6.QtCore import Qt


class ShortcutsDialog(QDialog):
    """Dialog displaying tips and keyboard shortcuts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tips & Shortcuts")
        self.setMinimumSize(600, 500)
        self.setModal(False)  # Allow interaction with main window

        self._setup_ui()

    def _setup_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background-color: #181825;")

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 16, 20, 16)
        content_layout.setSpacing(12)

        # Tips section (moved to top)
        tips_title = QLabel("💡 Did you know?")
        tips_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #f5e0dc;")
        content_layout.addWidget(tips_title)

        tips = [
            "Right-click any position to edit its note or delete it",
            "Drag and drop .xg, .mat, or .sgf files anywhere to import",
            "You can select multiple positions and delete them all at once",
        ]

        for tip in tips:
            tip_card = QWidget()
            tip_card.setStyleSheet("""
                QWidget {
                    background-color: rgba(137, 180, 250, 0.08);
                    border-left: 3px solid #89b4fa;
                    border-radius: 4px;
                    padding: 10px;
                }
            """)
            tip_layout = QHBoxLayout(tip_card)
            tip_layout.setContentsMargins(10, 10, 10, 10)

            tip_label = QLabel(tip)
            tip_label.setStyleSheet("color: #cdd6f4; font-size: 13px; background: transparent; border: none;")
            tip_label.setWordWrap(True)
            tip_layout.addWidget(tip_label)

            content_layout.addWidget(tip_card)

        # Shortcuts section (moved below tips)
        content_layout.addSpacing(8)

        shortcuts_title = QLabel("⌨️ Keyboard Shortcuts")
        shortcuts_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #f5e0dc;")
        content_layout.addWidget(shortcuts_title)

        # Determine modifier key based on OS
        modifier = "Cmd" if sys.platform == "darwin" else "Ctrl"

        shortcuts = [
            (f"{modifier}+N", "Add positions"),
            (f"{modifier}+O", "Import file"),
            (f"{modifier}+E", "Export to Anki"),
            (f"{modifier}+,", "Open Settings"),
            ("Delete", "Remove selected"),
            ("Shift+Click", "Select range"),
            (f"{modifier}+Click", "Select multiple"),
        ]

        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setContentsMargins(0, 0, 0, 0)

        for i, (key, desc) in enumerate(shortcuts):
            row = i // 2
            col = i % 2

            card = self._create_shortcut_card(key, desc)
            grid.addWidget(card, row, col)

        content_layout.addLayout(grid)

        content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)

        # Footer with close button
        footer = QWidget()
        footer.setStyleSheet("background-color: #1e1e2e; padding: 16px;")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(20, 16, 20, 16)

        close_hint = QLabel("Press ESC to close")
        close_hint.setStyleSheet("color: #6c7086; font-size: 11px;")
        footer_layout.addWidget(close_hint)

        footer_layout.addStretch()

        close_btn = QPushButton("Got it")
        close_btn.setDefault(True)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #89b4fa;
                color: #1e1e2e;
                border: none;
                padding: 8px 24px;
                border-radius: 6px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #74c7ec;
            }
        """)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        footer_layout.addWidget(close_btn)

        layout.addWidget(footer)

    def _create_shortcut_card(self, key: str, description: str) -> QWidget:
        """Create a card widget for a keyboard shortcut."""
        card = QWidget()
        card.setStyleSheet("""
            QWidget {
                background-color: #262637;
                border-radius: 6px;
                padding: 10px;
            }
        """)

        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(10, 10, 10, 10)
        card_layout.setSpacing(10)

        # Key badge
        key_badge = QLabel(key)
        key_badge.setStyleSheet("""
            QLabel {
                background-color: #45475a;
                color: #f5e0dc;
                padding: 4px 10px;
                border-radius: 4px;
                font-family: 'Consolas', monospace;
                font-size: 11px;
                font-weight: bold;
                border: none;
            }
        """)
        key_badge.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(key_badge)

        # Description
        desc_label = QLabel(description)
        desc_label.setStyleSheet("""
            QLabel {
                color: #cdd6f4;
                font-size: 13px;
                background: transparent;
                border: none;
            }
        """)
        card_layout.addWidget(desc_label, stretch=1)

        return card

    def keyPressEvent(self, event):
        """Close on ESC key."""
        if event.key() == Qt.Key_Escape:
            self.accept()
        else:
            super().keyPressEvent(event)
