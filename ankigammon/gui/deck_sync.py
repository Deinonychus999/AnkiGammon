"""Background thread for syncing deck structure from Anki via AnkiConnect."""

import logging
from typing import List

from PySide6.QtCore import QThread, Signal

from ankigammon.anki.ankiconnect import AnkiConnect

logger = logging.getLogger(__name__)


class DeckSyncThread(QThread):
    """Background thread for fetching Anki subdeck names.

    Signals:
        decks_loaded(list): Emitted with list of deck name strings on success.
        sync_failed(str): Emitted with error message on failure.
    """

    decks_loaded = Signal(list)
    sync_failed = Signal(str)

    def __init__(self, root_deck_name: str):
        """Initialize sync thread.

        Args:
            root_deck_name: The root deck name to search for subdecks under.
        """
        super().__init__()
        self.root_deck_name = root_deck_name

    def run(self) -> None:
        """Fetch subdeck names from Anki in background."""
        try:
            client = AnkiConnect()
            if not client.test_connection():
                logger.info("Anki not available for deck sync")
                self.sync_failed.emit("Could not connect to Anki")
                return

            subdecks = client.get_subdecks(self.root_deck_name)
            logger.info(f"Loaded {len(subdecks)} deck(s) from Anki under '{self.root_deck_name}'")
            self.decks_loaded.emit(subdecks)

        except Exception as e:
            logger.warning(f"Deck sync failed: {e}")
            self.sync_failed.emit(str(e))
