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
