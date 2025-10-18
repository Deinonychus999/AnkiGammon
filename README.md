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

## Installation

### Option 1: Standalone Executable (Recommended)

1. Run `build_executable.bat` to create `xg2anki.exe`
2. Double-click to run - no Python installation needed!

### Option 2: Development Install

```bash
git clone https://github.com/yourusername/xg2anki.git
cd xg2anki
pip install -r requirements.txt
python -m xg2anki
```

## Quick Start

### Interactive Mode (Easiest)
```bash
xg2anki
```
Then paste XG positions when prompted.

### File-Based Mode
```bash
# Push directly to Anki (requires AnkiConnect addon)
xg2anki analysis.txt

# Or generate APKG file
xg2anki analysis.txt --format apkg
```

## Getting Positions from XG

1. In eXtreme Gammon, analyze a position
2. Press Ctrl+C to copy the analysis
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
- Copy the full position from XG (press Ctrl+C)

## For Developers

### Building the Executable

**Quick Build:**

```bash
build_executable.bat
```

The executable will be in the `dist/` folder.

**Manual Build (if script doesn't work):**
```bash
# Install PyInstaller
pip install pyinstaller

# Clean previous builds
rm -rf build dist

# Build
pyinstaller xg2anki.spec
```

### Testing Builds

Before distributing:

```bash
# Test the executable works
cd dist
./xg2anki --help

# Test interactive mode
./xg2anki

# Test with a sample file
./xg2anki ../examples/example_xg_export.txt
```

### Project Structure

- `xg2anki/` - Main package code
  - `parsers/` - XG text format parsers
  - `renderer/` - Board image generation
  - `anki/` - Anki card generation and export
  - `utils/` - XGID encoding/decoding
- `tests/` - Unit tests
- `xg2anki.spec` - PyInstaller configuration
- `build_executable.bat/.sh` - Build scripts

### Settings Storage

User preferences (color scheme, deck name, etc.) are stored in:
- `C:\Users\YourName\.xg2anki\config.json`

This ensures settings persist even when using the standalone executable.

### Troubleshooting Build Issues

**ImportError during build:**
- Add missing module to `hiddenimports` in `xg2anki.spec`

**"Module not found" when running executable:**
- Check the module is in `hiddenimports`
- Try: `pyinstaller --collect-all xg2anki xg2anki.spec`

**Executable too large:**
- Remove unused dependencies from requirements.txt
- Add more items to `excludes` in xg2anki.spec

**Executable won't run:**
- Test on clean machine without Python installed
- Check Windows Defender / antivirus isn't blocking it
- Look at build warnings: `pyinstaller xg2anki.spec > build.log 2>&1`

**Security Note:**
- Some antivirus software may flag PyInstaller executables as suspicious (false positive)
- This is common with PyInstaller - nothing to worry about
- Users may need to add an exception in their antivirus
- To reduce false positives:
  1. Sign your executable (Windows: with a code signing certificate)
  2. Build on clean systems
  3. Upload to VirusTotal to show it's clean

## Requirements

- Python 3.8+ (for development/pip install)
- Dependencies: genanki, Pillow, click, requests, beautifulsoup4, lxml, numpy
- For standalone executable: No requirements, Python is bundled

## License

MIT
