"""Validate XG automation translation tables against XG language files.

Reads eXtreme Gammon's XGLanguage/<LANG>/STRINGS.TXT and DLG files for
all 7 supported languages, extracts button/dialog texts, and compares
them against the _BTN_* translation sets in automator.py.

Usage:
    python scripts/explore_xg_dialogs.py [XG_INSTALL_DIR]

    If XG_INSTALL_DIR is not given, checks common install paths.
"""

import io
import os
import re
import sys
from pathlib import Path

# Ensure stdout can handle Unicode (Japanese, Greek, Russian, etc.)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ankigammon.utils.xg_auto.automator import XGAutomator


# XG language folder codes → human-readable names
LANG_CODES = {
    "US": "English",
    "DE": "German",
    "FR": "French",
    "ES": "Spanish",
    "JA": "Japanese",
    "GR": "Greek",
    "RU": "Russian",
}

# MSG DIALOG string IDs in STRINGS.TXT → our translation set names
MSG_DIALOG_IDS = {
    440: "_BTN_YES",
    441: "_BTN_OK",
    442: "_BTN_NO",
    443: "_BTN_CANCEL",
}

# Additional STRINGS.TXT IDs for common button texts.
# These come from XG's TMainForm and various dialogs.
EXTRA_STRING_IDS = {
    238: "_BTN_SAVE",       # "Save Game" title, but button text = "Save"
    340: "_BTN_CLOSE",      # Close (used in multiple dialogs)
}

# DLG files contain button definitions in format:
#   ButtonName=1=TButtonX
#   ButtonName:Caption=1=Button Text
# We map known button control names to our translation sets.
DLG_BUTTON_PATTERNS = {
    # DlgAnalyze.txt
    "Close1:Caption":  "_BTN_CLOSE",
    "Help1:Caption":   "_BTN_HELP",
    # DlgImport.txt
    "Open1:Caption":   "_BTN_OPEN",
    # DlgProgress.txt  (analysis progress dialog)
    # DlgStart.txt     (start screen)
}


def find_xg_install() -> Path | None:
    """Search common XG installation directories."""
    candidates = [
        Path(r"D:\Program Files (x86)\eXtreme Gammon 2"),
        Path(r"C:\Program Files (x86)\eXtreme Gammon 2"),
        Path(r"D:\Program Files\eXtreme Gammon 2"),
        Path(r"C:\Program Files\eXtreme Gammon 2"),
    ]
    for p in candidates:
        if (p / "XGLanguage").is_dir():
            return p
    return None


def parse_strings_txt(filepath: Path) -> dict[int, str]:
    """Parse a STRINGS.TXT file into {id: text} mapping.

    Format: lines like '440,Yes' in the MSG DIALOG section, or
    general 'ID,Text' lines throughout the file.
    """
    entries = {}
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return entries

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("//") or line.startswith("*"):
            continue
        # Format: "<lang_index>=<string_id>=<text>"
        # US=0, DE=1, FR=2, ES=3, JA=4, GR=5, RU=6
        match = re.match(r"^\d+=(\d+)=(.+)$", line)
        if match:
            str_id = int(match.group(1))
            text = match.group(2).strip()
            entries[str_id] = text

    return entries


def parse_dlg_file(filepath: Path) -> dict[str, str]:
    """Parse a DLG file into {ControlName:Property: text} mapping.

    Format: 'ControlName:Caption=1=Button Text'
    """
    entries = {}
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return entries

    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        # Format: "Close1:Caption=1=Schließen"
        match = re.match(r"^(\w+:\w+)=\d+=(.+)$", line)
        if match:
            key = match.group(1)
            value = match.group(2).strip()
            entries[key] = value

    return entries


