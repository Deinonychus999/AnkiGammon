# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AnkiGammon converts eXtreme Gammon (XG) backgammon analysis into Anki flashcards. The application parses XG text exports containing position analysis, renders board positions as images, and creates flashcards with multiple-choice questions about the best move.

## Commands

### Development

```bash
# Install dependencies
pip install .

# Install in editable mode (for development)
pip install -e .

# Install with dev dependencies (includes PyInstaller, pytest)
pip install -e .[dev]

# Run the GUI application (after installation)
ankigammon

# Or run as a module (works without installation if package is in PYTHONPATH)
python -m ankigammon

# Or run the app.py directly
python ankigammon/gui/app.py

# Run tests
python -m unittest tests/test_basic.py
```

### Building Executables

**Windows:**
```bash
# Build using the build script
.\build_executable.bat

# Or use PyInstaller directly
pyinstaller ankigammon.spec
```

**macOS/Linux:**
```bash
# Build using the build script
./build_executable.sh

# Or use PyInstaller directly
pyinstaller ankigammon.spec
```

**Build Output:**
- Executable: `dist/AnkiGammon.exe` (Windows) or `dist/AnkiGammon.app` (macOS)
- Build artifacts: `build/` directory (can be deleted)
- Size: ~16MB (includes Python runtime and all dependencies)
- No Python installation required on target machine

### Testing

```bash
# Run all tests
python -m unittest discover tests

# Run specific test
python -m unittest tests.test_basic.TestXGIDParsing
```

## Architecture

### Core Data Flow

1. **Input Parsing** (`parsers/xg_text_parser.py`) → Parses XG text export into `Decision` objects
2. **Position Encoding** (`utils/xgid.py`, `utils/ogid.py`, `utils/gnuid.py`) → Handles three position formats: XGID (primary), OGID, and GNUID
3. **Board Rendering** (`renderer/svg_board_renderer.py`) → Generates SVG markup of positions
4. **Card Generation** (`anki/card_generator.py`) → Creates Anki card HTML with embedded SVG and MCQ format
5. **Export** → Either AnkiConnect API (`anki/ankiconnect.py`) or APKG file (`anki/apkg_exporter.py`)

### Critical Architecture Details

#### XGID Position Encoding (utils/xgid.py)

The XGID format is **entirely perspective-dependent**. The ENTIRE 26-character position string (including bars) depends on whose turn it is:

**When turn=1 (O on roll - standard view):**
- Char 0 = X's bar (top) → maps to points[0]
- Chars 1-24 = points 1-24 in normal order
- Char 25 = O's bar (bottom) → maps to points[25]
- lowercase = X checkers (positive), uppercase = O checkers (negative)

**When turn=-1 (X on roll - flipped view):**
- Char 0 = O's bar (top in X's view) → maps to points[25]
- Chars 1-24 = points in REVERSED order (char 1 → point 24, char 24 → point 1)
- Char 25 = X's bar (bottom in X's view) → maps to points[0]
- **lowercase = O checkers (negative), uppercase = X checkers (positive) - MAPPING IS FLIPPED!**

**Key insight:** When X is on roll, the ENTIRE encoding is flipped: bars are swapped, points are reversed, AND uppercase/lowercase meanings are inverted.

**Internal Position Model** (always consistent):
- `points[0]` = X's bar (TOP player)
- `points[1-24]` = board points (point 1 = O's home, point 24 = X's home)
- `points[25]` = O's bar (BOTTOM player)
- Positive values = X checkers, Negative values = O checkers

#### OGID Position Encoding (utils/ogid.py)

OGID (OpenGammon Position ID) is an alternative position format with **colon-separated fields** and **base-26 encoding**.

**Format Structure:**
```
P1:P2:CUBE[:DICE[:TURN[:STATE[:S1[:S2[:ML[:MID[:NCHECKERS]]]]]]]]
```

**Position Encoding (P1 and P2):**
- **Base-26 encoding** with repeated characters for multiple checkers
- Characters '0'-'9' = points 0-9
- Characters 'a'-'p' = points 10-25
- Repeated characters indicate multiple checkers on the same point
- Example: "aa" = 2 checkers on point 10, "000" = 3 checkers on point 0

