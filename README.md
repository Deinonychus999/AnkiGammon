# AnkiGammon

Convert eXtreme Gammon (XG) backgammon analysis into Anki flashcards for effective study.

## Features

- **Multiple position format support** - XGID (eXtreme Gammon), OGID (OpenGammon), and GNUID (GNU Backgammon)
- **Direct XG export support** - Copy/paste positions from eXtreme Gammon
- **Smart rendering** - Automatic board image generation from position IDs
- **Automatic format detection** - Paste any supported format, the app detects it automatically
- **Two output formats**:
  - AnkiConnect: Push directly to Anki (default, recommended)
  - APKG: Self-contained package for manual import
- **Interactive mode** - Paste positions directly, no file management needed
- **Complete analysis** - Top 5 moves with equities and error calculations

## Installation

### Option 1: Standalone Executable (Recommended)

**Windows:**
1. Run `build_executable.bat` to create `ankigammon.exe`
2. Double-click to run - no Python installation needed!

**macOS/Linux:**
1. Run `./build_executable.sh` to create `ankigammon`
2. Run from terminal: `./dist/ankigammon` - no Python installation needed!
3. macOS first run: Right-click → Open (or allow in System Settings → Privacy & Security)

### Option 2: Development Install

```bash
git clone https://github.com/yourusername/ankigammon.git
cd ankigammon
pip install -r requirements.txt
python -m ankigammon
```

## Quick Start

### Interactive Mode (Easiest)
```bash
ankigammon
```
Then paste XG positions when prompted.

### File-Based Mode
```bash
# Push directly to Anki (requires AnkiConnect addon)
ankigammon analysis.txt

# Or generate APKG file
ankigammon analysis.txt --format apkg
```

## Getting Positions from XG

1. In eXtreme Gammon, analyze a position
2. Press Ctrl+C to copy the analysis
3. Paste into a text file or interactive mode
4. Run ankigammon

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

## Supported Position Formats

AnkiGammon supports three backgammon position ID formats, with automatic detection:

### XGID (eXtreme Gammon ID) - Primary Format
**Format:** `XGID=PPPPPPPPPPPPPPPPPPPPPPPPPP:CV:CP:T:D:S1:S2:CJ:ML:MC`

The standard XG format with 9 colon-separated fields including position, cube state, dice, and match info.

**Example:**
```
XGID=---BBBBAAA---Ac-bbccbAA-A-:1:1:-1:63:4:3:0:5:8
```

### OGID (OpenGammon Position ID) - Alternative Format
**Format:** `P1:P2:CUBE[:DICE[:TURN[:STATE[:S1[:S2[:ML[:MID[:NCHECKERS]]]]]]]]`

Human-readable base-26 encoding with optional metadata fields. More verbose but easier to understand.

**Example:**
```
cccccggggg:ddddiiiiii:N0N:63:W:IW:4:3:7:1:15
```

### GNUID (GNU Backgammon ID) - GnuBG Format
**Format:** `PositionID:MatchID` (Base64 encoded)

Compact format used by GNU Backgammon. 14-character Position ID + 12-character Match ID.

**Example:**
```
4HPwATDgc/ABMA:8IhuACAACAAE
```

**⚠️ Known Limitation:** GNUID Position ID decoding is currently incomplete - only one player's checkers decode correctly. For full accuracy, prefer XGID or OGID formats. GNUID works best when combined with full analysis text or for match metadata extraction.

### Format Detection

The application **automatically detects** which format you're using. Just paste your position and AnkiGammon will handle it:
- XGID: Detected by `XGID=` prefix
- OGID: Detected by base-26 pattern with colons
- GNUID: Detected by base64 pattern

You can mix formats in the same input - each position can use a different format!

## Output Formats

### AnkiConnect (Default - Recommended)

Push cards directly to running Anki:
```bash
python -m ankigammon analysis.txt
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
python -m ankigammon analysis.txt --format apkg
```

Import into Anki: File → Import → Select the .apkg file

## Command-Line Options

```
Usage: ankigammon [OPTIONS] [INPUT_FILE]

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
python -m ankigammon

# Push to Anki (default)
python -m ankigammon positions.txt

# Generate APKG file
python -m ankigammon positions.txt --format apkg

# Custom deck name
python -m ankigammon positions.txt --deck-name "Opening Plays"

# Show text options on front
python -m ankigammon positions.txt --show-options
```

