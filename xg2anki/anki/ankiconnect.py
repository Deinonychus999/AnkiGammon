"""Anki-Connect integration for direct note creation in Anki."""

import json
import base64
import requests
from pathlib import Path
from typing import List, Dict, Any

from xg2anki.models import Decision
from xg2anki.anki.card_generator import CardGenerator
from xg2anki.anki.card_styles import MODEL_NAME, CARD_CSS


class AnkiConnect:
    """
    Interface to Anki via Anki-Connect addon.

    Requires: Anki-Connect addon installed in Anki
    https://ankiweb.net/shared/info/2055492159
    """

    def __init__(self, url: str = "http://localhost:8765", deck_name: str = "XG Backgammon"):
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

    def create_deck(self) -> None:
        """Create the target deck if it doesn't exist."""
        self.invoke('createDeck', deck=self.deck_name)

    def create_model(self) -> None:
        """Create the XG Backgammon note type if it doesn't exist."""
        # Check if model already exists
        model_names = self.invoke('modelNames')
        if MODEL_NAME in model_names:
            # Update the styling of existing model
            self.invoke('updateModelStyling', model={'name': MODEL_NAME, 'css': CARD_CSS})
            return

        # Create new model
        model = {
            'modelName': MODEL_NAME,
            'inOrderFields': ['Front', 'Back'],
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
        media_files: List[str]
    ) -> int:
        """
        Add a note to Anki.

        Args:
            front: Front HTML
            back: Back HTML
            tags: List of tags
            media_files: List of media file paths

        Returns:
            Note ID
        """
        # Store media files in Anki
        for media_file in media_files:
            self._store_media_file(media_file)

        # Create note
        note = {
            'deckName': self.deck_name,
            'modelName': MODEL_NAME,
            'fields': {
                'Front': front,
                'Back': back,
            },
            'tags': tags,
            'options': {
                'allowDuplicate': False
            }
        }

        return self.invoke('addNote', note=note)

    def _store_media_file(self, file_path: str) -> None:
        """
        Store a media file in Anki's collection.

        Args:
            file_path: Path to media file
        """
        path = Path(file_path)
        if not path.exists():
            return

        # Read file and encode as base64
        with open(path, 'rb') as f:
            data = base64.b64encode(f.read()).decode('utf-8')

        # Store in Anki
        self.invoke(
            'storeMediaFile',
            filename=path.name,
            data=data
        )

    def export_decisions(
        self,
        decisions: List[Decision],
        output_dir: Path,
        show_options: bool = False
    ) -> Dict[str, Any]:
        """
        Export decisions directly to Anki via Anki-Connect.

        Args:
            decisions: List of Decision objects
            output_dir: Directory for temporary media files
            show_options: Show multiple choice options (text-based)

        Returns:
            Dictionary with export statistics
        """
        # Test connection
        if not self.test_connection():
            raise Exception("Cannot connect to Anki-Connect")

        # Create model and deck
        self.create_model()
        self.create_deck()

        # Create card generator
        card_gen = CardGenerator(
            output_dir=output_dir,
            show_options=show_options
        )

        # Generate and add cards
        added = 0
        skipped = 0
        errors = []

        for i, decision in enumerate(decisions):
            try:
                card_data = card_gen.generate_card(decision, card_id=f"card_{i}")

                note_id = self.add_note(
                    front=card_data['front'],
                    back=card_data['back'],
                    tags=card_data['tags'],
                    media_files=card_data['media_files']
                )

                if note_id:
                    added += 1
                else:
                    skipped += 1

            except Exception as e:
                errors.append(f"Card {i}: {str(e)}")

        return {
            'added': added,
            'skipped': skipped,
            'errors': errors,
            'total': len(decisions)
        }
