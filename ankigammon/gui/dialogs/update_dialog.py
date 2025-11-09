"""Dialog for displaying version update information."""

import webbrowser
from datetime import datetime, timedelta
from typing import Dict

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
)


class UpdateDialog(QDialog):
    """Dialog to notify user about available updates."""

    def __init__(self, parent, release_info: Dict, current_version: str):
        """Initialize update dialog.

        Args:
            parent: Parent widget
            release_info: Release information from GitHub API
            current_version: Current application version
        """
        super().__init__(parent)
        self.release_info = release_info
        self.current_version = current_version
        self.snooze_hours = 24
        self.user_action = None  # 'update', 'snooze', or 'skip'

        self.setWindowTitle("Update Available")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        self._setup_ui()

    def _setup_ui(self):
        """Set up the dialog UI."""
        # Set dialog background to match app theme
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e2e;
                color: #cdd6f4;
            }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header = QLabel(f"AnkiGammon {self.release_info['version']} is available")
        header.setFont(QFont('Arial', 14, QFont.Bold))
        header.setStyleSheet("color: #cdd6f4;")
        layout.addWidget(header)

        # Version comparison
        version_label = QLabel(
            f"You have: <b>{self.current_version}</b><br>"
            f"Available: <b>{self.release_info['version']}</b>"
        )
        version_label.setStyleSheet("color: #a6adc8; margin-bottom: 10px;")
        layout.addWidget(version_label)

        # Release date (if available)
        published = self.release_info.get('published_at', '')
        if published:
            try:
                # Parse ISO date
                pub_date = datetime.fromisoformat(published.replace('Z', '+00:00'))
                date_str = pub_date.strftime('%B %d, %Y')
                date_label = QLabel(f"Released: {date_str}")
                date_label.setStyleSheet("color: #6c7086; font-size: 11px;")
                layout.addWidget(date_label)
            except (ValueError, AttributeError):
                pass

        # Release notes section
        notes_label = QLabel("What's new:")
        notes_label.setFont(QFont('Arial', 11, QFont.Bold))
        notes_label.setStyleSheet("margin-top: 10px; color: #cdd6f4;")
        layout.addWidget(notes_label)

        # Release notes text
        notes_text = QTextEdit()
        notes_text.setReadOnly(True)
        notes_text.setPlainText(
            self.release_info.get('release_notes', 'No release notes available.')
        )
        notes_text.setMinimumHeight(150)
        notes_text.setStyleSheet("""
            QTextEdit {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 10px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
            }
        """)
        layout.addWidget(notes_text)

        layout.addStretch()

        # Button layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        # Skip button
        skip_btn = QPushButton("Skip This Version")
        skip_btn.clicked.connect(self._on_skip)
        skip_btn.setCursor(Qt.PointingHandCursor)
        skip_btn.setStyleSheet("""
            QPushButton {
                background-color: #45475a;
                color: #cdd6f4;
                border: 1px solid #585b70;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #585b70;
                border: 1px solid #6c7086;
            }
        """)
        button_layout.addWidget(skip_btn)

        # Snooze button
        snooze_btn = QPushButton("Remind Me Tomorrow")
        snooze_btn.clicked.connect(self._on_snooze)
        snooze_btn.setCursor(Qt.PointingHandCursor)
        snooze_btn.setStyleSheet("""
            QPushButton {
                background-color: #45475a;
                color: #cdd6f4;
                border: 1px solid #585b70;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #585b70;
                border: 1px solid #6c7086;
            }
        """)
        button_layout.addWidget(snooze_btn)

        button_layout.addStretch()

        # Update button (prominent)
        update_btn = QPushButton("Download Update")
        update_btn.clicked.connect(self._on_update)
        update_btn.setDefault(True)
        update_btn.setCursor(Qt.PointingHandCursor)
        update_btn.setStyleSheet("""
            QPushButton {
                background-color: #a6e3a1;
                color: #1e1e2e;
                border: none;
                padding: 8px 20px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #94e2d5;
            }
            QPushButton:pressed {
                background-color: #89dceb;
            }
        """)
        button_layout.addWidget(update_btn)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def _on_update(self):
        """Handle download update button click."""
        self.user_action = 'update'
        download_url = self.release_info.get('download_url', '')
        if download_url:
            webbrowser.open(download_url)
        self.accept()

    def _on_snooze(self):
        """Handle snooze button click."""
        self.user_action = 'snooze'
        self.accept()

    def _on_skip(self):
        """Handle skip version button click."""
        self.user_action = 'skip'
        self.accept()

    def get_snooze_until(self) -> str:
        """Get the snooze-until timestamp.

        Returns:
            ISO format timestamp
        """
        return (datetime.now() + timedelta(hours=self.snooze_hours)).isoformat()


class CheckingUpdateDialog(QDialog):
    """Simple dialog shown while checking for updates."""

    def __init__(self, parent):
        """Initialize checking dialog.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("Checking for Updates")
        self.setModal(True)
        self.setMinimumWidth(300)

        # Remove close button
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint)

        # Set dialog background to match app theme
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e2e;
                color: #cdd6f4;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(30, 20, 30, 20)

        label = QLabel("Checking for updates...")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: #cdd6f4;")
        layout.addWidget(label)

        self.setLayout(layout)


class NoUpdateDialog(QDialog):
    """Dialog shown when no update is available."""

    def __init__(self, parent, current_version: str):
        """Initialize no-update dialog.

        Args:
            parent: Parent widget
            current_version: Current application version
        """
        super().__init__(parent)
        self.setWindowTitle("No Updates Available")
        self.setMinimumWidth(350)

        # Set dialog background to match app theme
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e2e;
                color: #cdd6f4;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)

        # Success icon and message
        message = QLabel(f"✓ You're up to date!\n\nVersion {current_version} is the latest version.")
        message.setAlignment(Qt.AlignCenter)
        message.setFont(QFont('Arial', 11))
        message.setStyleSheet("color: #a6e3a1; margin: 20px 0;")
        layout.addWidget(message)

        # OK button
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        ok_btn.setDefault(True)
        ok_btn.setMinimumWidth(100)
        ok_btn.setCursor(Qt.PointingHandCursor)
        ok_btn.setStyleSheet("""
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
        """)
        button_layout.addWidget(ok_btn)
        button_layout.addStretch()

        layout.addLayout(button_layout)

        self.setLayout(layout)


class UpdateCheckFailedDialog(QDialog):
    """Dialog shown when update check fails due to network error."""

    def __init__(self, parent, current_version: str):
        """Initialize failed check dialog.

        Args:
            parent: Parent widget
            current_version: Current application version
        """
        super().__init__(parent)
        self.setWindowTitle("Update Check Failed")
        self.setMinimumWidth(400)

        # Set dialog background to match app theme
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e2e;
                color: #cdd6f4;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)

        # Error icon and message
        message = QLabel(
            f"⚠ Couldn't check for updates\n\n"
            f"Unable to connect to the internet.\n\n"
            f"Current version: {current_version}"
        )
        message.setAlignment(Qt.AlignCenter)
        message.setFont(QFont('Arial', 11))
        message.setStyleSheet("color: #f38ba8; margin: 20px 0;")
        layout.addWidget(message)

        # OK button
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        ok_btn.setDefault(True)
        ok_btn.setMinimumWidth(100)
        ok_btn.setCursor(Qt.PointingHandCursor)
        ok_btn.setStyleSheet("""
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
        """)
        button_layout.addWidget(ok_btn)
        button_layout.addStretch()

        layout.addLayout(button_layout)

        self.setLayout(layout)
