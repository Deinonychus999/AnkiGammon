"""Waits while the browser trainer picks up a study pack from this computer."""

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ankigammon.trainer_handoff import TIMEOUT_SECONDS, PackHandoff

PRIMARY_STYLE = """
    QPushButton {
        background-color: #89b4fa;
        color: #1e1e2e;
        border: none;
        padding: 8px 16px;
        border-radius: 4px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #74c7ec;
    }
"""

SECONDARY_STYLE = """
    QPushButton {
        background-color: #313244;
        color: #cdd6f4;
        border: none;
        padding: 8px 16px;
        border-radius: 4px;
    }
    QPushButton:hover {
        background-color: #45475a;
    }
"""


class TrainerHandoffDialog(QDialog):
    """Opens the trainer and closes once it has fetched the pack.

    `outcome` is "sent", "save_file" or "cancelled" after exec().
    """

    _fetched = Signal()
    _timed_out = Signal()

    def __init__(self, parent, pack: dict, count: int, timeout: float = TIMEOUT_SECONDS):
        super().__init__(parent)
        self.outcome = "cancelled"
        self.setWindowTitle("Study in Trainer")
        self.setMinimumWidth(440)
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e2e;
                color: #cdd6f4;
            }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(16)
        layout.setContentsMargins(24, 20, 24, 20)

        self._message = QLabel(
            f"Opening the trainer in your browser to import {count} "
            f"position{'s' if count != 1 else ''}…\n\n"
            "If the browser asks to reach devices on your local network, allow it."
        )
        self._message.setWordWrap(True)
        self._message.setStyleSheet("color: #cdd6f4;")
        layout.addWidget(self._message)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self._save_btn = QPushButton("Save File Instead")
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.setStyleSheet(SECONDARY_STYLE)
        self._save_btn.clicked.connect(self._save_file)
        buttons.addWidget(self._save_btn)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setCursor(Qt.PointingHandCursor)
        self._cancel_btn.setStyleSheet(SECONDARY_STYLE)
        self._cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(self._cancel_btn)
        layout.addLayout(buttons)
        self.setLayout(layout)

        # The server calls back on its own thread; signals bring that to the GUI thread.
        self._fetched.connect(self._on_fetched)
        self._timed_out.connect(self._on_timed_out)
        self.handoff = PackHandoff(pack, on_fetched=self._fetched.emit,
                                   on_timeout=self._timed_out.emit, timeout=timeout)
        self.handoff.start()
        QDesktopServices.openUrl(QUrl(self.handoff.url()))

    def _on_fetched(self) -> None:
        self.outcome = "sent"
        self.accept()

    def _on_timed_out(self) -> None:
        self._message.setText(
            "The trainer didn't pick up the positions.\n\n"
            "Safari can't reach this computer from a website, and other browsers "
            "need the local network permission. Save the positions as a file and "
            "open it in the trainer instead."
        )
        self._cancel_btn.setText("Close")
        self._save_btn.setStyleSheet(PRIMARY_STYLE)
        self._save_btn.setDefault(True)

    def _save_file(self) -> None:
        self.outcome = "save_file"
        self.accept()

    def done(self, result: int) -> None:
        self.handoff.close()
        super().done(result)
