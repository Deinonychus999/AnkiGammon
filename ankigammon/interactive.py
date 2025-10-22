"""Interactive CLI mode for AnkiGammon - user-friendly position collection."""

import sys
from pathlib import Path
from typing import List, Optional

import click

from ankigammon.parsers.xg_text_parser import XGTextParser
from ankigammon.models import Decision
from ankigammon.settings import get_settings


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
        click.echo(click.style("  AnkiGammon - Backgammon Analysis to Anki Flashcards", fg='cyan', bold=True))
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
            click.echo(f"  3. Interactive moves (current: {'Yes' if self.settings.interactive_moves else 'No'})")
            export_display = "AnkiConnect" if self.settings.export_method == "ankiconnect" else "APKG"
            click.echo(f"  4. Export method (current: {export_display})")
            gnubg_status = "Configured" if self.settings.gnubg_path else "Not configured"
            click.echo(f"  5. Configure GnuBG path (current: {gnubg_status})")
            matrix_status = "Yes" if self.settings.generate_score_matrix else "No"
            click.echo(f"  6. Generate score matrix (current: {matrix_status})")
            click.echo("  7. Back to main menu")
            click.echo()

            choice = click.prompt(
                click.style("Choose an option", fg='green'),
                type=str,
                default='7'
            )

            if choice == '1':
                self.change_color_scheme()
            elif choice == '2':
                self.toggle_show_options()
            elif choice == '3':
                self.toggle_interactive_moves()
            elif choice == '4':
                self.change_export_method()
            elif choice == '5':
                self.configure_gnubg_path()
            elif choice == '6':
                self.toggle_score_matrix()
            elif choice == '7':
                break
            else:
                click.echo(click.style("\n  Invalid choice. Please try again.\n", fg='red'))

    def change_color_scheme(self):
        """Allow user to change the board color scheme."""
        from ankigammon.renderer.color_schemes import list_schemes

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

    def toggle_interactive_moves(self):
        """Toggle the 'interactive moves' setting."""
        click.echo()
        click.echo(click.style("=" * 60, fg='cyan'))
        click.echo(click.style("  Interactive Move Visualization", fg='cyan', bold=True))
        click.echo(click.style("=" * 60, fg='cyan'))
        click.echo()
        click.echo("When enabled, card backs will include clickable move visualization:")
        click.echo("  - Click any move in the analysis table to see the resulting position")
        click.echo("  - Smooth animated transitions between positions")
        click.echo("  - Toggle between original and resulting positions")
        click.echo()
        click.echo(click.style("Note:", fg='yellow'), nl=False)
        click.echo(" This generates additional SVG boards (5x more per card).")
        click.echo()

        new_value = click.confirm(
            click.style("Enable interactive move visualization?", fg='green'),
            default=self.settings.interactive_moves
        )

        self.settings.interactive_moves = new_value

        click.echo()
        click.echo(click.style(f"  Setting saved: {'Interactive moves enabled' if new_value else 'Interactive moves disabled'}", fg='green'))
        click.echo()
        click.echo(click.style(f"  (Saved as default)", fg='cyan'))
        click.echo()

    def change_export_method(self):
        """Allow user to change the export method."""
        click.echo()
        click.echo(click.style("=" * 60, fg='cyan'))
        click.echo(click.style("  Export Method", fg='cyan', bold=True))
        click.echo(click.style("=" * 60, fg='cyan'))
        click.echo()
        click.echo("Choose how cards are exported to Anki:")
        click.echo()
        click.echo("  1. AnkiConnect - Push directly to Anki (recommended)")
        click.echo("     Requires AnkiConnect add-on (code: 2055492159)")
        click.echo("     Cards appear immediately in the running Anki application")
        click.echo()
        click.echo("  2. APKG - Generate .apkg file for manual import")
        click.echo("     Creates a file you can import into Anki later")
        click.echo("     Useful when Anki is not running or AnkiConnect is unavailable")
        click.echo()

        current_choice = '1' if self.settings.export_method == 'ankiconnect' else '2'
        choice = click.prompt(
            click.style("Choose export method", fg='green'),
            type=click.Choice(['1', '2']),
            default=current_choice
        )

        format_map = {'1': 'ankiconnect', '2': 'apkg'}
        new_method = format_map[choice]
        self.settings.export_method = new_method

        display_name = "AnkiConnect" if new_method == "ankiconnect" else "APKG"
        click.echo()
        click.echo(click.style(f"  Export method changed to: {display_name}", fg='green'))
        click.echo(click.style(f"  (Saved as default)", fg='cyan'))
        click.echo()

    def configure_gnubg_path(self):
        """Allow user to configure GnuBG executable path."""
        from pathlib import Path

        click.echo()
        click.echo(click.style("=" * 60, fg='cyan'))
        click.echo(click.style("  GnuBG Configuration", fg='cyan', bold=True))
        click.echo(click.style("=" * 60, fg='cyan'))
        click.echo()
        click.echo("GnuBG enables analysis of positions when you only have position IDs")
        click.echo("(XGID, OGID, or GNUID) without full XG analysis text.")
        click.echo()

        if self.settings.gnubg_path:
            click.echo(f"Current path: {self.settings.gnubg_path}")
            if self.settings.is_gnubg_available():
                click.echo(click.style("  Status: Available", fg='green'))
            else:
                click.echo(click.style("  Status: Path not found or not executable", fg='yellow'))
        else:
            click.echo("Not currently configured (optional)")

        click.echo()
        click.echo("Enter the path to gnubg-cli.exe (or gnubg on macOS/Linux)")
        click.echo("Leave blank to clear/skip configuration")
        click.echo()

        path_input = click.prompt(
            click.style("GnuBG path", fg='green'),
            default=self.settings.gnubg_path or "",
            type=str,
            show_default=False
        )

        if path_input:
            path_obj = Path(path_input)
            if path_obj.exists():
                self.settings.gnubg_path = str(path_obj.absolute())
                click.echo()
                click.echo(click.style("  GnuBG path saved!", fg='green'))
                click.echo(click.style(f"  (Saved as default)", fg='cyan'))
            else:
                click.echo()
                click.echo(click.style(f"  Warning: Path not found: {path_input}", fg='yellow'))
                click.echo(click.style(f"  Path saved anyway (you can fix it later)", fg='cyan'))
                self.settings.gnubg_path = path_input
        else:
            self.settings.gnubg_path = None
            click.echo()
            click.echo(click.style("  GnuBG path cleared", fg='cyan'))

        click.echo()

    def toggle_score_matrix(self):
        """Toggle the 'generate score matrix' setting."""
        click.echo()
        click.echo(click.style("=" * 60, fg='cyan'))
        click.echo(click.style("  Score Matrix Generation", fg='cyan', bold=True))
        click.echo(click.style("=" * 60, fg='cyan'))
        click.echo()
        click.echo("When enabled, cube decision cards will include a score matrix showing")
        click.echo("optimal cube actions at all possible match scores.")
        click.echo()
        click.echo("For example, in a 7-point match:")
        click.echo("  - Matrix shows cube actions for 2a-2a through 7a-7a")
        click.echo("  - Each cell shows best action (D/T, N/T, D/P) and error values")
        click.echo("  - Current match score is highlighted")
        click.echo()
        click.echo(click.style("Note:", fg='yellow'), nl=False)
        click.echo(" Requires GnuBG to be configured (Option 5).")
        click.echo(click.style("Note:", fg='yellow'), nl=False)
        click.echo(" Matrix generation uses GnuBG analysis for each score combination.")
        click.echo("      This may increase card generation time significantly.")
        click.echo()

        if not self.settings.is_gnubg_available():
            click.echo(click.style("  Warning: GnuBG is not configured!", fg='red'))
            click.echo(click.style("  Please configure GnuBG path first (Option 5)", fg='yellow'))
            click.echo()

        new_value = click.confirm(
            click.style("Generate score matrix for cube decisions?", fg='green'),
            default=self.settings.generate_score_matrix
        )

        self.settings.generate_score_matrix = new_value

        click.echo()
        click.echo(click.style(f"  Setting saved: {'Matrix generation enabled' if new_value else 'Matrix generation disabled'}", fg='green'))
        click.echo(click.style(f"  (Saved as default)", fg='cyan'))
        click.echo()

    def show_help(self):
        """Show help information."""
        click.echo()
        click.echo(click.style("=" * 60, fg='cyan'))
        click.echo(click.style("  How to use AnkiGammon", fg='cyan', bold=True))
        click.echo(click.style("=" * 60, fg='cyan'))
        click.echo()
        click.echo(click.style("Installing AnkiConnect:", fg='yellow', bold=True))
        click.echo("  1. In Anki, click Tools > Add-ons > Get Add-ons...")
        click.echo("  2. Enter Code: 2055492159")
        click.echo("  3. Restart Anki")
        click.echo()
        click.echo(click.style("Using AnkiGammon:", fg='yellow', bold=True))
        click.echo("  1. In eXtreme Gammon (XG), analyze your positions")
        click.echo("  2. For each position, press Ctrl+C to copy the analysis")
        click.echo("  3. Come back to this tool and paste the entire position")
        click.echo("  4. The position should include:")
        click.echo("     - Position ID (XGID, OGID, or GNUID format)")
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

        # Use saved export method setting
        output_format = self.settings.export_method
        export_display = "AnkiConnect" if output_format == "ankiconnect" else "APKG"
        click.echo()
        click.echo(click.style(f"Export method: {export_display}", fg='cyan'))
        click.echo(click.style("(Change in Options menu if needed)", fg='cyan', dim=True))

        # Collect positions
        click.echo()
        click.echo(click.style("=" * 60, fg='yellow'))
        click.echo(click.style("  Position Collection", fg='yellow', bold=True))
        click.echo(click.style("=" * 60, fg='yellow'))
        click.echo()
        click.echo("Paste your positions below, one at a time.")
        click.echo("Supports XGID, OGID, and GNUID formats (auto-detected).")
        click.echo("Each position should include the position ID, board, and move analysis.")
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
                click.echo("  - Position ID (XGID, OGID, or GNUID format)")
                click.echo("  - Move analysis with equities")
                return

            click.echo(click.style(f"  Parsed {len(decisions)} position(s) successfully!", fg='green'))

        except Exception as e:
            click.echo(click.style(f"\nError parsing positions: {e}", fg='red'))
            return

        # Enrich positions with GnuBG analysis if available and needed
        if self.settings.is_gnubg_available():
            decisions = self._enrich_with_gnubg(decisions)

        # Export
        # Note: show_options is passed as-is, where True means show text options (image_choices=False)
        # The export functions will handle this correctly
        click.echo()
        self.export_deck(
            decisions,
            deck_name,
            output_format,
            self.settings.show_options,
            self.color_scheme,
            self.settings.interactive_moves
        )

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

            # Check for XGID
            has_xgid = 'XGID=' in text

            # Check for GNUID format (base64 pattern with colon separator)
            import re
            has_gnuid = bool(re.match(r'^[A-Za-z0-9+/=]+:[A-Za-z0-9+/=]+$', text.strip()))

            # Check for analysis text
            has_checker_play = 'eq:' in text or 'Eq:' in text
            has_cube_decision = ('Cubeful Equities:' in text or
                               'cubeful equities:' in text or
                               'Best Cube action:' in text or
                               'Proper cube action:' in text or
                               ('Double' in text and ('Take' in text or 'Pass' in text or 'Drop' in text)))

            # With gnubg configured, XGID-only or GNUID-only is complete
            if self.settings.is_gnubg_available():
                if has_xgid or has_gnuid:
                    return True

            # Standard: need XGID + analysis
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
                   output_format: str, show_options: bool, color_scheme: str = "classic",
                   interactive_moves: bool = False):
        """Export the deck using the specified format."""
        # Import here to avoid circular imports
        from ankigammon.cli import export_apkg, export_ankiconnect

        output_dir = Path.cwd() / "ankigammon_output"
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            click.echo(click.style("Generating deck...", fg='cyan'))

            if output_format == 'apkg':
                export_apkg(decisions, output_dir, deck_name, show_options, color_scheme, interactive_moves)
            elif output_format == 'ankiconnect':
                export_ankiconnect(decisions, output_dir, deck_name, show_options, color_scheme, interactive_moves)

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

    def _enrich_with_gnubg(self, decisions: List[Decision]) -> List[Decision]:
        """
        Enrich decisions with GnuBG analysis if they lack candidate moves.

        Args:
            decisions: List of Decision objects to enrich

        Returns:
            List of Decision objects with GnuBG analysis added where needed
        """
        from ankigammon.utils.gnubg_analyzer import GNUBGAnalyzer
        from ankigammon.parsers.gnubg_parser import GNUBGParser

        enriched_decisions = []
        positions_analyzed = 0

        for decision in decisions:
            # Check if decision needs analysis
            if (not decision.candidate_moves or len(decision.candidate_moves) == 0) and decision.xgid:
                try:
                    if positions_analyzed == 0:
                        click.echo()
                        click.echo(click.style(f"Analyzing positions with GnuBG ({self.settings.gnubg_analysis_ply}-ply)...", fg='cyan'))

                    # Create analyzer
                    analyzer = GNUBGAnalyzer(
                        gnubg_path=self.settings.gnubg_path,
                        analysis_ply=self.settings.gnubg_analysis_ply
                    )

                    # Analyze position
                    gnubg_output, decision_type = analyzer.analyze_position(decision.xgid)

                    # Parse gnubg output
                    enriched_decision = GNUBGParser.parse_analysis(
                        gnubg_output,
                        decision.xgid,
                        decision_type
                    )

                    enriched_decisions.append(enriched_decision)
                    positions_analyzed += 1
                    click.echo(click.style(f"  Position {positions_analyzed} analyzed", fg='green'))

                except Exception as e:
                    click.echo(click.style(f"  Warning: Failed to analyze position: {e}", fg='yellow'))
                    # Keep original decision without analysis
                    enriched_decisions.append(decision)
            else:
                # Decision already has analysis
                enriched_decisions.append(decision)

        if positions_analyzed > 0:
            click.echo(click.style(f"  Total analyzed: {positions_analyzed} position(s)", fg='green'))

        return enriched_decisions


def run_interactive():
    """Run the interactive CLI session."""
    session = InteractiveSession()
    session.run()
