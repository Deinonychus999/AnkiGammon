# Third-Party Licenses

AnkiGammon uses the following open-source libraries and components:

## Runtime Dependencies

### PySide6 (LGPL-3.0)

**Copyright:** Qt Company Ltd.
**License:** GNU Lesser General Public License v3.0
**Website:** https://www.qt.io/qt-for-python

This application uses PySide6, the official Python bindings for the Qt framework. PySide6 is licensed under the LGPL-3.0 license.

**LGPL Compliance Notice:**
- PySide6 is used as a dynamically linked library
- Users are free to replace the PySide6 library with their own version
- The GUI module is located in `ankigammon/gui/` and uses PySide6 as an external dependency
- Source code for AnkiGammon is available at: https://github.com/Deinonychus999/AnkiGammon
- PySide6 source code is available at: https://code.qt.io/cgit/pyside/pyside-setup.git/

For the full LGPL-3.0 license text, see: https://www.gnu.org/licenses/lgpl-3.0.html

---

### PySide6-Addons (LGPL-3.0)

**Copyright:** Qt Company Ltd.
**License:** GNU Lesser General Public License v3.0
**Website:** https://www.qt.io/qt-for-python

PySide6-Addons provides additional Qt modules for PySide6. It is licensed under the same LGPL-3.0 license as PySide6.

**LGPL Compliance Notice:**
- PySide6-Addons is used as a dynamically linked library
- Users are free to replace the PySide6-Addons library with their own version
- Source code for AnkiGammon is available at: https://github.com/Deinonychus999/AnkiGammon
- PySide6-Addons source code is available at: https://code.qt.io/cgit/pyside/pyside-setup.git/

For the full LGPL-3.0 license text, see: https://www.gnu.org/licenses/lgpl-3.0.html

---

### xgdatatools (LGPL-2.1)

**Copyright:** Copyright (c) 2013-2014 Michael Petch
**License:** GNU Lesser General Public License v2.1
**Website:** https://github.com/mpetch/xgdatatools (historical reference)

xgdatatools is a collection of Python modules for reading and parsing eXtreme Gammon (XG) binary file formats. This project incorporates the following modules from xgdatatools:
- `xgstruct.py` - Classes for reading XG file structures
- `xgzarc.py` - XG archive compression/decompression utilities
- `xgutils.py` - Utility functions for XG data handling
- `xgimport.py` - High-level XG file import functionality

**LGPL-2.1 Compliance Notice:**
- xgdatatools modules are used as library code within AnkiGammon
- Source code for the xgdatatools modules is included in this repository
- The full LGPL-2.1 license text is provided in `xgdatatools_LICENSE.txt`
- AnkiGammon source code is available at: https://github.com/Deinonychus999/AnkiGammon
- These modules were originally developed by Michael Petch for GNU Backgammon integration

For the full LGPL-2.1 license text, see: https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html

**Attribution:**
The xgdatatools code is based upon Delphi data structures provided by Xavier Dufaure de Citres (contact@extremegammon.com) for purposes of interacting with the eXtreme Gammon XG file formats. The file format specifications are published at http://www.extremegammon.com/xgformat.aspx

---

### beautifulsoup4 (MIT License)

**Copyright:** Copyright (c) 2004-present Leonard Richardson
**License:** MIT License
**Website:** https://www.crummy.com/software/BeautifulSoup/

Used for parsing HTML and XML content.

---

### lxml (BSD-3-Clause)

**Copyright:** Copyright (c) 2004 Infrae. Main development by Stefan Behnel and contributors.
**License:** BSD 3-Clause License
**Website:** https://lxml.de/

Used for XML processing.

---

### genanki (MIT License)

**Copyright:** Copyright (c) 2021 Kerrick Staley
**License:** MIT License
**Website:** https://github.com/kerrickstaley/genanki

Used for generating Anki .apkg files.

---

### requests (Apache-2.0)

**Copyright:** Copyright (c) Kenneth Reitz (original author). Project transferred to Python Software Foundation in 2019.
**License:** Apache License 2.0
**Website:** https://requests.readthedocs.io/

Used for HTTP communication with AnkiConnect.

---

### qtawesome (MIT License)

**Copyright:** Copyright (c) 2015 The Spyder Development Team and contributors. Original author: Sylvain Corlay.
**License:** MIT License
**Website:** https://github.com/spyder-ide/qtawesome

Used for icon support in the GUI.

---

## Position Format Specifications

### XGID Format (eXtreme Gammon)

The XGID position format specification is publicly documented by eXtreme Gammon with the explicit statement: "This information can freely be redistributed."

Our implementation is based on the public specification and is original code.

---

### GNUID Format (GNU Backgammon)

The GNUID format is used by GNU Backgammon, which is licensed under GPL-3.0. Our implementation is original code that reads and writes this format but does not incorporate any GPL code from GNU Backgammon itself.

---

## Trademarks

- "eXtreme Gammon" and "XG" are registered trademarks of GameSite 2000 Ltd.
- "Anki" is a trademark of Ankitects Pty Ltd
- "Qt" is a trademark of The Qt Company Ltd.
- GNU Backgammon is part of the GNU Project

This project is not affiliated with or endorsed by the creators of eXtreme Gammon, Anki, Qt, GNU Backgammon, or any other mentioned software.

---

## License Compatibility

All dependencies are compatible with MIT licensing:
- MIT + MIT = ✓ Compatible
- MIT + BSD-3-Clause = ✓ Compatible
- MIT + Apache-2.0 = ✓ Compatible
- MIT + LGPL-2.1 = ✓ Compatible (when used as library)
- MIT + LGPL-3.0 = ✓ Compatible (when used as library)

AnkiGammon remains licensed under the MIT License. The LGPL licenses (both LGPL-2.1 for xgdatatools and LGPL-3.0 for PySide6) apply only to those specific libraries, not to AnkiGammon itself.
