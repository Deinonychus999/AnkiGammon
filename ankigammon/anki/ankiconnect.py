"""Anki-Connect integration for direct note creation in Anki."""

import json
import requests
from pathlib import Path
from typing import List, Dict, Any

from ankigammon.models import Decision
from ankigammon.anki.card_generator import CardGenerator
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
        tags: List[str]
    ) -> int:
        """
        Add a note to Anki.

        Args:
            front: Front HTML (with embedded SVG)
            back: Back HTML (with embedded SVG)
            tags: List of tags

        Returns:
            Note ID
        """
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
                'allowDuplicate': True
            }
        }

        return self.invoke('addNote', note=note)

    def export_decisions(
        self,
        decisions: List[Decision],
        output_dir: Path,
        show_options: bool = False,
        color_scheme: str = "classic",
        interactive_moves: bool = False,
        orientation: str = "counter-clockwise"
    ) -> Dict[str, Any]:
        """
        Export decisions directly to Anki via Anki-Connect.

        Args:
            decisions: List of Decision objects
            output_dir: Directory for configuration (no media files needed)
            show_options: Show multiple choice options (text-based)
            color_scheme: Board color scheme name
            interactive_moves: Enable interactive move visualization
            orientation: Board orientation ("clockwise" or "counter-clockwise")

        Returns:
            Dictionary with export statistics
        """
        # Test connection
        if not self.test_connection():
            raise Exception("Cannot connect to Anki-Connect")

        # Create model and deck
        self.create_model()
        self.create_deck()

        # Create renderer with color scheme
        from ankigammon.renderer.color_schemes import get_scheme
        from ankigammon.renderer.svg_board_renderer import SVGBoardRenderer

        scheme = get_scheme(color_scheme)
        renderer = SVGBoardRenderer(color_scheme=scheme, orientation=orientation)

        # Create card generator
        card_gen = CardGenerator(
            output_dir=output_dir,
            show_options=show_options,
            interactive_moves=interactive_moves,
            renderer=renderer
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
                    tags=card_data['tags']
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
