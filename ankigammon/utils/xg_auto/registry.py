"""Read eXtreme Gammon 2 custom analysis level names from the Windows registry.

XG stores up to 5 user-defined analysis profiles under
``HKCU\\Software\\GameSite 2000\\eXtreme Gammon 2\\Analzye`` (sic — XG
misspells the key) as REG_SZ values named "1".."5". Format is
``<DisplayName>:<colon-delimited numeric parameters>``. We only need the
display name to mirror them in AnkiGammon's analysis-level dropdown.

The 7 built-in levels (None / Very Quick / Fast / Deep / Thorough /
World Class / Extensive) are baked into the XG binary and are NOT in the
registry; they must be merged with whatever this module returns.
"""

import logging
import sys
from typing import List

log = logging.getLogger(__name__)

_REG_PATH = r"Software\GameSite 2000\eXtreme Gammon 2\Analzye"


def read_custom_analysis_levels() -> List[str]:
    """Return display names of XG custom analysis profiles, or [] if unavailable.

    Safe to call on non-Windows or when XG isn't installed — degrades to
    an empty list. Read-only; never modifies the registry.
    """
    if sys.platform != "win32":
        return []

    try:
        import winreg
    except ImportError:
        return []

    names: List[str] = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH) as key:
            for slot in range(1, 6):
                try:
                    value, _type = winreg.QueryValueEx(key, str(slot))
                except FileNotFoundError:
                    continue
                if not isinstance(value, str) or not value:
                    continue
                display_name = value.split(":", 1)[0].strip()
                if display_name:
                    names.append(display_name)
    except FileNotFoundError:
        log.debug("XG custom-analysis registry key not present")
        return []
    except OSError as exc:
        log.warning("Failed to read XG custom analysis levels: %s", exc)
        return []

    return names
