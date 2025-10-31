# AnkiGammon

A graphical application for converting backgammon positions into Anki flashcards. Analyze positions from eXtreme Gammon, OpenGammon, or GNU Backgammon and create smart study cards.

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/X8X31NIT0H)

## Features

- **Modern GUI interface** - Easy-to-use graphical application, no command-line needed
- **Multiple position format support** - XGID (eXtreme Gammon), OGID (OpenGammon), and GNUID (GNU Backgammon)
- **Direct XG export support** - Copy/paste positions from eXtreme Gammon
- **Smart rendering** - Automatic board image generation from position IDs
- **Automatic format detection** - Paste any supported format, the app detects it automatically
- **Two export methods**:
  - AnkiConnect: Push directly to Anki (recommended)
  - APKG: Self-contained package for manual import
- **Customizable appearance** - 6 color schemes and board orientation options
- **Complete analysis** - Top 5 moves with equities and error calculations

## Installation

[![PyPI version](https://badge.fury.io/py/ankigammon.svg)](https://pypi.org/project/ankigammon/)

### Quick Install (PyPI - Recommended for Python users)

If you have Python 3.8+ installed:

```bash
pip install ankigammon
ankigammon  # Launch the GUI
```

### Standalone Executable (No Python required)

Download pre-built executables from [GitHub Releases](https://github.com/Deinonychus999/AnkiGammon/releases):

**Windows:**
1. Download `ankigammon-windows.zip` from the latest release
2. Extract and double-click `ankigammon.exe`

**macOS/Linux:**
1. Download the appropriate release for your platform
2. macOS first run: Right-click → Open (or allow in System Settings → Privacy & Security)

### Development Install

For developers who want to run from source:

```bash
git clone https://github.com/Deinonychus999/AnkiGammon.git
cd AnkiGammon
pip install -e .  # Install in editable mode
ankigammon  # Launches the GUI
```

## Usage

1. **Launch the application** - Double-click `ankigammon.exe` (Windows) or run `./ankigammon` (macOS/Linux)
2. **Paste positions** - Copy analysis from eXtreme Gammon (Ctrl+C) and paste into the application
3. **Configure settings** - Choose color scheme, board orientation, and export method in Settings
4. **Generate cards** - Click "Generate Cards" to create Anki flashcards

### Getting Positions from eXtreme Gammon

1. In eXtreme Gammon, analyze a position
2. Press Ctrl+C to copy the full analysis
3. Paste into AnkiGammon's input area
4. Click "Generate Cards"

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

GNUID fully supports position encoding and decoding, including all checker positions, bars, cube state, and match metadata.

### Format Detection

The application **automatically detects** which format you're using. Just paste your position and AnkiGammon will handle it:
- XGID: Detected by `XGID=` prefix
- OGID: Detected by base-26 pattern with colons
- GNUID: Detected by base64 pattern

You can mix formats in the same input - each position can use a different format!

## Export Methods

### AnkiConnect (Recommended)

Push cards directly to running Anki through the GUI:
- Install [AnkiConnect addon](https://ankiweb.net/shared/info/2055492159)
- Keep Anki running while generating cards
- Cards appear instantly in your deck

### APKG

Generate a package file for manual import:
- Select "APKG" in Settings
- Import into Anki: File → Import → Select the .apkg file
- Useful for offline card generation

## Card Format

Each position becomes one Anki card:

**Front:**
- Board image showing the position
- Metadata: player on roll, dice, score, cube, match length
- Multiple choice: 5 candidate moves (labeled A-E, shuffled)
- Optional text move descriptions

**Back:**
- Position image and metadata
- Ranked table of top 5 moves with equity and error
- Correct answer highlighted
- Source position ID for reference

## Customization Options

The GUI Settings dialog provides:
- **Color Schemes**: Choose from 6 built-in themes (Classic, Forest, Ocean, Desert, Sunset, Midnight)
- **Board Orientation**: Counter-clockwise or Clockwise orientation
- **Deck Name**: Customize your Anki deck name
- **Show Move Options**: Toggle text move descriptions on card front
- **Interactive Moves**: Enable/disable move visualization
- **Export Method**: Choose between AnkiConnect or APKG output

## Troubleshooting

**"Cannot connect to Anki-Connect"**
- Install AnkiConnect addon: https://ankiweb.net/shared/info/2055492159
- Make sure Anki is running
- Check firewall isn't blocking localhost:8765

**"No decisions found in input"**
- Ensure input includes position ID lines (XGID, OGID, or GNUID format)
- Make sure move analysis includes equity values (eq:)
- Copy the full position from XG (press Ctrl+C)
- For GNUID format: Consider using XGID or OGID instead due to known limitations

**Application won't start**
- Windows: Check Windows Defender isn't blocking the executable
- macOS: Right-click → Open, or remove quarantine with `xattr -cr ankigammon`
- Linux: Ensure execute permissions with `chmod +x ankigammon`

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
pyinstaller ankigammon.spec

# Remove quarantine attribute (macOS only)
xattr -cr dist/ankigammon
```

### Testing the Build

Windows:
```bash
# Test the GUI launches
cd dist
ankigammon.exe
```

macOS/Linux:
```bash
# Test the GUI launches
cd dist
./ankigammon
```

### Project Structure

- `ankigammon/` - Main package code
  - `parsers/` - XG text format parsers
  - `renderer/` - Board image generation (SVG-based)
  - `anki/` - Anki card generation and export
  - `utils/` - Position format encoding/decoding (XGID, OGID, GNUID)
  - `gui/` - GUI components and format detection
- `tests/` - Unit tests (includes tests for all three formats)
- `ankigammon.spec` - PyInstaller configuration for GUI build
- `build_executable.bat/.sh` - Build scripts

### Settings Storage

User preferences (color scheme, deck name, board orientation, etc.) are automatically saved to:
- Windows: `C:\Users\YourName\.ankigammon\config.json`
- macOS: `~/.ankigammon/config.json`
- Linux: `~/.ankigammon/config.json`

Settings persist across application restarts, even when using the standalone executable.

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

- Python 3.8+ (for development install only)
- Dependencies automatically installed via `pip install .`: genanki, requests, beautifulsoup4, lxml, PySide6, qtawesome
- For standalone executable: No requirements - Python and all dependencies are bundled

## Legal

### Third-Party Software

This application uses several LGPL-licensed components:
- **PySide6** (LGPL-3.0) - Qt framework Python bindings for the GUI
- **xgdatatools** (LGPL-2.1) - Modules for parsing eXtreme Gammon binary file formats

See [THIRD-PARTY-LICENSES.md](THIRD-PARTY-LICENSES.md) for complete license information and attributions for all dependencies.

### Trademarks

- "eXtreme Gammon" and "XG" are registered trademarks of GameSite 2000 Ltd.
- "Anki" is a trademark of Ankitects Pty Ltd
- "Qt" is a trademark of The Qt Company Ltd.
- GNU Backgammon is part of the GNU Project

**This project is not affiliated with or endorsed by the creators of eXtreme Gammon, Anki, Qt, GNU Backgammon, or any other mentioned software.**

### Position Format Specifications

- **XGID format** specification is publicly documented by eXtreme Gammon (GameSite 2000 Ltd.) with explicit permission for redistribution: "This information can freely redistributed"
- **XG binary format** parsing is implemented using xgdatatools (LGPL-2.1) by Michael Petch, based on Delphi data structures provided by Xavier Dufaure de Citres
- **GNUID format** is documented in the GNU Backgammon manual (GPL-3.0 project); our implementation is original code that reads/writes this format without incorporating GPL code

All position encoding/decoding implementations in this project are original code, except for the xgdatatools modules used for XG binary file parsing.

## License

AnkiGammon is licensed under the MIT License. See [LICENSE](LICENSE) for details.
