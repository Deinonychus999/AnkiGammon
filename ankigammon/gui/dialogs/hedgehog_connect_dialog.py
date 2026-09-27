"""Waits while the user approves AnkiGammon on hedgehog-bg.com."""

from typing import Optional

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ankigammon.gui.dialogs.trainer_handoff_dialog import PRIMARY_STYLE, SECONDARY_STYLE
from ankigammon.utils.hedgehog_client import HedgehogClient
from ankigammon.utils.hedgehog_oauth import TIMEOUT_SECONDS, HedgehogConnect


class HedgehogConnectDialog(QDialog):
    """Opens HedgeHog's approval page and closes once the account is connected.

    After exec(), `me` holds HedgeHog's /oauth/me answer when it connected.
    """

    _connected = Signal(dict)
    _failed = Signal(str)
    _timed_out = Signal()

    def __init__(self, parent, client: Optional[HedgehogClient] = None,
                 timeout: float = TIMEOUT_SECONDS):
        super().__init__(parent)
        self.me: Optional[dict] = None
        self.setWindowTitle("Connect HedgeHog")
        self.setMinimumWidth(440)
        self.setStyleSheet("QDialog { background-color: #1e1e2e; color: #cdd6f4; }")

        layout = QVBoxLayout()
        layout.setSpacing(16)
        layout.setContentsMargins(24, 20, 24, 20)

        self._message = QLabel(
            "Opening HedgeHog in your browser…\n\n"
            "Sign in there and click Allow to let AnkiGammon analyze positions "
            "with your HedgeHog account. Analyses count toward your HedgeHog plan."
        )
        self._message.setWordWrap(True)
        self._message.setStyleSheet("color: #cdd6f4;")
        layout.addWidget(self._message)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self._retry_btn = QPushButton("Try Again")
        self._retry_btn.setCursor(Qt.PointingHandCursor)
        self._retry_btn.setStyleSheet(PRIMARY_STYLE)
        self._retry_btn.clicked.connect(self._start)
        self._retry_btn.setVisible(False)
        buttons.addWidget(self._retry_btn)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setCursor(Qt.PointingHandCursor)
        self._cancel_btn.setStyleSheet(SECONDARY_STYLE)
        self._cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(self._cancel_btn)
        layout.addLayout(buttons)
        self.setLayout(layout)

        # The loopback server calls back on its own threads; signals bring that to the GUI thread.
        self._connected.connect(self._on_connected)
        self._failed.connect(self._on_failed)
        self._timed_out.connect(self._on_timed_out)
        self._client = client or HedgehogClient()
        self._timeout = timeout
        self.connect_flow: Optional[HedgehogConnect] = None
        self._start()

    def _start(self) -> None:
        if self.connect_flow is not None:
            self.connect_flow.close()
        self._retry_btn.setVisible(False)
        self.connect_flow = HedgehogConnect(
            self._client, on_done=self._connected.emit, on_error=self._failed.emit,
            on_timeout=self._timed_out.emit, timeout=self._timeout,
        )
        QDesktopServices.openUrl(QUrl(self.connect_flow.start()))

    def _on_connected(self, me: dict) -> None:
        self.me = me
        self.accept()

    def _on_failed(self, message: str) -> None:
        self._message.setText(message)
        self._retry_btn.setVisible(True)
        self._cancel_btn.setText("Close")

    def _on_timed_out(self) -> None:
        self._on_failed(
            "HedgeHog didn't send AnkiGammon an approval. If the browser shows an "
            "error on HedgeHog's page, AnkiGammon may not be approved yet."
        )

    def done(self, result: int) -> None:
        if self.connect_flow is not None:
            self.connect_flow.close()
        super().done(result)
