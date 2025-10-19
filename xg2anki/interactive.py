"""Interactive CLI mode for XG2Anki - user-friendly position collection."""

import sys
from pathlib import Path
from typing import List, Optional

import click

from xg2anki.parsers.xg_text_parser import XGTextParser
from xg2anki.models import Decision
from xg2anki.settings import get_settings


class InteractiveSession:
    """Manages interactive CLI session for collecting positions."""

    def __init__(self):
        self.positions_text: List[str] = []
        self.current_buffer = []
        self.settings = get_settings()
        self.color_scheme = self.settings.color_scheme  # Load saved color scheme

    def run(self):
        """Run the interactive session."""
        self.show_welcome()

        while True:
            choice = self.show_main_menu()

            if choice == '1':
                self.create_new_deck()
            elif choice == '2':
                self.show_options_menu()
            elif choice == '3':
                self.show_help()
            elif choice == '4':
                click.echo("\nGoodbye!")
                sys.exit(0)
            else:
                click.echo(click.style("\n  Invalid choice. Please try again.\n", fg='red'))

    def show_welcome(self):
        """Display welcome banner."""
        click.echo()
        click.echo(click.style("=" * 60, fg='cyan'))
        click.echo(click.style("  XG2Anki - Backgammon Analysis to Anki Flashcards", fg='cyan', bold=True))
        click.echo(click.style("=" * 60, fg='cyan'))
        click.echo()

    def show_main_menu(self) -> str:
        """Show main menu and get user choice."""
        click.echo(click.style("Main Menu:", fg='yellow', bold=True))
        click.echo("  1. Create new deck")
        click.echo("  2. Options")
        click.echo("  3. Help")
        click.echo("  4. Exit")
        click.echo()

        return click.prompt(click.style("Choose an option", fg='green'),
                          type=str, default='1')

    def show_options_menu(self):
        """Show options submenu for configuring settings."""
        while True:
            click.echo()
            click.echo(click.style("=" * 60, fg='cyan'))
            click.echo(click.style("  Options", fg='cyan', bold=True))
            click.echo(click.style("=" * 60, fg='cyan'))
            click.echo()
            click.echo(f"  1. Color scheme (current: {self.color_scheme})")
            click.echo(f"  2. Show move options (current: {'Yes' if self.settings.show_options else 'No'})")

            # Format antialiasing display
            aa_scale = self.settings.antialias_scale
            aa_display = {1: "Off", 2: "2x", 3: "3x", 4: "4x"}.get(aa_scale, f"{aa_scale}x")
            click.echo(f"  3. Antialiasing quality (current: {aa_display})")

            click.echo("  4. Back to main menu")
            click.echo()

            choice = click.prompt(
                click.style("Choose an option", fg='green'),
                type=str,
                default='4'
            )

            if choice == '1':
                self.change_color_scheme()
            elif choice == '2':
                self.toggle_show_options()
            elif choice == '3':
                self.change_antialiasing()
            elif choice == '4':
                break
            else:
                click.echo(click.style("\n  Invalid choice. Please try again.\n", fg='red'))

    def change_color_scheme(self):
        """Allow user to change the board color scheme."""
        from xg2anki.renderer.color_schemes import list_schemes

        click.echo()
        click.echo(click.style("=" * 60, fg='cyan'))
        click.echo(click.style("  Color Scheme Selection", fg='cyan', bold=True))
        click.echo(click.style("=" * 60, fg='cyan'))
        click.echo()

        schemes = list_schemes()
        click.echo("Available color schemes:")
        for i, scheme in enumerate(schemes, 1):
            current = " (current)" if scheme == self.color_scheme else ""
            click.echo(f"  {i}. {scheme.title()}{current}")
        click.echo()

        choice = click.prompt(
            click.style(f"Choose a scheme (1-{len(schemes)})", fg='green'),
            type=click.IntRange(1, len(schemes)),
            default=schemes.index(self.color_scheme) + 1 if self.color_scheme in schemes else 1
        )

        self.color_scheme = schemes[choice - 1]

        # Save the color scheme preference
        self.settings.color_scheme = self.color_scheme

        click.echo()
        click.echo(click.style(f"  Color scheme changed to: {self.color_scheme.title()}", fg='green'))
        click.echo(click.style(f"  (Saved as default)", fg='cyan'))
        click.echo()

    def toggle_show_options(self):
        """Toggle the 'show move options' setting."""
        click.echo()
        click.echo(click.style("=" * 60, fg='cyan'))
        click.echo(click.style("  Show Move Options", fg='cyan', bold=True))
        click.echo(click.style("=" * 60, fg='cyan'))
        click.echo()
        click.echo("When enabled, flashcards will show multiple choice options.")
        click.echo("When disabled, only the board position will be shown.")
        click.echo()

        new_value = click.confirm(
            click.style("Show move options on flashcards?", fg='green'),
            default=self.settings.show_options
        )

        self.settings.show_options = new_value

        click.echo()
        click.echo(click.style(f"  Setting saved: {'Show options' if new_value else 'Hide options'}", fg='green'))
        click.echo()

    def change_antialiasing(self):
        """Allow user to change the antialiasing quality."""
        click.echo()
        click.echo(click.style("=" * 60, fg='cyan'))
        click.echo(click.style("  Antialiasing Quality", fg='cyan', bold=True))
        click.echo(click.style("=" * 60, fg='cyan'))
        click.echo()
        click.echo("Antialiasing smooths edges in board images for better quality.")
        click.echo("Higher values produce smoother images but take longer to render.")
        click.echo()
        click.echo("Quality levels:")
        current_mark = {1: " (current)", 2: " (current)", 3: " (current)", 4: " (current)"}.get(
            self.settings.antialias_scale, ""
        )
        click.echo(f"  1. Off (fastest){current_mark if self.settings.antialias_scale == 1 else ''}")
        click.echo(f"  2. 2x (good){current_mark if self.settings.antialias_scale == 2 else ''}")
        click.echo(f"  3. 3x (excellent - recommended){current_mark if self.settings.antialias_scale == 3 else ''}")
        click.echo(f"  4. 4x (maximum){current_mark if self.settings.antialias_scale == 4 else ''}")
        click.echo()

        choice = click.prompt(
            click.style("Choose quality level (1-4)", fg='green'),
            type=click.IntRange(1, 4),
            default=self.settings.antialias_scale
        )

        self.settings.antialias_scale = choice

        quality_names = {1: "Off", 2: "2x", 3: "3x", 4: "4x"}
        click.echo()
        click.echo(click.style(f"  Antialiasing set to: {quality_names[choice]}", fg='green'))
        click.echo(click.style(f"  (Saved as default)", fg='cyan'))
        click.echo()

    def show_help(self):
        """Show help information."""
        click.echo()
        click.echo(click.style("=" * 60, fg='cyan'))
        click.echo(click.style("  How to use XG2Anki", fg='cyan', bold=True))
        click.echo(click.style("=" * 60, fg='cyan'))
        click.echo()
        click.echo(click.style("Installing AnkiConnect:", fg='yellow', bold=True))
        click.echo("  1. In Anki, click Tools > Add-ons > Get Add-ons...")
        click.echo("  2. Enter Code: 2055492159")
        click.echo("  3. Restart Anki")
        click.echo()
        click.echo(click.style("Using XG2Anki:", fg='yellow', bold=True))
        click.echo("  1. In eXtreme Gammon (XG), analyze your positions")
        click.echo("  2. For each position, press Ctrl+C to copy the analysis")
        click.echo("  3. Come back to this tool and paste the entire position")
        click.echo("  4. The position should include:")
        click.echo("     - XGID line")
        click.echo("     - ASCII board diagram")
        click.echo("     - Move analysis with equities")
        click.echo()
        click.echo(click.style("Press Enter to continue...", fg='green'), nl=False)
        input()
        click.echo()

    def create_new_deck(self):
        """Create a new deck by collecting positions."""
        click.echo()
        click.echo(click.style("=" * 60, fg='cyan'))
        click.echo(click.style("  Create New Deck", fg='cyan', bold=True))
        click.echo(click.style("=" * 60, fg='cyan'))
        click.echo()

        # Get deck name
        click.echo(click.style("Note: Using an existing deck name will append cards to that deck.", fg='cyan'))
        click.echo()
        deck_name = click.prompt(
            click.style("Deck name", fg='green'),
            default=self.settings.deck_name,
            type=str
        )

        # Get output format
        click.echo()
        click.echo("Output format:")
        click.echo("  1. AnkiConnect (Push directly to Anki - recommended)")
        click.echo("  2. APKG (Import into Anki)")
        format_choice = click.prompt(
            click.style("Choose format", fg='green'),
            type=click.Choice(['1', '2']),
            default='1'
        )

        format_map = {'1': 'ankiconnect', '2': 'apkg'}
        output_format = format_map[format_choice]

        # Collect positions
        click.echo()
        click.echo(click.style("=" * 60, fg='yellow'))
        click.echo(click.style("  Position Collection", fg='yellow', bold=True))
        click.echo(click.style("=" * 60, fg='yellow'))
        click.echo()
        click.echo("Paste your XG positions below, one at a time.")
        click.echo("Each position should include the XGID, board, and move analysis.")
        click.echo()
        click.echo(click.style("Commands:", fg='cyan'))
        click.echo(click.style("  - Type 'done' when finished", fg='cyan'))
        click.echo(click.style("  - Type 'cancel' to abort", fg='cyan'))
        click.echo(click.style("  - Type 'show' to see collected positions", fg='cyan'))
        click.echo()

        positions = self.collect_positions()

        if not positions:
            click.echo(click.style("\nNo positions collected. Returning to menu.\n", fg='yellow'))
            return

        # Parse positions
        click.echo()
        click.echo(click.style("Processing positions...", fg='cyan'))

        try:
            # Combine all positions into one text block
            combined_text = "\n\n".join(positions)
            decisions = XGTextParser.parse_string(combined_text)

            if not decisions:
                click.echo(click.style("\nError: No valid positions found!", fg='red'))
                click.echo("Make sure each position includes:")
                click.echo("  - XGID line")
                click.echo("  - Move analysis with equities")
                return

            click.echo(click.style(f"  Parsed {len(decisions)} position(s) successfully!", fg='green'))

        except Exception as e:
            click.echo(click.style(f"\nError parsing positions: {e}", fg='red'))
            return

        # Export
        # Note: show_options is passed as-is, where True means show text options (image_choices=False)
        # The export functions will handle this correctly
        click.echo()
        self.export_deck(decisions, deck_name, output_format, self.settings.show_options, self.color_scheme)

    def collect_positions(self) -> List[str]:
        """
        Collect positions from user, one at a time.

        Returns:
            List of position text blocks
        """
        positions: List[str] = []
        current_position_lines: List[str] = []
        position_number = 1
        consecutive_empty_lines = 0
        pending_position_ready = False

        def trim_trailing_empty_lines(lines: List[str]) -> List[str]:
            trimmed = list(lines)
            while trimmed and not trimmed[-1].strip():
                trimmed.pop()
            return trimmed

        def looks_like_complete_position(lines: List[str]) -> bool:
            if not lines:
                return False
            text = "\n".join(trim_trailing_empty_lines(lines)).strip()
            # Check for XGID and either:
            # - Checker play: has 'eq:' in move lines
            # - Cube decision: has 'Cubeful Equities:' or 'Best Cube action:' or both 'Double' and 'Take'/'Pass'
            has_xgid = 'XGID=' in text
            has_checker_play = 'eq:' in text
            has_cube_decision = ('Cubeful Equities:' in text or
                               'Best Cube action:' in text or
                               ('Double' in text and ('Take' in text or 'Pass' in text or 'Drop' in text)))
            return has_xgid and (has_checker_play or has_cube_decision)

        def finalize_current_position(announce: bool = True) -> bool:
            nonlocal current_position_lines, consecutive_empty_lines, position_number
            nonlocal pending_position_ready

            trimmed_lines = trim_trailing_empty_lines(current_position_lines)
            if not trimmed_lines:
                return False

            positions.append('\n'.join(trimmed_lines))
            current_position_lines = []
            consecutive_empty_lines = 0
            position_number += 1
            pending_position_ready = False

            if announce:
                click.echo(click.style(f"\n  Position #{position_number - 1} saved!", fg='green'))
                click.echo()
                click.echo(click.style(f"Position #{position_number}:", fg='yellow', bold=True))
                click.echo(click.style("(Paste position or type 'done', 'show' or 'abort')", fg='cyan'))

            return True

        click.echo(click.style(f"Position #{position_number}:", fg='yellow', bold=True))
        click.echo(click.style("(Paste position to finish or type command)", fg='cyan'))

        while True:
            try:
                line = input()
            except EOFError:
                trimmed_remaining = trim_trailing_empty_lines(current_position_lines)
                if trimmed_remaining:
                    positions.append('\n'.join(trimmed_remaining))
                break

            stripped = line.strip()
            line_lower = stripped.lower()

            if pending_position_ready:
                if not stripped:
                    finalize_current_position()
                    continue
                if line_lower in {'done', 'cancel', 'show'} or line.startswith("XGID="):
                    finalize_current_position()
                else:
                    pending_position_ready = False
                    consecutive_empty_lines = 0

            if line_lower == 'done':
                if current_position_lines:
                    trimmed_lines = trim_trailing_empty_lines(current_position_lines)
                    if trimmed_lines:
                        positions.append('\n'.join(trimmed_lines))
                click.echo(click.style(f"\n  Collected {len(positions)} position(s)", fg='green', bold=True))
                break

            elif line_lower == 'cancel':
                if click.confirm(click.style("\n  Are you sure you want to cancel?", fg='yellow')):
                    return []
                click.echo()
                consecutive_empty_lines = 0
                pending_position_ready = False
                continue

            elif line_lower == 'show':
                self.show_collected_positions(positions, current_position_lines)
                consecutive_empty_lines = 0
                pending_position_ready = False
                continue

            # If a new position starts without separating command, finalize previous
            if line.startswith("XGID=") and current_position_lines and looks_like_complete_position(current_position_lines):
                finalize_current_position()

            if not stripped:
                consecutive_empty_lines += 1
                current_position_lines.append('')
                if consecutive_empty_lines >= 2 and looks_like_complete_position(current_position_lines):
                    pending_position_ready = True
                continue

            consecutive_empty_lines = 0
            current_position_lines.append(line)
            if 'eXtreme Gammon Version' in line and looks_like_complete_position(current_position_lines):
                finalize_current_position()
                continue

        return positions

    def show_collected_positions(self, positions: List[str], current_buffer: List[str]):
        """Show summary of collected positions."""
        click.echo()
        click.echo(click.style("=" * 60, fg='cyan'))
        click.echo(click.style(f"  Collected Positions: {len(positions)}", fg='cyan', bold=True))
        click.echo(click.style("=" * 60, fg='cyan'))

        for i, pos in enumerate(positions, 1):
            # Extract XGID for summary
            xgid_match = None
            for line in pos.split('\n'):
                if 'XGID=' in line:
                    xgid_match = line[:60] + '...' if len(line) > 60 else line
                    break

            click.echo(f"{i}. {xgid_match or '[Position]'}")

        if current_buffer:
            click.echo(click.style(f"\nCurrent (unsaved): {len(current_buffer)} lines", fg='yellow'))

        click.echo(click.style("=" * 60, fg='cyan'))
        click.echo()

    def export_deck(self, decisions: List[Decision], deck_name: str,
                   output_format: str, show_options: bool, color_scheme: str = "classic"):
        """Export the deck using the specified format."""
        # Import here to avoid circular imports
        from xg2anki.cli import export_apkg, export_ankiconnect

        output_dir = Path.cwd() / "xg2anki_output"
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            click.echo(click.style("Generating deck...", fg='cyan'))

            if output_format == 'apkg':
                export_apkg(decisions, output_dir, deck_name, show_options, color_scheme)
            elif output_format == 'ankiconnect':
                export_ankiconnect(decisions, output_dir, deck_name, show_options, color_scheme)

            click.echo()
            click.echo(click.style("=" * 60, fg='green'))
            click.echo(click.style("  Success! Deck created.", fg='green', bold=True))
            click.echo(click.style("=" * 60, fg='green'))
            click.echo()

            click.echo(click.style("Press Enter to return to main menu...", fg='green'), nl=False)
            input()
            click.echo()

        except Exception as e:
            click.echo()
            click.echo(click.style(f"Error creating deck: {e}", fg='red'))
            click.echo()
            click.echo(click.style("Press Enter to continue...", fg='yellow'), nl=False)
            input()


def run_interactive():
    """Run the interactive CLI session."""
    session = InteractiveSession()
    session.run()
