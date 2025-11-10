"""
Silent message box helpers that suppress system beep sounds.

This module provides drop-in replacements for QMessageBox static methods
that maintain the exact same visual appearance but without triggering
Windows system sounds (beeps).

The key technique is using setIconPixmap() instead of setIcon(), which
bypasses Qt's accessibility system that triggers the system sounds.
"""

from PySide6.QtWidgets import QMessageBox


def _silent_msgbox(parent, title: str, text: str, icon_type):
    """
    Internal helper to show message box without system sound.

    Args:
        parent: Parent widget
        title: Dialog title
        text: Dialog message
        icon_type: QMessageBox.Icon enum value

    Returns:
        Dialog result (button clicked)
    """
    msgBox = QMessageBox(parent)
    msgBox.setWindowTitle(title)
    msgBox.setText(text)
    msgBox.setStandardButtons(QMessageBox.StandardButton.Ok)
    # Use pixmap instead of setIcon() to avoid triggering accessibility sounds
    msgBox.setIconPixmap(QMessageBox.standardIcon(icon_type))
    return msgBox.exec()


def information(parent, title: str, text: str) -> int:
    """
    Show information message without system sound.

    Drop-in replacement for QMessageBox.information().

    Args:
        parent: Parent widget
        title: Dialog title
        text: Dialog message

    Returns:
        QMessageBox.StandardButton value (always Ok for information)
    """
    return _silent_msgbox(parent, title, text, QMessageBox.Icon.Information)


def warning(parent, title: str, text: str) -> int:
    """
    Show warning message without system sound.

    Drop-in replacement for QMessageBox.warning().

    Args:
        parent: Parent widget
        title: Dialog title
        text: Dialog message

    Returns:
        QMessageBox.StandardButton value (always Ok for warning)
    """
    return _silent_msgbox(parent, title, text, QMessageBox.Icon.Warning)


def critical(parent, title: str, text: str) -> int:
    """
    Show critical/error message without system sound.

    Drop-in replacement for QMessageBox.critical().

    Args:
        parent: Parent widget
        title: Dialog title
        text: Dialog message

    Returns:
        QMessageBox.StandardButton value (always Ok for critical)
    """
    return _silent_msgbox(parent, title, text, QMessageBox.Icon.Critical)


def question(parent, title: str, text: str,
             buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
             default_button=QMessageBox.StandardButton.No) -> int:
    """
    Show question dialog without system sound.

    Drop-in replacement for QMessageBox.question().

    Args:
        parent: Parent widget
        title: Dialog title
        text: Dialog message
        buttons: Standard buttons to show (default: Yes|No)
        default_button: Default button (default: No)

    Returns:
        QMessageBox.StandardButton value indicating which button was clicked
    """
    msgBox = QMessageBox(parent)
    msgBox.setWindowTitle(title)
    msgBox.setText(text)
    msgBox.setStandardButtons(buttons)
    msgBox.setDefaultButton(default_button)
    # Use pixmap instead of setIcon() to avoid triggering accessibility sounds
    msgBox.setIconPixmap(QMessageBox.standardIcon(QMessageBox.Icon.Question))
    return msgBox.exec()


# Keep QMessageBox.about() available since it's already silent
about = QMessageBox.about