**Cube Field (3 characters):**
- Char 1: Cube owner (W=White/X, B=Black/O, N=centered)
- Char 2: Cube value (0-9 as log2: 0=1, 1=2, 2=4, etc.)
- Char 3: Cube action (O=Offered, T=Taken, P=Passed, N=Normal)

**Optional Metadata Fields:**
- **DICE**: Two-digit dice roll (e.g., "63")
- **TURN**: W=White on roll, B=Black on roll
- **STATE**: Two-character game state (e.g., "IW", "FB")
- **S1/S2**: Player scores
- **ML**: Match length with modifiers (L=Last game, C=Crawford, G=Galaxie)
  - Examples: "7" (7-point match), "5C" (Crawford game), "9G15" (Galaxie, max 15 games)
- **MID**: Move ID sequence number
- **NCHECKERS**: Number of checkers per side (default 15)

**Key Characteristics:**
- Not perspective-dependent (always absolute positions)
- Supports position-only mode (first 3 fields: P1:P2:CUBE)
- More verbose than XGID but more human-readable
- Used by OpenGammon and compatible tools

#### GNUID Position Encoding (utils/gnuid.py)

GNUID (GNU Backgammon ID) is GnuBG's native position format with **Base64 encoding**.

**Format Structure:**
```
PositionID:MatchID
```

**Position ID (14-character Base64 string):**
- Encodes 10 bytes (80 bits) of position data
- Variable-length bit encoding using run-length algorithm
- Always encoded from Player X's perspective
- Consecutive 1s represent checker counts at each point

