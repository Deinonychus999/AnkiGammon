"""Command-line interface for XG2Anki."""

import click
import sys
from pathlib import Path

from xg2anki.parsers.xg_text_parser import XGTextParser
from xg2anki.anki.apkg_exporter import ApkgExporter
from xg2anki.anki.ankiconnect import AnkiConnect
from xg2anki.settings import get_settings


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
    help='Input file format (default: auto-detect)'
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
    '--interactive',
    '-i',
    is_flag=True,
    help='Run in interactive mode (default when no input file provided)'
)
def main(input_file, format, output, deck_name, show_options, input_format, color_scheme, interactive_moves, interactive):
    """
    Convert eXtreme Gammon (XG) positions/analysis into Anki flashcards.

    Run without arguments for interactive mode, or provide an INPUT_FILE for batch processing.

    INPUT_FILE should be:
    - XG text export (with ASCII board and rollout data)

    Examples:

        \b
        # Interactive mode (user-friendly)
        xg2anki

        \b
        # Push directly to Anki (default - requires Anki-Connect)
        xg2anki analysis.json

        \b
        # Generate APKG file instead
        xg2anki analysis.json --format apkg
    """
    # Launch interactive mode if no input file provided
    if not input_file or interactive:
        from xg2anki.interactive import run_interactive
        run_interactive()
        return

    click.echo(f"XG2Anki - Converting backgammon analysis to Anki flashcards...")
    click.echo()

    # Parse input
    try:
        decisions = parse_input(input_file, input_format)
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


def parse_input(input_file: str, input_format: str):
    """Parse input file and return list of decisions."""
    input_path = Path(input_file)

    # Always use XGTextParser (format detection happens within parser)
    click.echo(f"Reading input (XG text format)...")
    return XGTextParser.parse_file(str(input_path))


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
