# Changelog

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
