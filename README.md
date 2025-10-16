# XG2Anki

Convert eXtreme Gammon (XG) positions and analysis into Anki flashcards for backgammon study.

## Features

- **XG text export input format**:
  - Direct copy/paste from eXtreme Gammon
  - Includes XGID, ASCII board, and rollout data
- **Flexible output options**:
  - `.apkg` file (ready to import into Anki)
  - CSV + media folder (manual import)
  - Direct push to Anki via Anki-Connect
- **Two card variants**:
  - Text MCQ: Shows move notation (e.g., "13/9 6/5")
  - Image MCQ: Shows visual board state after each candidate move
- **Complete decision analysis**: Top 5 moves with equities and error calculations
- **Automatic board rendering**: Generates board images from positions

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

Copy analysis directly from eXtreme Gammon:

1. In XG, select and copy your position analysis (Ctrl+C or Edit > Copy Position)
2. Paste into a text file (e.g., `my_analysis.txt`)
3. Run:
   ```bash
   python -m xg2anki my_analysis.txt
   ```
4. Import the generated `.apkg` into Anki!

See [XG_EXPORT_GUIDE.md](XG_EXPORT_GUIDE.md) for details.

## Usage Examples

### Basic usage (generates APKG):
```bash
python -m xg2anki my_analysis.txt
```

### With image-based choices:
```bash
python -m xg2anki my_analysis.txt --image-choices
```

### Export to CSV:
```bash
python -m xg2anki my_analysis.txt --format csv
```

### Push directly to Anki (requires Anki-Connect):
```bash
python -m xg2anki my_analysis.txt --format ankiconnect
```

### Custom deck name:
```bash
python -m xg2anki my_analysis.txt --deck-name "Backgammon::Expert Positions"
```

## Input Format

### XG Text Export Format

The XG text export format includes XGID, ASCII board diagram, and rollout data:

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

**How to get this format:**
1. In eXtreme Gammon, analyze a position
2. Go to Edit > Copy Position (or press Ctrl+C)
3. Paste into a text file
4. Save and run xg2anki on that file

See [XG_EXPORT_GUIDE.md](XG_EXPORT_GUIDE.md) for detailed instructions.

## Output

Each XG decision becomes one Anki card:

### Front (Text MCQ)
- Board image showing the position
- Metadata: player on roll, dice, score, cube state, match length
- Multiple choice: 5 candidate moves (labeled A-E, shuffled)

### Front (Image MCQ)
- Initial board position
- Metadata
- 2×3 grid showing resulting positions for each candidate move (A-E)

### Back
- Position image and metadata
- Ranked table of top 5 moves with equity and error
- Correct answer highlighted
- Source information (XGID, game/move numbers if available)

## Documentation

- **[XG_EXPORT_GUIDE.md](XG_EXPORT_GUIDE.md)** - How to use XG text exports (RECOMMENDED!)
- [USAGE.md](USAGE.md) - Comprehensive usage guide
- [QUICK_START.md](QUICK_START.md) - 5-minute tutorial
- [examples/](examples/) - Example input files
- [tests/](tests/) - Basic tests

## Command-Line Options

```
Usage: xg2anki [OPTIONS] INPUT_FILE

Options:
  --format [apkg|csv|ankiconnect]  Output format (default: apkg)
  -o, --output PATH                Output directory
  --deck-name TEXT                 Anki deck name (default: XG Backgammon)
  --image-choices                  Use image-based MCQ variant
  -i, --interactive                Run in interactive mode
  --help                           Show help message
```

## Requirements

- Python 3.8+
- See requirements.txt for dependencies

## Contributing

Contributions welcome! Feel free to open issues or submit pull requests.

## License

MIT
