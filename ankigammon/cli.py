"""Command-line interface for AnkiGammon."""

import click
import sys
from pathlib import Path

from ankigammon.parsers.xg_text_parser import XGTextParser
from ankigammon.anki.apkg_exporter import ApkgExporter
from ankigammon.anki.ankiconnect import AnkiConnect
from ankigammon.settings import get_settings


@click.command()
@click.argument('input_file', type=click.Path(exists=True), required=False)
@click.option(
    '--format',
    type=click.Choice(['ankiconnect', 'apkg'], case_sensitive=False),
    default='ankiconnect',
    help='Output format (default: ankiconnect - recommended)'
)
@click.option(
    '--output',
    '-o',
    type=click.Path(),
    help='Output file/directory path (default: auto-generated)'
)
@click.option(
    '--deck-name',
    default='XG Backgammon',
    help='Anki deck name (default: XG Backgammon)'
)
@click.option(
    '--show-options',
    is_flag=True,
    help='Show multiple choice options (text-based) on the card front'
)
@click.option(
    '--input-format',
    type=click.Choice(['auto', 'xgtext'], case_sensitive=False),
    default='auto',
    help='Input file format (default: auto-detect). Supports XGID, OGID, and GNUID position formats.'
)
@click.option(
    '--color-scheme',
    type=click.Choice(['classic', 'forest', 'ocean', 'desert', 'sunset', 'midnight'], case_sensitive=False),
    default=None,
    help='Board color scheme (default: saved preference or classic)'
)
@click.option(
    '--interactive-moves',
    is_flag=True,
    help='Enable interactive move visualization (clickable moves in analysis table)'
)
@click.option(
    '--gnubg-path',
    type=click.Path(),
    default=None,
    help='Path to gnubg-cli.exe (overrides saved preference)'
)
@click.option(
    '--gnubg-ply',
    type=int,
    default=None,
    help='GnuBG analysis depth in plies (default: 2)'
)
@click.option(
    '--use-gnubg',
    is_flag=True,
    help='Use GnuBG to analyze positions without XG analysis'
)
@click.option(
    '--interactive',
    '-i',
    is_flag=True,
    help='Run in interactive mode (default when no input file provided)'
)
@click.option(
    '--gui',
    '-g',
    is_flag=True,
    help='Launch graphical user interface (GUI mode)'
)
def main(input_file, format, output, deck_name, show_options, input_format, color_scheme, interactive_moves, gnubg_path, gnubg_ply, use_gnubg, interactive, gui):
    """
    Convert backgammon positions/analysis into Anki flashcards.

    Run without arguments for interactive mode, or provide an INPUT_FILE for batch processing.

    INPUT_FILE can contain:
    - XG text export (with ASCII board and rollout data)
    - Position IDs only: XGID, OGID, or GNUID formats (auto-detected)
    - Mixed content (different formats in the same file)

    Examples:

        \b
        # Interactive mode (user-friendly)
        ankigammon

        \b
        # Push directly to Anki (default - requires Anki-Connect)
        ankigammon analysis.txt

        \b
        # Generate APKG file instead
        ankigammon analysis.txt --format apkg

        \b
        # Use GnuBG to analyze position IDs without full analysis
        ankigammon positions.txt --use-gnubg
    """
    # Launch GUI mode if requested
    if gui:
        from ankigammon.gui import run_gui
        sys.exit(run_gui())

    # Launch interactive mode if no input file provided
    if not input_file or interactive:
        from ankigammon.interactive import run_interactive
        run_interactive()
        return

    click.echo(f"AnkiGammon - Converting backgammon analysis to Anki flashcards...")
    click.echo()

    # Apply gnubg settings from CLI if provided
    settings = get_settings()
    if gnubg_path:
        settings.gnubg_path = gnubg_path
    if gnubg_ply:
        settings.gnubg_analysis_ply = gnubg_ply

    # Parse input
    try:
        decisions = parse_input(input_file, input_format, use_gnubg, settings)
        if not decisions:
            click.echo("Error: No decisions found in input file", err=True)
            sys.exit(1)

        click.echo(f"Parsed {len(decisions)} decision(s)")

    except Exception as e:
        click.echo(f"Error parsing input: {e}", err=True)
        sys.exit(1)

    # Determine output path
    input_path = Path(input_file)
    if not output:
        output_dir = input_path.parent / f"{input_path.stem}_output"
    else:
        output_dir = Path(output)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Get color scheme (use CLI argument, fallback to saved preference, then to "classic")
    if color_scheme is None:
        settings = get_settings()
        color_scheme = settings.color_scheme

    # Export based on format
    try:
        if format == 'apkg':
            export_apkg(decisions, output_dir, deck_name, show_options, color_scheme, interactive_moves)

        elif format == 'ankiconnect':
            export_ankiconnect(decisions, output_dir, deck_name, show_options, color_scheme, interactive_moves)

    except Exception as e:
        click.echo(f"Error during export: {e}", err=True)
        sys.exit(1)

    click.echo()
    click.echo("Done!")


def parse_input(input_file: str, input_format: str, use_gnubg: bool = False, settings=None):
    """Parse input file and return list of decisions."""
    from ankigammon.settings import get_settings

    if settings is None:
        settings = get_settings()

    input_path = Path(input_file)

    # Always use XGTextParser (format detection happens within parser)
    click.echo(f"Reading input (XG text format)...")
    decisions = XGTextParser.parse_file(str(input_path))

    # If gnubg is enabled, enrich positions without analysis
    if use_gnubg and settings.is_gnubg_available():
        decisions = _enrich_with_gnubg_analysis(decisions, settings)
    elif use_gnubg and not settings.is_gnubg_available():
        click.echo(click.style("Warning: --use-gnubg specified but GnuBG not configured or not found", fg='yellow'))
        click.echo(click.style("  Use --gnubg-path to specify path or configure in interactive mode", fg='yellow'))

    return decisions