## Troubleshooting

**"Cannot connect to Anki-Connect"**
- Install AnkiConnect addon: https://ankiweb.net/shared/info/2055492159
- Make sure Anki is running
- Check firewall isn't blocking localhost:8765

**"No decisions found in input file"**
- Ensure file includes position ID lines (XGID, OGID, or GNUID format)
- Make sure move analysis includes equity values (eq:)
- Copy the full position from XG (press Ctrl+C)
- For GNUID format: Consider using XGID or OGID instead due to known limitations

## For Developers

### Building the Executable

**Quick Build:**

Windows:
```bash
build_executable.bat
```

macOS/Linux:
```bash
chmod +x build_executable.sh
./build_executable.sh
```

The executable will be in the `dist/` folder.

**Manual Build (if script doesn't work):**

Windows:
```bash
# Install PyInstaller
pip install pyinstaller

# Clean previous builds
rmdir /s /q build dist

# Build
pyinstaller ankigammon.spec
```

macOS/Linux:
```bash
# Install PyInstaller
pip3 install pyinstaller

# Clean previous builds
rm -rf build dist

# Build
pyinstaller ankigammon-mac.spec

# Remove quarantine attribute (macOS only)
xattr -cr dist/ankigammon
```

### Testing Builds

Before distributing:

Windows:
```bash
# Test the executable works
cd dist
ankigammon.exe --help

# Test interactive mode
ankigammon.exe

# Test with a sample file
ankigammon.exe ..\examples\example_xg_export.txt
```

macOS/Linux:
```bash
# Test the executable works
cd dist
./ankigammon --help

# Test interactive mode
./ankigammon

# Test with a sample file
./ankigammon ../examples/example_xg_export.txt
```

### Project Structure

- `ankigammon/` - Main package code
  - `parsers/` - XG text format parsers
  - `renderer/` - Board image generation
  - `anki/` - Anki card generation and export
  - `utils/` - Position format encoding/decoding (XGID, OGID, GNUID)
  - `gui/` - GUI components and format detection
- `tests/` - Unit tests (includes tests for all three formats)
- `ankigammon.spec` - PyInstaller configuration
- `build_executable.bat/.sh` - Build scripts

### Settings Storage

User preferences (color scheme, deck name, etc.) are stored in:
- Windows: `C:\Users\YourName\.ankigammon\config.json`
- macOS: `~/.ankigammon/config.json`
- Linux: `~/.ankigammon/config.json`

This ensures settings persist even when using the standalone executable.

### Troubleshooting Build Issues

**ImportError during build:**
- Add missing module to `hiddenimports` in `ankigammon.spec`

**"Module not found" when running executable:**
- Check the module is in `hiddenimports`
- Try: `pyinstaller --collect-all ankigammon ankigammon.spec`

**Executable too large:**
- Remove unused dependencies from requirements.txt
- Add more items to `excludes` in ankigammon.spec

**Executable won't run:**
- Test on clean machine without Python installed
- Check Windows Defender / antivirus isn't blocking it
- Look at build warnings: `pyinstaller ankigammon.spec > build.log 2>&1`

**Platform-Specific Issues:**

Windows:
- Some antivirus software may flag PyInstaller executables as suspicious (false positive)
- Users may need to add an exception in their antivirus
- To reduce false positives: Sign executable with code signing certificate

macOS:
- First run may show "cannot be opened because it is from an unidentified developer"
- Solution 1: Right-click executable → Open → Open anyway
- Solution 2: System Settings → Privacy & Security → Allow anyway
- Solution 3: Remove quarantine: `xattr -cr dist/ankigammon`
- For distribution: Sign with Apple Developer certificate and notarize

Linux:
- Ensure executable has execute permissions: `chmod +x ankigammon`
- May need to install dependencies on minimal systems: `sudo apt install libxcb1`

## Requirements

- Python 3.8+ (for development/pip install)
- Dependencies: genanki, Pillow, click, requests, beautifulsoup4, lxml, numpy
- For standalone executable: No requirements, Python is bundled

## License

MIT
