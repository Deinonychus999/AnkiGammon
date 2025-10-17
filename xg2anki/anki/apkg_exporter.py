"""Export XG decisions to Anki .apkg file using genanki."""

import genanki
import random
from pathlib import Path
from typing import List

from xg2anki.models import Decision
from xg2anki.anki.card_generator import CardGenerator
from xg2anki.anki.card_styles import MODEL_NAME, CARD_CSS


class ApkgExporter:
    """
    Export XG decisions to Anki .apkg file.
    """

    def __init__(self, output_dir: Path, deck_name: str = "XG Backgammon"):
        """
        Initialize the APKG exporter.

        Args:
            output_dir: Directory for output files
            deck_name: Name of the Anki deck
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.deck_name = deck_name

        # Generate unique IDs
        self.deck_id = random.randrange(1 << 30, 1 << 31)
        self.model_id = random.randrange(1 << 30, 1 << 31)

        # Create model
        self.model = self._create_model()

        # Create deck
        self.deck = genanki.Deck(self.deck_id, self.deck_name)

    def _create_model(self) -> genanki.Model:
        """Create the Anki note model."""
        return genanki.Model(
            self.model_id,
            MODEL_NAME,
            fields=[
                {'name': 'Front'},
                {'name': 'Back'},
            ],
            templates=[
                {
                    'name': 'Card 1',
                    'qfmt': '{{Front}}',
                    'afmt': '{{Back}}',
                },
            ],
            css=CARD_CSS
        )

    def export(
        self,
        decisions: List[Decision],
        output_file: str = "xg_deck.apkg",
        show_options: bool = False
    ) -> str:
        """
        Export decisions to an APKG file.

        Args:
            decisions: List of Decision objects
            output_file: Output filename
            show_options: Show multiple choice options (text-based)

        Returns:
            Path to generated APKG file
        """
        # Create card generator
        card_gen = CardGenerator(
            output_dir=self.output_dir,
            show_options=show_options
        )

        # Generate cards
        media_files = []
        for i, decision in enumerate(decisions):
            card_data = card_gen.generate_card(decision, card_id=f"card_{i}")

            # Create note
            note = genanki.Note(
                model=self.model,
                fields=[card_data['front'], card_data['back']],
                tags=card_data['tags']
            )

            # Add to deck
            self.deck.add_note(note)

            # Collect media files
            media_files.extend(card_data['media_files'])

        # Create package
        output_path = self.output_dir / output_file
        package = genanki.Package(self.deck)
        package.media_files = media_files

        # Write APKG
        package.write_to_file(str(output_path))

        return str(output_path)
