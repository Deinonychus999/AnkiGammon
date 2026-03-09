# Changelog

## [1.4.0b6] - 2026-03-09

### Added
- "Send Diagnostic Logs" button in Help menu to collect and share logs for troubleshooting
- Persistent debug logging to `~/.ankigammon/ankigammon.log` for diagnosing issues

## [1.4.0b5] - 2026-03-08

### Fixed
- XG position import now uses a temp file instead of the clipboard, preventing interference from user copy/paste activity
- Clipboard export from XG now validates content and retries automatically if overwritten

## [1.4.0b4] - 2026-03-08

### Added
- Support for eXtreme Gammon 2.19 (auto-detects version and uses correct menu commands)

### Fixed
- .mat file import now works correctly in XG automation
- Cancelling analysis/export immediately terminates the headless XG process instead of waiting for timeout
- Startup dialogs in XG no longer block automated analysis
- Score matrix export reuses the existing XG instance instead of launching a second one

## [1.4.0b3] - 2026-03-08

### Fixed
- Score matrix now reuses the analysis engine, improving export speed
- Analysis engine label now correctly shows "XG" when using eXtreme Gammon
- Resolved a Windows threading warning when using XG automation

## [1.4.0b2] - 2026-03-08

### Improved
- XG automation dependencies (pywinauto, pyautogui) are now bundled with the application
- eXtreme Gammon integration is disabled on non-Windows platforms
- Version number now shown in the main window title bar

## [1.4.0b1] - 2026-03-08

### Added
- eXtreme Gammon (XG) as an analysis engine option alongside GNU Backgammon
- Double cubeless equity with MET calculation for XG text and binary parsing
- Pre-release version support for beta releases

### Improved
- Max moves setting now works independently of MCQ mode

## [1.3.0] - 2026-01-31

### Added
- Regenerate all existing cards in Anki with current settings (File → Regenerate Cards in Anki)
- Cubeless equity display for moves and cube decisions

### Fixed
- "Too good to double" MCQ now marks wrong answers correctly and shows correct equities

### Improved
- Re-exporting positions no longer creates duplicates; existing cards are updated instead
- Score matrix row count now respects max MCQ options setting

## [1.2.0] - 2026-01-26

### Added
- Move score matrix showing best moves across different match scores
- XGID copy button on card back for easy position sharing
- Option to display match scores as "absolute" or "away" format
- Option to show original position on card back
- XGID field in Anki notes for position-based sorting and searching

### Improved
- Clear error message when GNU Backgammon is not configured for export analysis

## [1.1.7] - 2026-01-25

### Fixed
- GNU Backgammon parser now correctly extracts winning probabilities and identifies played moves in cube decisions
- Cube action display now handles "too good to double" scenarios correctly
- Board elements (bearoff trays, bar checkers, pip counts) now flip correctly when changing board perspective

### Changed
- "Money games" renamed to "unlimited games" for clarity

## [1.1.6] - 2026-01-13

### Added
- Monochrome color scheme for a clean, minimalist board appearance
- Option to swap checker colors (play as the other side)
- Option to keep positions in the list after export

### Fixed
- Match import now works when GNU Backgammon uses MWC output mode
- Winning chances circles now display correct colors based on board perspective
- Linux AppImage compatibility with modern distributions

### Improved
- Error display now matches XG convention: signed values for cube actions, negative for checker plays
- Analysis table highlights the move that was actually played
- Export dialog shows "Done" button after successful export for better workflow

## [1.1.5] - 2025-12-02

### Added
- Option to split checker and cube decisions into separate subdecks
- Random board orientation option
- Option to toggle pip count display on cards

### Fixed
- Score and cube owner display now correct across all position formats
- AnkiDroid cards now auto-flip correctly after answering
- Clockwise board orientation now positions cube and bearoff correctly
- Linux AppImage missing dependency
- Unanalyzed XGP files can now be imported

### Improved
- Flashcard layout on mobile devices

## [1.1.4] - 2025-11-23

### Added
- Move preview option in settings to view checker movements before submitting answers on flashcards

## [1.1.3] - 2025-11-22

### Added
- XGP position files can now be imported (supports multiple files at once)
- SGF position files (without game records) can now be imported

### Improved
- Score matrix generation can now be cancelled more reliably during export
- GNU Backgammon validation in the settings dialog doesn't make sound anymore

