"""Export XG decisions to Anki .apkg file using genanki."""

import genanki
import random
from pathlib import Path
from typing import List

from ankigammon.models import Decision
from ankigammon.anki.card_generator import CardGenerator
from ankigammon.anki.card_styles import MODEL_NAME, CARD_CSS
from ankigammon.settings import get_settings


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

        self.deck_id = random.randrange(1 << 30, 1 << 31)
        self.model_id = random.randrange(1 << 30, 1 << 31)

        self.model = self._create_model()
        self.deck = genanki.Deck(self.deck_id, self.deck_name)

    def _create_model(self) -> genanki.Model:
        """Create the Anki note model."""
        return genanki.Model(
            self.model_id,
            MODEL_NAME,
            fields=[
                {'name': 'XGID'},
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
            css=CARD_CSS,
            sort_field_index=0  # XGID is the sort field
        )

    def export(
        self,
        decisions: List[Decision],
        output_file: str = "xg_deck.apkg",
        show_options: bool = False,
        color_scheme: str = "classic",
        interactive_moves: bool = False,
        orientation: str = "counter-clockwise",
        progress_callback: callable = None,
        use_subdecks: bool = False
    ) -> str:
        """
        Export decisions to an APKG file.

        Args:
            decisions: List of Decision objects
            output_file: Output filename
            show_options: Show multiple choice options
            color_scheme: Board color scheme name
            interactive_moves: Enable interactive move visualization
            orientation: Board orientation
            progress_callback: Optional callback for progress updates
            use_subdecks: Whether to organize into subdecks by decision type

        Returns:
            Path to generated APKG file
        """
        from ankigammon.renderer.color_schemes import get_scheme
        from ankigammon.renderer.svg_board_renderer import SVGBoardRenderer
        from ankigammon.anki.deck_utils import group_decisions_by_deck

        scheme = get_scheme(color_scheme)
        if get_settings().swap_checker_colors:
            scheme = scheme.with_swapped_checkers()
        renderer = SVGBoardRenderer(color_scheme=scheme, orientation=orientation)

        card_gen = CardGenerator(
            output_dir=self.output_dir,
            show_options=show_options,
            interactive_moves=interactive_moves,
            renderer=renderer,
            progress_callback=progress_callback
        )

        # Group decisions by deck
        decisions_by_deck = group_decisions_by_deck(decisions, self.deck_name, use_subdecks)

        # Create deck objects for each group
        decks_dict = {}
        for deck_name in decisions_by_deck.keys():
            deck_id = random.randrange(1 << 30, 1 << 31)
            decks_dict[deck_name] = genanki.Deck(deck_id, deck_name)

        # Generate cards and add to appropriate decks
        card_index = 0
        for deck_name, deck_decisions in decisions_by_deck.items():
            deck = decks_dict[deck_name]

            for decision in deck_decisions:
                if progress_callback:
                    progress_callback(f"Position {card_index+1}/{len(decisions)}: Starting...")

                card_data = card_gen.generate_card(decision, card_id=f"card_{card_index}")

                note = genanki.Note(
                    model=self.model,
                    fields=[card_data.get('xgid', ''), card_data['front'], card_data['back']],
                    tags=card_data['tags']
                )

                deck.add_note(note)
                card_index += 1

        # Package all decks into single APKG file
        output_path = self.output_dir / output_file
        package = genanki.Package(list(decks_dict.values()))
        package.write_to_file(str(output_path))

        return str(output_path)
