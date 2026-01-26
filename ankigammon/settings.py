"""
Settings and configuration management for AnkiGammon.

Handles loading and saving user preferences such as color scheme selection.
"""

import json
import os
from pathlib import Path
from typing import Optional


class Settings:
    """Manages application settings with persistence."""

    DEFAULT_SETTINGS = {
        "default_color_scheme": "classic",
        "swap_checker_colors": False,
        "deck_name": "My AnkiGammon Deck",
        "use_subdecks_by_type": False,
        "clear_positions_after_export": True,
        "show_options": True,
        "show_pip_count": True,
        "score_format": "absolute",  # "absolute" or "away"
        "interactive_moves": True,
        "preview_moves_before_submit": False,
        "export_method": "ankiconnect",
        "gnubg_path": None,
        "gnubg_analysis_ply": 3,
        "generate_score_matrix": False,
        "generate_move_score_matrix": False,
        "board_orientation": "counter-clockwise",
        "last_apkg_directory": None,
        "import_checker_error_threshold": 0.080,
        "import_cube_error_threshold": 0.080,
        "import_include_player_x": True,
        "import_include_player_o": True,
        "import_selected_player_names": [],
        "max_mcq_options": 5,
        "check_for_updates": True,
        "last_update_check": None,
        "snooze_update_until": None,
    }

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize settings manager.

        Args:
            config_path: Path to config file. If None, uses default location.
        """
        if config_path is None:
            config_dir = Path.home() / ".ankigammon"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path = config_dir / "config.json"

        self.config_path = config_path
        self._settings = self._load()

    def _load(self) -> dict:
        """Load settings from config file."""
        if not self.config_path.exists():
            return self.DEFAULT_SETTINGS.copy()

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                # Merge with defaults to ensure new settings have default values
                settings = self.DEFAULT_SETTINGS.copy()
                settings.update(loaded)
                return settings
        except (json.JSONDecodeError, IOError):
            # Use defaults if file is corrupted or unreadable
            return self.DEFAULT_SETTINGS.copy()

    def _save(self) -> None:
        """Save settings to config file."""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self._settings, f, indent=2)
        except IOError:
            # Silently fail if unable to save
            pass

    def get(self, key: str, default=None):
        """Get a setting value."""
        return self._settings.get(key, default)

    def set(self, key: str, value) -> None:
        """Set a setting value and save to disk."""
        self._settings[key] = value
        self._save()

    @property
    def color_scheme(self) -> str:
        """Get the default color scheme."""
        return self._settings.get("default_color_scheme", "classic")

    @color_scheme.setter
    def color_scheme(self, value: str) -> None:
        """Set the default color scheme."""
        self.set("default_color_scheme", value)

    @property
    def swap_checker_colors(self) -> bool:
        """Get whether to swap checker colors (X uses light, O uses dark)."""
        return self._settings.get("swap_checker_colors", False)

    @swap_checker_colors.setter
    def swap_checker_colors(self, value: bool) -> None:
        """Set whether to swap checker colors."""
        self.set("swap_checker_colors", value)

    @property
    def deck_name(self) -> str:
        """Get the default deck name."""
        return self._settings.get("deck_name", "My AnkiGammon Deck")

    @deck_name.setter
    def deck_name(self, value: str) -> None:
        """Set the default deck name."""
        self.set("deck_name", value)

    @property
    def use_subdecks_by_type(self) -> bool:
        """Get whether to organize cards into subdecks by decision type."""
        return self._settings.get("use_subdecks_by_type", False)

    @use_subdecks_by_type.setter
    def use_subdecks_by_type(self, value: bool) -> None:
        """Set whether to organize cards into subdecks by decision type."""
        self.set("use_subdecks_by_type", value)

    @property
    def clear_positions_after_export(self) -> bool:
        """Get whether to clear the position list after successful export."""
        return self._settings.get("clear_positions_after_export", True)

    @clear_positions_after_export.setter
    def clear_positions_after_export(self, value: bool) -> None:
        """Set whether to clear the position list after successful export."""
        self.set("clear_positions_after_export", value)

    @property
    def show_options(self) -> bool:
        """Get whether to show options on cards."""
        return self._settings.get("show_options", True)

    @show_options.setter
    def show_options(self, value: bool) -> None:
        """Set whether to show options on cards."""
        self.set("show_options", value)

    @property
    def show_pip_count(self) -> bool:
        """Get whether to show pip counts on cards."""
        return self._settings.get("show_pip_count", True)

    @show_pip_count.setter
    def show_pip_count(self, value: bool) -> None:
        """Set whether to show pip counts on cards."""
        self.set("show_pip_count", value)

    @property
    def score_format(self) -> str:
        """Get score format for match play. Options: 'absolute' or 'away'."""
        return self._settings.get("score_format", "absolute")

    @score_format.setter
    def score_format(self, value: str) -> None:
        """Set score format for match play."""
        if value not in ("absolute", "away"):
            value = "absolute"
        self.set("score_format", value)

    @property
    def interactive_moves(self) -> bool:
        """Get whether to enable interactive move visualization."""
        return self._settings.get("interactive_moves", True)

    @interactive_moves.setter
    def interactive_moves(self, value: bool) -> None:
        """Set whether to enable interactive move visualization."""
        self.set("interactive_moves", value)

    @property
    def preview_moves_before_submit(self) -> bool:
        """Get whether to preview moves before submitting MCQ answer."""
        return self._settings.get("preview_moves_before_submit", False)

    @preview_moves_before_submit.setter
    def preview_moves_before_submit(self, value: bool) -> None:
        """Set whether to preview moves before submitting MCQ answer."""
        self.set("preview_moves_before_submit", value)

    @property
    def export_method(self) -> str:
        """Get the default export method."""
        return self._settings.get("export_method", "ankiconnect")

    @export_method.setter
    def export_method(self, value: str) -> None:
        """Set the default export method."""
        self.set("export_method", value)

    @property
    def gnubg_path(self) -> Optional[str]:
        """Get the GnuBG executable path."""
        return self._settings.get("gnubg_path", None)

    @gnubg_path.setter
    def gnubg_path(self, value: Optional[str]) -> None:
        """Set the GnuBG executable path."""
        self.set("gnubg_path", value)

    @property
    def gnubg_analysis_ply(self) -> int:
        """Get the GnuBG analysis depth (ply)."""
        return self._settings.get("gnubg_analysis_ply", 3)

    @gnubg_analysis_ply.setter
    def gnubg_analysis_ply(self, value: int) -> None:
        """Set the GnuBG analysis depth (ply)."""
        self.set("gnubg_analysis_ply", value)

    @property
    def generate_score_matrix(self) -> bool:
        """Get whether to generate score matrix for cube decisions."""
        return self._settings.get("generate_score_matrix", False)

    @generate_score_matrix.setter
    def generate_score_matrix(self, value: bool) -> None:
        """Set whether to generate score matrix for cube decisions."""
        self.set("generate_score_matrix", value)

    @property
    def generate_move_score_matrix(self) -> bool:
        """Get whether to generate move score matrix for checker play decisions."""
        return self._settings.get("generate_move_score_matrix", False)

    @generate_move_score_matrix.setter
    def generate_move_score_matrix(self, value: bool) -> None:
        """Set whether to generate move score matrix for checker play decisions."""
        self.set("generate_move_score_matrix", value)

    @property
    def board_orientation(self) -> str:
        """Get the board orientation (clockwise or counter-clockwise)."""
        return self._settings.get("board_orientation", "counter-clockwise")

    @board_orientation.setter
    def board_orientation(self, value: str) -> None:
        """Set the board orientation (clockwise, counter-clockwise, or random)."""
        if value not in ["clockwise", "counter-clockwise", "random"]:
            raise ValueError("board_orientation must be 'clockwise', 'counter-clockwise', or 'random'")
        self.set("board_orientation", value)

    @property
    def last_apkg_directory(self) -> Optional[str]:
        """Get the last directory used for APKG export."""
        return self._settings.get("last_apkg_directory", None)

    @last_apkg_directory.setter
    def last_apkg_directory(self, value: Optional[str]) -> None:
        """Set the last directory used for APKG export."""
        self.set("last_apkg_directory", value)

    @property
    def import_checker_error_threshold(self) -> float:
        """Get the error threshold for checker play decisions."""
        return self._settings.get("import_checker_error_threshold", 0.080)

    @import_checker_error_threshold.setter
    def import_checker_error_threshold(self, value: float) -> None:
        """Set the error threshold for checker play decisions."""
        self.set("import_checker_error_threshold", value)

    @property
    def import_cube_error_threshold(self) -> float:
        """Get the error threshold for cube decisions."""
        return self._settings.get("import_cube_error_threshold", 0.080)

    @import_cube_error_threshold.setter
    def import_cube_error_threshold(self, value: float) -> None:
        """Set the error threshold for cube decisions."""
        self.set("import_cube_error_threshold", value)

    @property
    def import_include_player_x(self) -> bool:
        """Get whether to include Player X mistakes in imports."""
        return self._settings.get("import_include_player_x", True)

    @import_include_player_x.setter
    def import_include_player_x(self, value: bool) -> None:
        """Set whether to include Player X mistakes in imports."""
        self.set("import_include_player_x", value)

    @property
    def import_include_player_o(self) -> bool:
        """Get whether to include Player O mistakes in imports."""
        return self._settings.get("import_include_player_o", True)

    @import_include_player_o.setter
    def import_include_player_o(self, value: bool) -> None:
        """Set whether to include Player O mistakes in imports."""
        self.set("import_include_player_o", value)

    @property
    def import_selected_player_names(self) -> list[str]:
        """Get the list of previously selected player names."""
        return self._settings.get("import_selected_player_names", [])

    @import_selected_player_names.setter
    def import_selected_player_names(self, value: list[str]) -> None:
        """Set the list of previously selected player names."""
        if not isinstance(value, list):
            value = []

        validated = []
        seen = set()
        for name in value:
            if not isinstance(name, str):
                continue

            trimmed = name.strip()
            if not trimmed:
                continue

            # Case-insensitive deduplication
            key = trimmed.lower()
            if key not in seen:
                seen.add(key)
                validated.append(trimmed)

        self.set("import_selected_player_names", validated)

    @property
    def max_mcq_options(self) -> int:
        """Get the maximum number of MCQ options to display."""
        return self._settings.get("max_mcq_options", 5)

    @max_mcq_options.setter
    def max_mcq_options(self, value: int) -> None:
        """Set the maximum number of MCQ options to display."""
        if value < 2 or value > 10:
            raise ValueError("max_mcq_options must be between 2 and 10")
        self.set("max_mcq_options", value)

    @property
    def check_for_updates(self) -> bool:
        """Get whether to check for updates on startup."""
        return self._settings.get("check_for_updates", True)

    @check_for_updates.setter
    def check_for_updates(self, value: bool) -> None:
        """Set whether to check for updates on startup."""
        self.set("check_for_updates", value)

    @property
    def last_update_check(self) -> Optional[str]:
        """Get the timestamp of the last update check (ISO format)."""
        return self._settings.get("last_update_check", None)

    @last_update_check.setter
    def last_update_check(self, value: Optional[str]) -> None:
        """Set the timestamp of the last update check (ISO format)."""
        self.set("last_update_check", value)

    @property
    def snooze_update_until(self) -> Optional[str]:
        """Get the timestamp to snooze update notifications until (ISO format)."""
        return self._settings.get("snooze_update_until", None)

    @snooze_update_until.setter
    def snooze_update_until(self, value: Optional[str]) -> None:
        """Set the timestamp to snooze update notifications until (ISO format)."""
        self.set("snooze_update_until", value)

    def is_gnubg_available(self) -> bool:
        """
        Check if GnuBG is configured and accessible.

        Returns:
            True if gnubg_path is set and the file exists and is executable.
        """
        path = self.gnubg_path
        if path is None:
            return False
        try:
            path_obj = Path(path)
            return path_obj.exists() and os.access(path, os.X_OK)
        except (OSError, ValueError):
            return False


# Global settings instance
_settings = None


def get_settings() -> Settings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