def get_translation_sets() -> dict[str, set[str]]:
    """Extract the _BTN_* translation sets from XGAutomator."""
    return {
        "_BTN_OK":       XGAutomator._BTN_OK,
        "_BTN_YES":      XGAutomator._BTN_YES,
        "_BTN_NO":       XGAutomator._BTN_NO,
        "_BTN_CANCEL":   XGAutomator._BTN_CANCEL,
        "_BTN_OPEN":     XGAutomator._BTN_OPEN,
        "_BTN_CLOSE":    XGAutomator._BTN_CLOSE,
        "_BTN_SAVE":     XGAutomator._BTN_SAVE,
        "_BTN_IMPORT":   XGAutomator._BTN_IMPORT,
        "_BTN_CONTINUE": XGAutomator._BTN_CONTINUE,
        "_BTN_HELP":     XGAutomator._BTN_HELP,
        "_BTN_LOAD":     XGAutomator._BTN_LOAD,
    }


def validate_text(text: str, set_name: str, sets: dict[str, set[str]],
                   lang: str, source: str) -> str | None:
    """Check if text (lowercased) is in the expected translation set.

    Returns an error message if missing, or None if OK.
    """
    btn_set = sets.get(set_name)
    if btn_set is None:
        return f"  Unknown set {set_name}"

    # Normalize: strip accelerator keys (&), keyboard hints, trailing dots
    normalized = text.replace("&", "").strip()
    # Strip parenthetical keyboard hints first (e.g. "(H)" from "ヘルプ(H)")
    # Use fullwidth parens too: （ ）
    normalized = re.sub(r"\s*[(\uff08][A-Za-z][)\uff09]\s*$", "", normalized)
    # Strip trailing ellipsis/dots (e.g. "Öffnen ..." → "Öffnen")
    normalized = re.sub(r"[\s.]+$", "", normalized)
    normalized = normalized.lower()

    if not normalized or normalized == "ok":
        # "Ok" is universal, always present
        return None

    if normalized in btn_set:
        return None

    return (
        f"  MISSING: {lang} {source}: {text!r} (normalized: {normalized!r}) "
        f"not in {set_name} = {btn_set}"
    )


