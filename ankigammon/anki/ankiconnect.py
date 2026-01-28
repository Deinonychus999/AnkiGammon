"""Anki-Connect integration for direct note creation in Anki."""

import requests
from typing import Any, List

from ankigammon.anki.card_styles import MODEL_NAME, CARD_CSS


class AnkiConnect:
    """
    Interface to Anki via Anki-Connect addon.

    Requires: Anki-Connect addon installed in Anki
    https://ankiweb.net/shared/info/2055492159
    """

    def __init__(self, url: str = "http://localhost:8765", deck_name: str = "My AnkiGammon Deck"):
        """
        Initialize Anki-Connect client.

        Args:
            url: Anki-Connect API URL
            deck_name: Target deck name
        """
        self.url = url
        self.deck_name = deck_name

    def invoke(self, action: str, **params) -> Any:
        """
        Invoke an Anki-Connect action.

        Args:
            action: Action name
            **params: Action parameters

        Returns:
            Action result

        Raises:
            Exception: If request fails or Anki returns error
        """
        payload = {
            'action': action,
            'version': 6,
            'params': params
        }

        try:
            response = requests.post(self.url, json=payload, timeout=5)
            response.raise_for_status()
            result = response.json()

            if 'error' in result and result['error']:
                raise Exception(f"Anki-Connect error: {result['error']}")

            return result.get('result')

        except requests.exceptions.ConnectionError as e:
            raise Exception(
                f"Could not connect to Anki-Connect at {self.url}. "
                f"Make sure Anki is running and Anki-Connect addon is installed. "
                f"Details: {str(e)}"
            )
        except requests.exceptions.Timeout:
            raise Exception(
                f"Connection to Anki-Connect at {self.url} timed out. "
                "Make sure Anki is running and responsive."
            )
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {str(e)}")

    def test_connection(self) -> bool:
        """
        Test connection to Anki-Connect.

        Returns:
            True if connection successful
        """
        try:
            self.invoke('version')
            return True
        except Exception:
            return False

    def create_deck(self, deck_name: str = None) -> None:
        """
        Create a deck if it doesn't exist.

        Args:
            deck_name: Deck name to create. If None, uses self.deck_name.
        """
        if deck_name is None:
            deck_name = self.deck_name
        self.invoke('createDeck', deck=deck_name)

    def create_model(self) -> None:
        """Create the XG Backgammon note type if it doesn't exist."""
        model_names = self.invoke('modelNames')
        if MODEL_NAME in model_names:
            # Update styling for existing model
            self.invoke('updateModelStyling', model={'name': MODEL_NAME, 'css': CARD_CSS})
            # Check if XGID field exists, add it if missing
            field_names = self.invoke('modelFieldNames', modelName=MODEL_NAME)
            if 'XGID' not in field_names:
                # Add XGID field at the beginning (index 0)
                self.invoke('modelFieldAdd', modelName=MODEL_NAME, fieldName='XGID', index=0)
            return

        model = {
            'modelName': MODEL_NAME,
            'inOrderFields': ['XGID', 'Front', 'Back'],
            'css': CARD_CSS,
            'cardTemplates': [
                {
                    'Name': 'Card 1',
                    'Front': '{{Front}}',
                    'Back': '{{Back}}'
                }
            ]
        }
        self.invoke('createModel', **model)

    def add_note(
        self,
        front: str,
        back: str,
        tags: List[str],
        deck_name: str = None,
        xgid: str = ''
    ) -> int:
        """
        Add a note to Anki.

        Args:
            front: Front HTML with embedded SVG
            back: Back HTML with embedded SVG
            tags: List of tags
            deck_name: Target deck name. If None, uses self.deck_name.
            xgid: XGID string for the position (used as sort field)

        Returns:
            Note ID
        """
        if deck_name is None:
            deck_name = self.deck_name

        note = {
            'deckName': deck_name,
            'modelName': MODEL_NAME,
            'fields': {
                'XGID': xgid,
                'Front': front,
                'Back': back,
            },
            'tags': tags,
            'options': {
                'allowDuplicate': True
            }
        }

        return self.invoke('addNote', note=note)

    def find_notes_by_xgid(self, xgid: str) -> List[int]:
        """
        Find note IDs matching an XGID value.

        Args:
            xgid: XGID string to search for

        Returns:
            List of matching note IDs (may be empty)
        """
        escaped_xgid = xgid.replace('"', '\\"')
        query = f'"XGID:{escaped_xgid}" "note:{MODEL_NAME}"'
        return self.invoke('findNotes', query=query)

    def update_note_fields(
        self,
        note_id: int,
        front: str,
        back: str,
        xgid: str = ''
    ) -> None:
        """
        Update an existing note's fields.

        Args:
            note_id: Anki note ID to update
            front: New front HTML
            back: New back HTML
            xgid: XGID string
        """
        self.invoke('updateNoteFields', note={
            'id': note_id,
            'fields': {
                'XGID': xgid,
                'Front': front,
                'Back': back,
            }
        })

    def update_note_tags(self, note_id: int, tags: List[str]) -> None:
        """
        Replace all tags on an existing note.

        Args:
            note_id: Anki note ID
            tags: New list of tags
        """
        note_info = self.invoke('notesInfo', notes=[note_id])
        if note_info and len(note_info) > 0:
            old_tags = note_info[0].get('tags', [])
            if old_tags:
                self.invoke('removeTags', notes=[note_id], tags=' '.join(old_tags))
        if tags:
            self.invoke('addTags', notes=[note_id], tags=' '.join(tags))

    def upsert_note(
        self,
        front: str,
        back: str,
        tags: List[str],
        deck_name: str = None,
        xgid: str = ''
    ) -> int:
        """
        Update an existing note or add a new one, matched by XGID.

        Searches for an existing note with the same XGID. If found,
        updates its fields and tags (preserving review history).
        If not found, adds a new note.

        Args:
            front: Front HTML with embedded SVG
            back: Back HTML with embedded SVG
            tags: List of tags
            deck_name: Target deck name. If None, uses self.deck_name.
            xgid: XGID string for matching

        Returns:
            Note ID (existing or new)
        """
        if deck_name is None:
            deck_name = self.deck_name

        # Try to find existing note by XGID
        if xgid:
            existing_ids = self.find_notes_by_xgid(xgid)
            if existing_ids:
                note_id = existing_ids[0]
                self.update_note_fields(note_id, front, back, xgid)
                self.update_note_tags(note_id, tags)
                return note_id

        # No existing note found — add new
        return self.add_note(front, back, tags, deck_name, xgid)

    def delete_notes(self, note_ids: List[int]) -> None:
        """
        Delete notes and all their cards.

        Args:
            note_ids: List of note IDs to delete
        """
        if note_ids:
            self.invoke('deleteNotes', notes=note_ids)

    def find_all_deck_notes(self, deck_name: str = None) -> List[int]:
        """
        Find all AnkiGammon note IDs in a specific deck.

        Args:
            deck_name: Deck name to search. If None, uses self.deck_name.

        Returns:
            List of note IDs
        """
        if deck_name is None:
            deck_name = self.deck_name
        escaped_deck = deck_name.replace('"', '\\"')
        query = f'"deck:{escaped_deck}" "note:{MODEL_NAME}"'
        return self.invoke('findNotes', query=query)

    def notes_info(self, note_ids: List[int]) -> List[dict]:
        """
        Get detailed information for notes.

        Args:
            note_ids: List of Anki note IDs

        Returns:
            List of note info dicts with 'noteId', 'fields', 'tags', etc.
        """
        if not note_ids:
            return []
        return self.invoke('notesInfo', notes=note_ids)
