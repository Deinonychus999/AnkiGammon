from PySide6.QtWidgets import QTextBrowser

from ankigammon.gui.dialogs.update_dialog import UpdateDialog


def _dialog() -> UpdateDialog:
    return UpdateDialog(
        None,
        {
            'version': '1.14.0',
            'release_notes': 'Opens the [trainer](https://ankigammon.com/train/).',
        },
        '1.13.0',
    )


def test_release_note_links_open_in_browser(qapp):
    dialog = _dialog()
    notes = dialog.findChild(QTextBrowser)

    assert notes is not None
    assert notes.openExternalLinks()


def test_release_note_links_are_readable_on_dark_background(qapp):
    dialog = _dialog()
    notes = dialog.findChild(QTextBrowser)

    block = notes.document().begin()
    link_colors = []
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            fmt = it.fragment().charFormat()
            if fmt.isAnchor():
                link_colors.append(fmt.foreground().color())
            it += 1
        block = block.next()

    assert link_colors
    assert all(color.lightness() > 150 for color in link_colors)