### Fixed
- Winning chances table now displays correctly for cube decisions at all analysis depths

## [1.1.2] - 2025-11-21

### Fixed
- GNU Backgammon analysis now works correctly for users with European locale settings (comma decimal separators)

## [1.1.1] - 2025-11-20

### Added
- Score matrix now supports redouble positions in match play

### Improved
- GNU Backgammon can now analyze longer matches at high ply levels without timing out
- GNU Backgammon no longer plays sounds during analysis

### Fixed
- Score matrix now uses correct cube ownership, matching the main analysis equity values
- Player names with spaces now import correctly from match files

## [1.1.0] - 2025-11-15

### Added
- Comments and notes from XG text files or pasted XG analyzed position text are now automatically imported
- Cards now display source information (position format, analysis depth, and source file)

### Improved
- Pip counts now display in larger, more readable font on board diagrams
- Position list automatically clears after successful export to keep workspace tidy

### Fixed
- XG binary file imports no longer fail when temporary rollout files are present
- XG text exports from European locale systems now import correctly (comma decimal separators)

## [1.0.10] - 2025-11-10

### Added
- Tips & Shortcuts dialog in Help menu to improve feature discoverability

### Improved
- Disabled system beep sounds in message dialogs for better user experience

## [1.0.9] - 2025-11-10

### Improved
- Import dialog now supports separate error thresholds for checker play and cube decisions

### Fixed
- Windows executable no longer spawns multiple instances during score matrix generation

## [1.0.8] - 2025-11-09

### Improved
- Update dialog now renders release notes with markdown formatting for better readability
- Update notifications now show cumulative changelogs from all missed versions instead of just the latest
- Update check cache duration reduced from 24 hours to 6 hours for faster update discovery

### Fixed
- Release date in update dialog now displays in local timezone instead of UTC

## [1.0.7] - 2025-11-09

### Fixed
- XGID cube position encoding to correctly handle perspective changes
- GNUBG parser Double vs Redouble terminology

## [1.0.6] - 2025-11-09

### Added
- Automatic update notifications to alert users when new versions are available
- Manual update check via Help menu
- Update notification caching to avoid excessive GitHub API calls
- Direct download links for platform-specific installers in update dialog

## [1.0.5] - 2025-11-09

### Fixed
- UnboundLocalError when generating card backs for certain decision types
- Score matrix generation now correctly handles redouble positions
- Score matrix styling improvements for better readability

## [1.0.4] - 2025-11-08

### Improved
- Import dialog now remembers player selection by name across multiple file imports
- Cube action analysis table on flashcards now uses cleaner "Action" column header
- Card back layout simplified by removing redundant rank column from cube decisions

### Fixed
- Layout shift issue in import dialog during player selection

## [1.0.3] - 2025-11-04

### Improved
- Multi-file import process for better handling of batch imports
- Linux build configuration now targets Ubuntu 22.04 for better compatibility

## [1.0.2] - 2025-11-03

### Fixed
- Linux missing dependencies in AppImage
- XG binary parser now correctly handles hit markers in move notation
- Improved accuracy of move notation for positions with intermediate hits

### Changed
- Migrated test suite from unittest to pytest
- Enhanced XG binary parser move notation conversion algorithm

### Removed
- Removed unused BeautifulSoup4 and lxml dependencies to reduce package size

## [1.0.1] - 2025-11-02

### Added
- SGF (Smart Game Format) file import support for backgammon positions
- Match file import support (.mat format and plain text match files)
- Player name extraction from match file headers
- Import options dialog for filtering positions by player and decision type
- Winning chances extraction from GNU Backgammon cube analysis
- Score matrix display on cube decision flashcards
- Match analysis progress feedback in GUI

### Improved
- File import responsiveness with background processing
- XG binary parser now extracts cube decisions and winning probabilities
- XGID generation for score matrix position encoding
- Format detection for multiple file types (XG, MAT, SGF, plain text)
- Main window button layout for better workflow
- Card generation with enhanced metadata display


## [1.0.0] - 2025-10-31

### Added
- Initial release
- Windows, macOS, and Linux executable support
- XG text parser with XGID and OGID support
- Interactive flashcard generation
- AnkiConnect and APKG export options
- GUI with position preview and card customization
- 6 color schemes for board rendering
