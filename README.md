# AnkiGammon

A graphical application for converting backgammon positions into Anki flashcards. Analyze positions from eXtreme Gammon, OpenGammon, or GNU Backgammon and create smart study cards.

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/X8X31NIT0H)

## Features

- **Modern GUI interface** - Easy-to-use graphical application with drag-and-drop support
- **Multiple input formats** - XGID/OGID/GNUID position IDs, XG binary files (.xg, .xgp), match files (.mat), SGF files
- **Direct XG export support** - Copy/paste pre-analyzed positions from eXtreme Gammon
- **File import with filtering** - Drag-and-drop files with error threshold and player selection
- **GNU Backgammon integration** - Analyze unanalyzed positions automatically
- **Automatic format detection** - Paste any supported format, the app detects it automatically
- **Two export methods**:
  - AnkiConnect: Push directly to Anki (recommended)
  - APKG: Self-contained package for manual import
- **Customizable appearance** - 7 color schemes, board orientation (including random), configurable MCQ options (2-10)
- **Position management** - Multi-select, add notes, preview positions before export
- **Automatic update notifications** - Get notified when new versions are available
- **Comments extraction** - Automatically imports comments and notes from XG files (.xg, .xgp)

## Installation

### Standalone Executable (Recommended)

Download pre-built executables from [GitHub Releases](https://github.com/Deinonychus999/AnkiGammon/releases):

**Windows:**
1. Download `ankigammon-windows.zip` from the latest release
2. Extract the ZIP file
3. Double-click `ankigammon.exe`
4. **Windows SmartScreen Warning:** Click "More info" → "Run anyway"
   - This warning appears because the app is not code-signed
   - The application is safe and open-source

**macOS:**
1. Download `AnkiGammon-macOS.dmg` from the latest release
2. Open the DMG file
3. Drag AnkiGammon to your Applications folder
4. **First time only:** Right-click AnkiGammon → Open
   - If blocked, go to System Settings → Privacy & Security
   - Scroll down and click "Open Anyway"
   - Enter your password when prompted
5. After first run, you can open AnkiGammon normally

**Why do I see a security warning on macOS?**
AnkiGammon is not code-signed because that requires a $99/year Apple Developer account. The app is open-source and safe to use.

**Linux:**
1. Download `AnkiGammon-x86_64.AppImage` from the latest release
2. Make it executable:
   - Right-click → Properties → Permissions → "Allow executing file as program"
   - Or via terminal: `chmod +x AnkiGammon-x86_64.AppImage`
3. Double-click to run!

**Note for Ubuntu 22.04+ users:** If the AppImage doesn't run, install FUSE 2:
- Ubuntu 22.04: `sudo apt install libfuse2`
- Ubuntu 24.04: `sudo apt install libfuse2t64`

### Install via pip

[![PyPI version](https://badge.fury.io/py/ankigammon.svg)](https://pypi.org/project/ankigammon/)

If you have Python 3.8+ installed:

```bash
pip install ankigammon
ankigammon  # Launch the GUI
```

### Development Install

For developers who want to run from source:

```bash
git clone https://github.com/Deinonychus999/AnkiGammon.git
cd AnkiGammon
pip install -e .  # Install in editable mode
ankigammon  # Launches the GUI
```

## Usage

1. **Launch the application**:
   - Windows: Double-click `ankigammon.exe`
   - macOS: Open AnkiGammon from Applications folder
   - Linux: Double-click `AnkiGammon-x86_64.AppImage`
   - From PyPI install: Run `ankigammon` in terminal
2. **Add positions** (choose one or more methods):
   - **Paste XG analysis**: Press Ctrl+N, paste pre-analyzed positions from eXtreme Gammon (Ctrl+C)
   - **Paste position IDs**: Press Ctrl+N, paste XGID/OGID/GNUID strings (requires GNU Backgammon for analysis)
   - **Import files**: Press Ctrl+O or drag-and-drop files (.xg, .xgp, .mat, .sgf, .txt)
     - For match files: Choose error threshold and which player's mistakes to import
3. **Configure settings** - Choose color scheme, board orientation, and export method (Ctrl+,)
4. **Generate cards** - Click "Generate Cards" (Ctrl+E) to create Anki flashcards

### Keyboard Shortcuts

- **Ctrl+N** - Add positions
- **Ctrl+O** - Import file
- **Ctrl+E** - Export cards
- **Ctrl+,** - Settings
- **Ctrl+Q** - Quit
- **Delete/Backspace** - Remove selected positions

### Position Analysis

Unanalyzed positions (position IDs, match files, SGF files) can be analyzed using GNU Backgammon if configured in Settings (see Customization Options below).

## Supported Formats

AnkiGammon supports multiple input formats with automatic detection:

### XG Text Export (Pre-Analyzed)

Import **pre-analyzed positions** directly from eXtreme Gammon:

1. In eXtreme Gammon, analyze a position
2. Press Ctrl+C to copy the full analysis
3. Paste into AnkiGammon's input area

### Position ID Formats (Unanalyzed)

Position IDs encode positions without move analysis. Configure GNU Backgammon in Settings to enable automatic analysis.

- **XGID (eXtreme Gammon ID)** - 26-character position string + metadata fields
  - Example: `XGID=---BBBBAAA---Ac-bbccbAA-A-:1:1:-1:63:4:3:0:5:8`

- **OGID (OpenGammon Position ID)** - Base-26 position encoding with colon-separated fields
  - Example: `cccccggggg:ddddiiiiii:N0N:63:W:IW:4:3:7:1:15`

- **GNUID (GNU Backgammon ID)** - Compact Base64 format (PositionID:MatchID)
  - Example: `4HPwATDgc/ABMA:8IhuACAACAAE`

All formats fully support position encoding, cube state, dice, and match metadata.

### File Formats

- **XG Binary files (.xg, .xgp)** - eXtreme Gammon match and position files (includes pre-analysis from XG)
- **Match files (.mat, .txt)** - GNU Backgammon match exports (requires GNU Backgammon for analysis)
- **SGF files (.sgf)** - Smart Game Format for backgammon (requires GNU Backgammon for analysis)

Import via Ctrl+O or drag-and-drop directly onto the window.

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

### Regenerating Cards

Both export methods support updating existing cards when you change settings (color scheme, board orientation, etc.):
- Cards are matched by their XGID position identifier
- Re-exporting updates the card content while preserving your Anki review history
- Useful for applying new color schemes or enabling features like move score matrices

## Card Format

Each position becomes one Anki card:

**Front:**
- Board image showing the position
- Metadata: player on roll, dice, score, cube, match length
- Multiple choice: Candidate moves (configurable 2-10, labeled A-J, shuffled)
- Optional text move descriptions

**Back:**
- Position image and metadata
- MCQ feedback showing if your answer was correct, close, or incorrect
- Ranked table of moves with equity, error, and winning chances
- Interactive move visualization - click any move to see the resulting position
- Cubeful/cubeless equity toggle
- Source position ID with copy button for easy sharing
- Source attribution (analysis source and ply level)
- Explanation (if added)
- Score matrix showing optimal cube actions across all match scores (if enabled)
- Move score matrix showing top moves at different match contexts (if enabled)

## Customization Options

Open Settings with **Ctrl+,** to configure:

**Appearance:**
- **Color Schemes**: Choose from 7 built-in themes (Classic, Forest, Ocean, Desert, Sunset, Midnight, Monochrome)
- **Board Orientation**: Counter-clockwise (default), Clockwise, or Random (varies per card)
- **Score Format**: Display match scores as absolute (e.g., "3-2") or away (e.g., "4-away, 5-away")
- **Show Pip Count**: Toggle pip count display on the board
- **Swap Checker Colors**: Play as the other side by swapping checker colors

**Card Options:**
- **Show Move Options**: Toggle multiple-choice options on card front
- **Move Preview**: Preview the resulting position before submitting your answer
- **Interactive Moves**: Enable/disable animated move visualization on card back
- **Number of MCQ Options**: Configure how many moves to display (2-10, default: 5)

**Export:**
- **Deck Name**: Customize your Anki deck name
- **Export Method**: Choose between AnkiConnect or APKG output
- **Use Subdecks**: Split checker and cube decisions into separate subdecks
- **Clear After Export**: Automatically clear the position list after successful export

**Analysis:**
- **GNU Backgammon Path**: Configure path to `gnubg-cli` executable for automatic position analysis
- **Analysis Ply**: Set depth (0-4, default: 3)
- **Score Matrix**: Generate cube decision matrix for all match scores (optional, time-consuming)
- **Move Score Matrix**: Generate move analysis at different match contexts - Neutral, DMP, Gammon-Save, Gammon-Go (optional, time-consuming)

## Troubleshooting

**"Cannot connect to Anki-Connect"**
- Install AnkiConnect addon: https://ankiweb.net/shared/info/2055492159
- Make sure Anki is running
- Check firewall isn't blocking localhost:8765

**"No decisions found in input"**
- Ensure input includes position ID lines (XGID, OGID, or GNUID format)
- Copy the full analyzed position from XG (press Ctrl+C)

**Application won't start**
- Windows: Click "More info" → "Run anyway" if SmartScreen blocks the app
- macOS: Right-click → Open on first run, or go to System Settings → Privacy & Security → "Open Anyway"
- Linux: Make the AppImage executable with `chmod +x AnkiGammon-x86_64.AppImage`
- Linux (Ubuntu 22.04+): Install FUSE 2 with `sudo apt install libfuse2` or `sudo apt install libfuse2t64` (Ubuntu 24.04)
- Linux (running from source): If you get `ImportError: libxkbcommon.so.0`, install Qt dependencies with `sudo apt install libxkbcommon0 libxcb1`

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

### Settings Storage

User preferences (color scheme, deck name, board orientation, etc.) are automatically saved to:
- Windows: `C:\Users\YourName\.ankigammon\config.json`
- macOS: `~/.ankigammon/config.json`
- Linux: `~/.ankigammon/config.json`

Settings persist across application restarts, even when using the standalone executable.

### Troubleshooting Build Issues

**Missing modules in executable:**
- Add the module to `hiddenimports` in `ankigammon.spec`
- Or try: `pyinstaller --collect-all ankigammon ankigammon.spec`

**macOS code signing:**
- Remove quarantine for local testing: `xattr -cr dist/ankigammon`

## Requirements

- Python 3.8+ (for development install only)
- Dependencies automatically installed via `pip install .`: genanki, requests, PySide6, qtawesome
- For standalone executable: No requirements - Python and all dependencies are bundled

## License

AnkiGammon is licensed under the MIT License. See [LICENSE](LICENSE) for details.

For third-party licenses and attributions, see [THIRD-PARTY-LICENSES.md](THIRD-PARTY-LICENSES.md).
