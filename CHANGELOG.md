# Changelog

## [1.1.3] - 2025-11-22

### Added
- XGP position files can now be imported (supports multiple files at once)
- SGF position files (without game records) can now be imported

### Improved
- Score matrix generation can now be cancelled more reliably during export
- GNU Backgammon validation runs more quietly in the background

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
