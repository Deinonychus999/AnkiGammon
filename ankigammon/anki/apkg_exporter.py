"""Export XG decisions to Anki .apkg file using genanki."""

import genanki
import random
from pathlib import Path
from typing import List

from ankigammon.models import Decision
from ankigammon.anki.card_generator import CardGenerator
from ankigammon.anki.card_styles import MODEL_NAME, CARD_CSS


class ApkgExporter:
    """
    Export XG decisions to Anki .apkg file.
    """

    def __init__(self, output_dir: Path, deck_name: str = "My AnkiGammon Deck"):
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
        show_options: bool = False,
        color_scheme: str = "classic",
        interactive_moves: bool = False,
        orientation: str = "counter-clockwise",
        progress_callback: callable = None
    ) -> str:
        """
        Export decisions to an APKG file.

        Args:
            decisions: List of Decision objects
            output_file: Output filename
            show_options: Show multiple choice options (text-based)
            color_scheme: Board color scheme name
            interactive_moves: Enable interactive move visualization
            orientation: Board orientation ("clockwise" or "counter-clockwise")
            progress_callback: Optional callback(message: str) for progress updates

        Returns:
            Path to generated APKG file
        """
        # Create renderer with color scheme
        from ankigammon.renderer.color_schemes import get_scheme
        from ankigammon.renderer.svg_board_renderer import SVGBoardRenderer

        scheme = get_scheme(color_scheme)
        renderer = SVGBoardRenderer(color_scheme=scheme, orientation=orientation)

        # Create card generator
        card_gen = CardGenerator(
            output_dir=self.output_dir,
            show_options=show_options,
            interactive_moves=interactive_moves,
            renderer=renderer,
            progress_callback=progress_callback
        )

        # Generate cards
        for i, decision in enumerate(decisions):
            if progress_callback:
                progress_callback(f"Position {i+1}/{len(decisions)}: Starting...")
            card_data = card_gen.generate_card(decision, card_id=f"card_{i}")

            # Create note
            note = genanki.Note(
                model=self.model,
                fields=[card_data['front'], card_data['back']],
                tags=card_data['tags']
            )

            # Add to deck
            self.deck.add_note(note)

        # Create package (no media files needed - SVG is embedded)
        output_path = self.output_dir / output_file
        package = genanki.Package(self.deck)

        # Write APKG
        package.write_to_file(str(output_path))

        return str(output_path)
