"""
Smart input widget with auto-detection and visual feedback.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
    QLabel, QFrame, QPushButton
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont
import qtawesome as qta

from flashgammon.settings import Settings
from flashgammon.gui.format_detector import FormatDetector, DetectionResult, InputFormat


class SmartInputWidget(QWidget):
    """
    Input widget with intelligent format detection.

    Signals:
        format_detected(DetectionResult): Emitted when format is detected
    """

    format_detected = Signal(DetectionResult)

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.detector = FormatDetector(settings)
        self.last_result = None

        # Debounce timer for detection
        self.detection_timer = QTimer()
        self.detection_timer.setSingleShot(True)
        self.detection_timer.timeout.connect(self._run_detection)

        self._setup_ui()

    def _setup_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Label
        label = QLabel("Input Text:")
        label.setStyleSheet("font-weight: 600; color: #cdd6f4;")
        layout.addWidget(label)

        # Text input area
        self.text_area = QPlainTextEdit()
        self.text_area.setPlaceholderText(
            "Paste XG analysis or position IDs here...\n\n"
            "Examples:\n"
            "• Full XG analysis (Ctrl+C from eXtreme Gammon)\n"
            "• XGID lines (one per line)\n"
            "• GNUID format"
        )

        # Use fixed-width font for better XGID readability
        font = QFont("Consolas", 10)
        if not font.exactMatch():
            font = QFont("Courier New", 10)
        self.text_area.setFont(font)

        self.text_area.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.text_area.setTabChangesFocus(True)
        self.text_area.setMinimumHeight(300)

        # Dark theme styling
        self.text_area.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 2px solid #313244;
                border-radius: 8px;
                padding: 12px;
                selection-background-color: #585b70;
            }
            QPlainTextEdit:focus {
                border-color: #89b4fa;
            }
        """)

        self.text_area.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.text_area, stretch=1)

        # Feedback panel
        self.feedback_panel = QFrame()
        self.feedback_panel.setStyleSheet("""
            QFrame {
                background-color: #313244;
                border-left: 4px solid #6c7086;
                border-radius: 6px;
                padding: 12px;
            }
        """)
        self.feedback_panel.setVisible(False)

        feedback_layout = QHBoxLayout(self.feedback_panel)
        feedback_layout.setContentsMargins(12, 12, 12, 12)
        feedback_layout.setSpacing(12)  # Add spacing between icon and text

        # Icon
        self.feedback_icon = QLabel()
        self.feedback_icon.setPixmap(qta.icon('fa6s.circle-info', color='#60a5fa').pixmap(20, 20))
        self.feedback_icon.setFixedSize(20, 20)
        feedback_layout.addWidget(self.feedback_icon)

        # Text content
        text_content = QVBoxLayout()
        text_content.setSpacing(4)

        self.feedback_title = QLabel()
        self.feedback_title.setStyleSheet("font-weight: 600; font-size: 13px;")
        text_content.addWidget(self.feedback_title)

        self.feedback_detail = QLabel()
        self.feedback_detail.setStyleSheet("font-size: 12px; color: #a6adc8;")
        self.feedback_detail.setWordWrap(True)
        text_content.addWidget(self.feedback_detail)

        feedback_layout.addLayout(text_content, stretch=1)

        # Override button
        self.override_btn = QPushButton("Override...")
        self.override_btn.setVisible(False)
        self.override_btn.setStyleSheet("""
            QPushButton {
                background-color: #45475a;
                color: #cdd6f4;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #585b70;
            }
        """)
        feedback_layout.addWidget(self.override_btn, alignment=Qt.AlignTop)

        layout.addWidget(self.feedback_panel)

    def _on_text_changed(self):
        """Handle text change (debounced)."""
        # Cancel previous timer, start new one
        self.detection_timer.stop()
        self.detection_timer.start(500)  # 500ms debounce

    def _run_detection(self):
        """Run format detection (after debounce)."""
        text = self.text_area.toPlainText()

        if not text.strip():
            self.feedback_panel.setVisible(False)
            self.last_result = None
            return

        result = self.detector.detect(text)
        self.last_result = result
        self._update_feedback_ui(result)
        self.format_detected.emit(result)

    def _update_feedback_ui(self, result: DetectionResult):
        """Update feedback panel with detection result."""
        self.feedback_panel.setVisible(True)

        # Update icon and styling based on result
        if result.format == InputFormat.POSITION_IDS:
            if result.warnings:
                # Warning state (GnuBG not configured)
                self.feedback_icon.setPixmap(qta.icon('fa6s.triangle-exclamation', color='#fab387').pixmap(20, 20))
                self.feedback_panel.setStyleSheet("""
                    QFrame {
                        background-color: #2e2416;
                        border-left: 4px solid #f9e2af;
                        border-radius: 6px;
                        padding: 12px;
                    }
                """)
                self.feedback_title.setStyleSheet("font-weight: 600; font-size: 13px; color: #f9e2af;")
                self.feedback_title.setText(f"{result.details}")
                self.feedback_detail.setText(
                    result.warnings[0] + "\nConfigure GnuBG in Settings to analyze positions."
                )
            else:
                # Success state
                self.feedback_icon.setPixmap(qta.icon('fa6s.circle-check', color='#a6e3a1').pixmap(20, 20))
                self.feedback_panel.setStyleSheet("""
                    QFrame {
                        background-color: #1e2d1f;
                        border-left: 4px solid #a6e3a1;
                        border-radius: 6px;
                        padding: 12px;
                    }
                """)
                self.feedback_title.setStyleSheet("font-weight: 600; font-size: 13px; color: #a6e3a1;")
                self.feedback_title.setText(f"{result.details}")

                # Calculate estimated time
                est_seconds = result.count * 5  # ~5 seconds per position
                self.feedback_detail.setText(
                    f"Will analyze with GnuBG (ply {self.settings.gnubg_analysis_ply})\n"
                    f"Estimated time: ~{est_seconds} seconds"
                )

        elif result.format == InputFormat.FULL_ANALYSIS:
            # Success state (blue)
            self.feedback_icon.setPixmap(qta.icon('fa6s.circle-check', color='#89b4fa').pixmap(20, 20))
            self.feedback_panel.setStyleSheet("""
                QFrame {
                    background-color: #1e2633;
                    border-left: 4px solid #89b4fa;
                    border-radius: 6px;
                    padding: 12px;
                }
            """)
            self.feedback_title.setStyleSheet("font-weight: 600; font-size: 13px; color: #89b4fa;")
            self.feedback_title.setText(f"{result.details}")

            # Show preview of first position if available
            preview_text = "Ready to add to export list"
            if result.position_previews:
                preview_text += f"\nFirst position: {result.position_previews[0]}"

            if result.warnings:
                preview_text += f"\n{result.warnings[0]}"

            self.feedback_detail.setText(preview_text)

        else:
            # Unknown/error state
            self.feedback_icon.setPixmap(qta.icon('fa6s.triangle-exclamation', color='#fab387').pixmap(20, 20))
            self.feedback_panel.setStyleSheet("""
                QFrame {
                    background-color: #2e2416;
                    border-left: 4px solid #fab387;
                    border-radius: 6px;
                    padding: 12px;
                }
            """)
            self.feedback_title.setStyleSheet("font-weight: 600; font-size: 13px; color: #fab387;")
            self.feedback_title.setText(f"{result.details}")

            warning_text = "Paste XGID/GNUID or full XG analysis text"
            if result.warnings:
                warning_text = "\n".join(result.warnings)

            self.feedback_detail.setText(warning_text)

    def get_text(self) -> str:
        """Get current input text."""
        return self.text_area.toPlainText()

    def clear_text(self):
        """Clear input text."""
        self.text_area.clear()
        self.feedback_panel.setVisible(False)
        self.last_result = None

    def get_last_result(self) -> DetectionResult:
        """Get last detection result."""
        return self.last_result
