"""The main window's first-launch size fits the screen it opens on."""

from PySide6.QtCore import QSize

from ankigammon.gui.main_window import fitted_window_size

DEFAULT = QSize(1300, 720)
MINIMUM = QSize(800, 600)


def test_the_default_size_when_the_screen_has_room():
    assert fitted_window_size(DEFAULT, MINIMUM, QSize(1920, 1040)) == DEFAULT


def test_shrinks_to_fit_a_laptop_screen_with_room_for_the_title_bar():
    # 1366x768 with a 40px taskbar: 1300x720 plus a title bar ran off the bottom
    size = fitted_window_size(DEFAULT, MINIMUM, QSize(1366, 728))
    assert size.width() <= 1366 and size.height() <= 728 * 0.9
    assert size.width() >= MINIMUM.width() and size.height() >= MINIMUM.height()


def test_never_below_the_minimum_the_layout_needs():
    assert fitted_window_size(DEFAULT, MINIMUM, QSize(800, 600)) == MINIMUM