def main():
    print("XG Translation Table Validator")
    print("=" * 60)

    # Find XG installation
    if len(sys.argv) > 1:
        xg_dir = Path(sys.argv[1])
    else:
        xg_dir = find_xg_install()

    if not xg_dir or not (xg_dir / "XGLanguage").is_dir():
        print("ERROR: Cannot find XG installation with XGLanguage folder.")
        print("Usage: python scripts/explore_xg_dialogs.py [XG_INSTALL_DIR]")
        sys.exit(1)

    lang_root = xg_dir / "XGLanguage"
    print(f"XG install: {xg_dir}")
    print(f"Languages:  {lang_root}")

    sets = get_translation_sets()
    print(f"\nLoaded {len(sets)} translation sets from automator.py")
    for name, s in sorted(sets.items()):
        print(f"  {name:18s} ({len(s):2d} entries): {s}")

    errors = []
    all_texts: dict[str, dict[str, list[tuple[str, str]]]] = {}
    # {lang: {set_name: [(text, source), ...]}}

    print(f"\n{'=' * 60}")
    print("Scanning language files...")
    print(f"{'=' * 60}")

    for code, name in sorted(LANG_CODES.items()):
        lang_dir = lang_root / code
        if not lang_dir.is_dir():
            print(f"\n  WARNING: {code}/ directory not found, skipping")
            continue

        print(f"\n--- {name} ({code}) ---")
        all_texts[code] = {}

        # 1. Parse STRINGS.TXT for MSG DIALOG buttons
        strings_file = lang_dir / "STRINGS.TXT"
        strings = parse_strings_txt(strings_file)

        if strings:
            print(f"  STRINGS.TXT: {len(strings)} entries")
        else:
            print(f"  WARNING: STRINGS.TXT not found or empty")

        for str_id, set_name in MSG_DIALOG_IDS.items():
            text = strings.get(str_id)
            if text:
                print(f"    ID {str_id} ({set_name:15s}): {text!r}")
                all_texts[code].setdefault(set_name, []).append(
                    (text, f"STRINGS.TXT ID {str_id}")
                )
                err = validate_text(text, set_name, sets, code, f"STRINGS.TXT ID {str_id}")
                if err:
                    errors.append(err)
            else:
                print(f"    ID {str_id} ({set_name:15s}): NOT FOUND")

        # 2. Check extra string IDs
        for str_id, set_name in EXTRA_STRING_IDS.items():
            text = strings.get(str_id)
            if text:
                # These are often full phrases like "Save Game" — extract
                # just the verb/action word for validation
                print(f"    ID {str_id} ({set_name:15s}): {text!r} (title/label)")

        # 3. Parse DLG files for button captions
        dlg_files = sorted(lang_dir.glob("*.txt"))
        dlg_files = [f for f in dlg_files if f.name != "STRINGS.TXT"]

        for dlg_file in dlg_files:
            dlg_entries = parse_dlg_file(dlg_file)
            if not dlg_entries:
                continue

            for key, set_name in DLG_BUTTON_PATTERNS.items():
                text = dlg_entries.get(key)
                if text:
                    print(f"    {dlg_file.name} {key}: {text!r} → {set_name}")
                    all_texts[code].setdefault(set_name, []).append(
                        (text, f"{dlg_file.name} {key}")
                    )
                    err = validate_text(text, set_name, sets, code, f"{dlg_file.name} {key}")
                    if err:
                        errors.append(err)

            # Also scan for any button captions containing known patterns
            for entry_key, entry_val in dlg_entries.items():
                if ":Caption" not in entry_key and ":Hint" not in entry_key:
                    continue
                val_lower = entry_val.replace("&", "").strip().lower()
                for sname, svalues in sets.items():
                    if val_lower in svalues and val_lower not in ("ok", "no"):
                        # Found a match — record it
                        all_texts[code].setdefault(sname, []).append(
                            (entry_val, f"{dlg_file.name} {entry_key}")
                        )

    # Summary
    print(f"\n\n{'=' * 60}")
    print("VALIDATION RESULTS")
    print(f"{'=' * 60}")

    if errors:
        print(f"\n  ERRORS FOUND: {len(errors)}")
        for err in errors:
            print(err)
        print("\n  Fix these in automator.py's _BTN_* sets!")
    else:
        print("\n  ALL CHECKS PASSED — translation tables match XG language files.")

    # Cross-reference: check that every language has entries for the
    # core MSG DIALOG buttons
    print(f"\n{'=' * 60}")
    print("COVERAGE MATRIX (MSG DIALOG buttons)")
    print(f"{'=' * 60}")

    header = f"  {'Lang':<6}"
    for set_name in MSG_DIALOG_IDS.values():
        header += f" {set_name:>15}"
    print(header)
    print("  " + "-" * (6 + 16 * len(MSG_DIALOG_IDS)))

    for code in sorted(LANG_CODES.keys()):
        row = f"  {code:<6}"
        lang_data = all_texts.get(code, {})
        for set_name in MSG_DIALOG_IDS.values():
            entries = lang_data.get(set_name, [])
            if entries:
                text = entries[0][0]
                row += f" {text:>15}"
            else:
                row += f" {'???':>15}"
        print(row)

    # Also show what's in our sets that wasn't found in any language file
    print(f"\n{'=' * 60}")
    print("REVERSE CHECK: entries in _BTN_* sets not found in XG files")
    print(f"{'=' * 60}")

    all_found_texts = set()
    for code_data in all_texts.values():
        for entries in code_data.values():
            for text, _ in entries:
                all_found_texts.add(text.replace("&", "").strip().lower())

    # Add universal entries
    all_found_texts.add("ok")

    orphans_found = False
    for sname, svalues in sorted(sets.items()):
        for val in sorted(svalues):
            if val not in all_found_texts:
                if not orphans_found:
                    print()
                    orphans_found = True
                print(f"  {sname}: {val!r} — not found in any XG language file")
                print(f"    (may be a Windows common dialog string, which is OK)")

    if not orphans_found:
        print("\n  All entries in translation sets are accounted for.")

    print(f"\n{'=' * 60}")
    print("Done.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