**Match ID (12-character Base64 string):**
- Encodes 9 bytes (72 bits) of metadata
- Bit-packed fields:
  - Bits 0-3: Cube value (as log2)
  - Bits 4-5: Cube owner (0=centered, 1=player, 2=opponent, 3=not available)
  - Bit 7: Crawford rule flag
  - Bits 8-10: Game state
  - Bit 11: Turn (who's on roll)
  - Bits 15-20: Dice values
  - Bits 21-35: Match length
  - Bits 36-50: Player X score
  - Bits 51-65: Player O score

**Key Characteristics:**
- Most compact format (26 characters total)
- Base64 encoding for efficiency
- Bit-level packing of all metadata
- Native format for GNU Backgammon
- Fully supports both position encoding and metadata extraction

#### Cube Decision Parsing (parsers/xg_text_parser.py)

XG provides 3 equity values in "Cubeful Equities:" section, but the parser generates **all 5 possible cube actions**:

1. Parse XG's 3 equities: No double, Double/Take, Double/Pass
2. Generate 5 options by adding "Too good/Take" and "Too good/Pass" (using Double/Pass equity)
3. Determine best move from "Best Cube action:" text
4. Rank all 5 options (rank 1 = best, ranks 2-5 based on equity)
5. Track both `xg_rank` (order in XG's output) and `rank` (overall best-to-worst)

#### Crawford Game Support

The application fully supports Crawford games across all layers:

**Data Model** (`models.py`):
- `Decision` class has `crawford: bool` field to indicate Crawford game status
- `get_metadata_text()` displays "7pt (Crawford)" for Crawford games vs. "7pt" for normal match games

**Position Format Support:**
- **XGID**: Field 8 (`crawford_jacoby`) indicates Crawford rule (value 1) or Jacoby rule (money games)
- **OGID**: Match modifier 'C' in field 9 (e.g., "5C" = 5-point Crawford match)
- **GNUID**: Bit 7 of Match ID is dedicated Crawford boolean flag

**XG Text Parser** (`parsers/xg_text_parser.py`):
- Detects Crawford games from pip count line: `Pip count  X: 156  O: 167 X-O: 1-4/5 Crawford`
- Multi-source Crawford detection with priority: Text parsing → XGID → OGID → GNUID
- Note: XG text format shows "5 pt.(s) match." in score line; Crawford appears only in pip count

**Card Display:**
- Flashcards show Crawford status in metadata line
- Example: "White | Dice: 66 | Score: 1-4 | Cube: — | Match: 5pt (Crawford)"

#### Card Back Analysis Table (anki/card_generator.py)

The card back shows moves in **XG's original order** (not shuffled MCQ order):

- Sort by `xg_rank` (preserves "Cubeful Equities:" order)
- Display `xg_notation` (e.g., "No double" not "No double/Take")
- Display `xg_error` (XG's error with sign, not our calculated error)
- Only show moves where `from_xg_analysis=True` (excludes synthetic "Too good" options)
- Highlight the overall best move (rank == 1)

#### Player Representation

- **Internal model**: Player.O = BOTTOM player (plays up the board), Player.X = TOP player (plays down)
- **Board rendering**: Always shown from O's perspective (O at bottom, X at top)
- **Display names**: Player.O = "White", Player.X = "Black" (in metadata text)
- The board is **never flipped** in rendering; XG positions are already encoded correctly

## Key Files

- **`models.py`**: Core data classes (Position, Decision, Move, Player, CubeState, DecisionType)
- **`utils/xgid.py`**: XGID encoding/decoding with perspective handling (primary format)
- **`utils/ogid.py`**: OGID encoding/decoding with base-26 format (alternative format)
- **`utils/gnuid.py`**: GNUID encoding/decoding for GNU Backgammon format (has known Position ID limitations)
- **`parsers/xg_text_parser.py`**: Parses XG text exports (supports XGID and OGID), handles cube decisions
- **`gui/main_window.py`**: Main GUI window for the application
- **`gui/format_detector.py`**: Auto-detects position format (XGID, OGID, or GNUID)
- **`gui/dialogs/settings_dialog.py`**: Settings dialog for user preferences
- **`renderer/svg_board_renderer.py`**: Generates backgammon board SVG markup
- **`renderer/color_schemes.py`**: Defines color schemes for board rendering (6 built-in schemes: classic, forest, ocean, desert, sunset, midnight)
- **`anki/card_generator.py`**: Creates MCQ flashcard HTML with embedded SVG boards
- **`anki/ankiconnect.py`**: Sends cards to Anki via AnkiConnect API
- **`anki/apkg_exporter.py`**: Generates .apkg files using genanki
- **`settings.py`**: Settings persistence (saves user preferences like color scheme to `~/.ankigammon/config.json`)

#### Color Schemes (renderer/color_schemes.py)

The application supports customizable board color schemes:

**Available Schemes:**
- `classic` - Traditional brown/beige board
- `forest` - Green/brown nature theme
- `ocean` - Blue/teal water theme
- `desert` - Tan/orange sand theme
- `sunset` - Purple/orange evening theme
- `midnight` - Dark blue/purple night theme

**Color Scheme Properties:**
Each `ColorScheme` dataclass defines 10 colors:
- `board_light`, `board_dark` - Board background and borders
- `point_light`, `point_dark` - Triangle point colors
- `checker_x`, `checker_o` - Checker colors for X (top) and O (bottom) players
- `checker_border` - Checker outline color
- `bar` - Center bar color
- `text` - Text color for labels
- `bearoff` - Bear-off tray background

**Usage:**
- In GUI: Settings dialog, Card Appearance section
- User's selection is saved to `~/.ankigammon/config.json` and persisted across sessions

#### Board Orientation (renderer/svg_board_renderer.py)

The application supports two board orientation modes that horizontally mirror the entire board layout:

**Available Orientations:**
- `counter-clockwise` (default) - Standard backgammon numbering
  - Layout: Top (13-18 left, 19-24 right) | Bottom (12-7 left, 6-1 right)
  - Point 1 = bottom right edge, Point 24 = top right edge
  - Most common numbering system used in backgammon
- `clockwise` - Horizontally mirrored layout
  - Layout: Top (24-19 left, 18-13 right) | Bottom (1-6 left, 7-12 right)
  - Point 1 = bottom left edge, Point 24 = top left edge
  - Simple horizontal mirror of the standard layout

**Implementation Details:**
- The `SVGBoardRenderer` accepts an `orientation` parameter
- Visual positions are mapped via `_get_visual_point_index()` method
- The entire board layout is mirrored horizontally, including checker positions
- A checker on point 24 will always be labeled "24" but appears on top-right (counter-clockwise) or top-left (clockwise)

**Visual Mapping Formula (Clockwise):**
- Points 1-12: `visual = 12 - point` (bottom row, flipped)
- Points 13-24: `visual = 36 - point` (top row, both quadrants reversed)

**Usage:**
- In GUI: Settings dialog, Card Appearance section
- User's selection is saved to `~/.ankigammon/config.json` and persisted across sessions
- Setting is automatically applied to all generated cards

#### Settings Persistence (settings.py)

User preferences are automatically saved to `~/.ankigammon/config.json`:

**Saved Settings:**
- `default_color_scheme` - Last selected color scheme (default: "classic")
- `deck_name` - Default deck name (default: "My AnkiGammon Deck")
- `show_options` - Whether to show options on cards (default: true)
- `interactive_moves` - Whether to enable interactive move visualization (default: true)
- `export_method` - Export method for cards: "ankiconnect" or "apkg" (default: "ankiconnect")
- `board_orientation` - Board orientation: "clockwise" or "counter-clockwise" (default: "counter-clockwise")

**Settings API:**
```python
from ankigammon.settings import get_settings

settings = get_settings()
settings.color_scheme = "forest"  # Automatically saved
settings.interactive_moves = True  # Enable interactive move visualization
settings.export_method = "apkg"  # Choose export method: "ankiconnect" or "apkg"
settings.board_orientation = "clockwise"  # Set board orientation
print(settings.color_scheme)  # Loads from config file
```

**Fallback Behavior:**
- Missing config file → uses defaults
- Corrupted config file → silently falls back to defaults

## Common Patterns

### Adding a New Input Format

1. Create parser in `parsers/` implementing `parse_file()` → `List[Decision]`
2. Add format detection in GUI file import logic
3. Update GUI to handle the new format

### Adding a New Color Scheme

1. Define new `ColorScheme` object in `renderer/color_schemes.py`
2. Add to `SCHEMES` dictionary with a lowercase key name
3. The scheme will automatically appear in the GUI settings dialog

### Modifying Card Layout

1. Edit HTML templates in `anki/card_generator.py` (`_generate_*_front/back` methods)
2. Update CSS in `anki/card_styles.py`
3. Ensure media files (board images) are tracked in `media_files` list

### Working with Positions

Always use the internal Position model (points[0-25]). The application supports three position formats:

**XGID (Primary format):**
- Use `parse_xgid()` to convert XGID → (Position, metadata)
- Use `encode_xgid()` or `Position.to_xgid()` to convert back
- Never manually flip positions; XGID parsing handles perspective automatically

**OGID (Alternative format):**
- Use `parse_ogid()` to convert OGID → (Position, metadata)
- Use `encode_ogid()` or `Position.to_ogid()` to convert back
- More human-readable than XGID, supports position-only mode

**GNUID (GNU Backgammon format):**
- Use `parse_gnuid()` to convert GNUID → (Position, metadata)
- Use `encode_gnuid()` or `Position.to_gnuid()` to convert back
- ⚠️ Known limitation: Position ID decoding is incomplete, prefer XGID/OGID for accuracy

**Format Conversion:**
```python
# Convert between formats using Position methods
position = Position.from_xgid("XGID=...")
ogid = position.to_ogid(...)
gnuid = position.to_gnuid(...)

# Auto-detect format in GUI
from ankigammon.gui.format_detector import FormatDetector
result = FormatDetector.detect(user_input)
```

### Working with Settings

Always use the global settings instance via `get_settings()`:
- Automatically loads from `~/.ankigammon/config.json`
- Changes are immediately persisted to disk
- Thread-safe singleton pattern
- Gracefully handles missing/corrupted config files
