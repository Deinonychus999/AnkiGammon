# XG2Anki

Convert eXtreme Gammon (XG) backgammon analysis into Anki flashcards for effective study.

## Features

- **Direct XG export support** - Copy/paste positions from eXtreme Gammon
- **Smart rendering** - Automatic board image generation from XGID
- **Two output formats**:
  - AnkiConnect: Push directly to Anki (default, recommended)
  - APKG: Self-contained package for manual import
- **Interactive mode** - Paste positions directly, no file management needed
- **Complete analysis** - Top 5 moves with equities and error calculations

## Quick Start

### Install
```bash
pip install -r requirements.txt
```

### Interactive Mode (Easiest)
```bash
python -m xg2anki
```
Then paste XG positions when prompted.

### File-Based Mode
```bash
# Push directly to Anki (requires AnkiConnect addon)
python -m xg2anki analysis.txt

# Or generate APKG file
python -m xg2anki analysis.txt --format apkg
```

## Getting Positions from XG

1. In eXtreme Gammon, analyze a position
2. Edit > Copy Position (or Ctrl+C)
3. Paste into a text file or interactive mode
4. Run xg2anki

**Example XG export format:**
```
XGID=---BBBBAAA---Ac-bbccbAA-A-:1:1:-1:63:4:3:0:5:8

X:Player 2   O:Player 1
Score is X:3 O:4 5 pt.(s) match.
 +13-14-15-16-17-18------19-20-21-22-23-24-+
 |          O  O  O |   | O  O  O  O       |
 ...

    1. XG Roller+  11/8 11/5                    eq:+0.589
      Player:   79.46% (G:17.05% B:0.67%)
      Opponent: 20.54% (G:2.22% B:0.06%)
```

## Output Formats

### AnkiConnect (Default - Recommended)

Push cards directly to running Anki:
```bash
python -m xg2anki analysis.txt
```

**Prerequisites:**
- Install [AnkiConnect addon](https://ankiweb.net/shared/info/2055492159)
- Anki must be running

**Advantages:**
- No manual import
- Automatic duplicate detection
- Instant feedback

### APKG

Generate a package file for manual import:
```bash
python -m xg2anki analysis.txt --format apkg
```

Import into Anki: File → Import → Select the .apkg file

## Command-Line Options

```
Usage: xg2anki [OPTIONS] [INPUT_FILE]

Options:
  --format [ankiconnect|apkg]   Output format (default: ankiconnect)
  -o, --output PATH             Output directory
  --deck-name TEXT              Anki deck name (default: XG Backgammon)
  --show-options                Show text move options on card front
  -i, --interactive             Run in interactive mode
  --help                        Show help message
```

## Card Format

Each XG position becomes one Anki card:

**Front:**
- Board image showing the position
- Metadata: player on roll, dice, score, cube, match length
- Multiple choice: 5 candidate moves (labeled A-E, shuffled)

**Back:**
- Position image and metadata
- Ranked table of top 5 moves with equity and error
- Correct answer highlighted
- Source XGID for reference

## Examples

```bash
# Interactive mode
python -m xg2anki

# Push to Anki (default)
python -m xg2anki positions.txt

# Generate APKG file
python -m xg2anki positions.txt --format apkg

# Custom deck name
python -m xg2anki positions.txt --deck-name "Opening Plays"

# Show text options on front
python -m xg2anki positions.txt --show-options
```

## Troubleshooting

**"Cannot connect to Anki-Connect"**
- Install AnkiConnect addon: https://ankiweb.net/shared/info/2055492159
- Make sure Anki is running
- Check firewall isn't blocking localhost:8765

**"No decisions found in input file"**
- Ensure file includes XGID lines
- Make sure move analysis includes equity values (eq:)
- Copy the full position from XG (Edit > Copy Position)

## Requirements

- Python 3.8+
- Dependencies: genanki, Pillow, click, requests

## License

MIT
