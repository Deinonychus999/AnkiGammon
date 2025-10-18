# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

XG2Anki converts eXtreme Gammon (XG) backgammon analysis into Anki flashcards. The application parses XG text exports containing position analysis, renders board positions as images, and creates flashcards with multiple-choice questions about the best move.

## Commands

### Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application (interactive mode)
python -m xg2anki

# Run with file input
python -m xg2anki analysis.txt

# Run tests
python -m unittest tests/test_basic.py
```

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
2. **Position Encoding** (`utils/xgid.py`) → Handles XGID format for position representation
3. **Board Rendering** (`renderer/board_renderer.py`) → Generates PNG images of positions
4. **Card Generation** (`anki/card_generator.py`) → Creates Anki card HTML with MCQ format
5. **Export** → Either AnkiConnect API (`anki/ankiconnect.py`) or APKG file (`anki/apkg_exporter.py`)

### Critical Architecture Details

#### XGID Position Encoding (utils/xgid.py)

The XGID format is **perspective-dependent** for board points but **not for bar positions**. Understanding this is crucial when working with positions:

**Bar positions (ALWAYS the same regardless of turn):**
- Char 0 = X's bar → maps to points[0]
- Char 25 = O's bar → maps to points[25]

**Board points (perspective depends on turn):**
- **When turn=1 (O on roll)**: Encoding is from O's perspective (standard)
  - Chars 1-24 = points 1-24 in normal order
  - lowercase = X checkers (positive), uppercase = O checkers (negative)

- **When turn=-1 (X on roll)**: Encoding is **FLIPPED** from X's perspective
  - Point numbering is reversed (point 1 in encoding → point 24 in internal model)
  - The uppercase/lowercase → player mapping stays the same

**Internal Position Model** (always consistent):
- `points[0]` = X's bar (TOP player)
- `points[1-24]` = board points (point 1 = O's home, point 24 = X's home)
- `points[25]` = O's bar (BOTTOM player)
- Positive values = X checkers, Negative values = O checkers

#### Cube Decision Parsing (parsers/xg_text_parser.py)

XG provides 3 equity values in "Cubeful Equities:" section, but the parser generates **all 5 possible cube actions**:

1. Parse XG's 3 equities: No double, Double/Take, Double/Pass
2. Generate 5 options by adding "Too good/Take" and "Too good/Pass" (using Double/Pass equity)
3. Determine best move from "Best Cube action:" text
4. Rank all 5 options (rank 1 = best, ranks 2-5 based on equity)
5. Track both `xg_rank` (order in XG's output) and `rank` (overall best-to-worst)

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
- **`utils/xgid.py`**: XGID encoding/decoding with perspective handling
- **`parsers/xg_text_parser.py`**: Parses XG text exports, handles cube decisions
- **`renderer/board_renderer.py`**: Generates backgammon board images with PIL
- **`renderer/color_schemes.py`**: Defines color schemes for board rendering (6 built-in schemes: classic, forest, ocean, desert, sunset, midnight)
- **`anki/card_generator.py`**: Creates MCQ flashcard HTML
- **`anki/ankiconnect.py`**: Sends cards to Anki via AnkiConnect API
- **`anki/apkg_exporter.py`**: Generates .apkg files using genanki
- **`cli.py`**: Command-line interface with `--color-scheme` option
- **`interactive.py`**: Interactive mode for collecting positions with color scheme selection
- **`settings.py`**: Settings persistence (saves user preferences like color scheme to `~/.xg2anki/config.json`)

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
- In CLI: `python -m xg2anki --color-scheme ocean analysis.txt`
- In interactive mode: Option 2 from main menu
- User's selection is saved to `~/.xg2anki/config.json` and persisted across sessions

#### Settings Persistence (settings.py)

User preferences are automatically saved to `~/.xg2anki/config.json`:

**Saved Settings:**
- `default_color_scheme` - Last selected color scheme (default: "classic")
- `deck_name` - Default deck name (default: "XG Backgammon")
- `show_options` - Whether to show options on cards (default: true)

**Settings API:**
```python
from xg2anki.settings import get_settings

settings = get_settings()
settings.color_scheme = "forest"  # Automatically saved
print(settings.color_scheme)  # Loads from config file
```

**Fallback Behavior:**
- Missing config file → uses defaults
- Corrupted config file → silently falls back to defaults
- CLI `--color-scheme` argument → overrides saved preference for that run only

## Common Patterns

### Adding a New Input Format

1. Create parser in `parsers/` implementing `parse_file()` → `List[Decision]`
2. Add format detection in `cli.py:parse_input()`
3. Update `--input-format` option in CLI

### Adding a New Color Scheme

1. Define new `ColorScheme` object in `renderer/color_schemes.py`
2. Add to `SCHEMES` dictionary with a lowercase key name
3. Update `--color-scheme` choices in `cli.py` (line 45)
4. The scheme will automatically appear in interactive mode's color scheme menu

### Modifying Card Layout

1. Edit HTML templates in `anki/card_generator.py` (`_generate_*_front/back` methods)
2. Update CSS in `anki/card_styles.py`
3. Ensure media files (board images) are tracked in `media_files` list

### Working with Positions

Always use the internal Position model (points[0-25]). When reading/writing XGID:
- Use `parse_xgid()` to convert XGID → (Position, metadata)
- Use `encode_xgid()` or `Position.to_xgid()` to convert back
- Never manually flip positions; XGID parsing handles perspective automatically

### Working with Settings

Always use the global settings instance via `get_settings()`:
- Automatically loads from `~/.xg2anki/config.json`
- Changes are immediately persisted to disk
- Thread-safe singleton pattern
- Gracefully handles missing/corrupted config files