def _enrich_with_gnubg_analysis(decisions, settings):
    """
    For decisions without moves, use gnubg to generate analysis.

    Detects XGID-only positions by checking:
    - decision.candidate_moves is empty or None
    - decision.xgid is present
    """
    from ankigammon.utils.gnubg_analyzer import GNUBGAnalyzer
    from ankigammon.parsers.gnubg_parser import GNUBGParser

    enriched_decisions = []
    positions_analyzed = 0

    for decision in decisions:
        # Check if decision needs analysis
        if (not decision.candidate_moves or len(decision.candidate_moves) == 0) and decision.xgid:
            try:
                click.echo(f"  Analyzing position with GnuBG ({settings.gnubg_analysis_ply}-ply)...")

                # Create analyzer
                analyzer = GNUBGAnalyzer(
                    gnubg_path=settings.gnubg_path,
                    analysis_ply=settings.gnubg_analysis_ply
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

            except Exception as e:
                click.echo(click.style(f"  Warning: Failed to analyze position with GnuBG: {e}", fg='yellow'))
                # Keep original decision without analysis
                enriched_decisions.append(decision)
        else:
            # Decision already has analysis
            enriched_decisions.append(decision)

    if positions_analyzed > 0:
        click.echo(click.style(f"  GnuBG analyzed {positions_analyzed} position(s)", fg='green'))

    return enriched_decisions


def export_apkg(decisions, output_dir, deck_name, show_options, color_scheme="classic", interactive_moves=False):
    """Export to APKG format."""
    click.echo(f"Generating APKG file...")
    click.echo(f"  Deck name: {deck_name}")
    click.echo(f"  Show options: {'Yes' if show_options else 'No'}")
    click.echo(f"  Color scheme: {color_scheme}")
    click.echo(f"  Interactive moves: {'Yes' if interactive_moves else 'No'}")

    exporter = ApkgExporter(output_dir, deck_name)
    output_file = exporter.export(
        decisions,
        output_file="xg_deck.apkg",
        show_options=show_options,
        color_scheme=color_scheme,
        interactive_moves=interactive_moves
    )

    click.echo()
    click.echo(f"APKG file created: {output_file}")
    click.echo()
    click.echo("Import into Anki:")
    click.echo(f"  1. Open Anki")
    click.echo(f"  2. File > Import")
    click.echo(f"  3. Select: {output_file}")


def export_ankiconnect(decisions, output_dir, deck_name, show_options, color_scheme="classic", interactive_moves=False):
    """Export via Anki-Connect."""
    click.echo(f"Connecting to Anki...")
    click.echo(f"  Deck name: {deck_name}")
    click.echo(f"  Show options: {'Yes' if show_options else 'No'}")
    click.echo(f"  Color scheme: {color_scheme}")
    click.echo(f"  Interactive moves: {'Yes' if interactive_moves else 'No'}")

    client = AnkiConnect(deck_name=deck_name)

    # Test connection with detailed error reporting
    try:
        if not client.test_connection():
            click.echo()
            click.echo(click.style("Error: Cannot connect to Anki-Connect", fg='red'), err=True)
            click.echo()
            click.echo("Make sure:")
            click.echo("  1. Anki is running")
            click.echo("  2. Anki-Connect addon is installed")
            click.echo("     (https://ankiweb.net/shared/info/2055492159)")
            click.echo("  3. AnkiConnect is configured to allow connections")
            click.echo()
            click.echo("Troubleshooting:")
            click.echo("  - Restart Anki after installing AnkiConnect")
            click.echo("  - Check Tools > Add-ons to verify AnkiConnect is enabled")
            click.echo("  - Try testing the connection: http://localhost:8765")
            sys.exit(1)
    except Exception as e:
        click.echo()
        click.echo(click.style(f"Error: {str(e)}", fg='red'), err=True)
        click.echo()
        click.echo("Troubleshooting:")
        click.echo("  - Restart Anki after installing AnkiConnect")
        click.echo("  - Check Tools > Add-ons to verify AnkiConnect is enabled")
        click.echo("  - Try accessing http://localhost:8765 in a browser")
        sys.exit(1)

    click.echo(click.style("Connected to Anki", fg='green'))
    click.echo()
    click.echo("Adding notes to Anki...")

    # Export
    results = client.export_decisions(
        decisions,
        output_dir=output_dir,
        show_options=show_options,
        color_scheme=color_scheme,
        interactive_moves=interactive_moves
    )

    click.echo()
    click.echo(f"Added: {results['added']} notes")
    if results['skipped'] > 0:
        click.echo(f"  Skipped: {results['skipped']} (duplicates)")
    if results['errors']:
        click.echo(f"  Errors: {len(results['errors'])}")
        for error in results['errors'][:5]:  # Show first 5 errors
            click.echo(f"    - {error}")
        # Raise exception if all cards failed
        if results['added'] == 0 and len(results['errors']) > 0:
            raise Exception(f"Failed to add any cards. Errors: {results['errors'][0]}")


if __name__ == '__main__':
    main()
