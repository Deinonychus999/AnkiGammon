"""
Custom dialog for editing notes with word wrapping.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QPlainTextEdit
)
from PySide6.QtCore import Qt


class NoteEditDialog(QDialog):
    """Custom dialog for editing notes with word wrapping."""

    def __init__(self, current_note: str = "", label_text: str = "Note:", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Note")
        self.setModal(True)
        self.setMinimumSize(500, 300)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Label
        label = QLabel(label_text)
        label.setStyleSheet("color: #cdd6f4; font-weight: 600;")
        layout.addWidget(label)

        # Text edit with word wrap
        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlainText(current_note)
        self.text_edit.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.text_edit.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 2px solid #313244;
                border-radius: 6px;
                padding: 8px;
            }
            QPlainTextEdit:focus {
                border-color: #89b4fa;
            }
        """)
        layout.addWidget(self.text_edit, stretch=1)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.btn_ok = QPushButton("OK")
        self.btn_ok.setStyleSheet("""
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
        """)
        self.btn_ok.setCursor(Qt.PointingHandCursor)
        self.btn_ok.clicked.connect(self.accept)
        button_layout.addWidget(self.btn_ok)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setStyleSheet("""
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
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)
        button_layout.addWidget(self.btn_cancel)

        layout.addLayout(button_layout)

        # Focus the text edit
        self.text_edit.setFocus()

    def get_text(self) -> str:
        """Get the edited text."""
        return self.text_edit.toPlainText()
