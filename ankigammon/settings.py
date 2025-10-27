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
        "deck_name": "My AnkiGammon Deck",
        "show_options": True,
        "interactive_moves": True,
        "export_method": "ankiconnect",
        "gnubg_path": None,
        "gnubg_analysis_ply": 3,
        "generate_score_matrix": False,
        "board_orientation": "counter-clockwise",
        "last_apkg_directory": None,
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
                # Merge with defaults to handle new settings
                settings = self.DEFAULT_SETTINGS.copy()
                settings.update(loaded)
                return settings
        except (json.JSONDecodeError, IOError):
            # If file is corrupted or unreadable, use defaults
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
    def deck_name(self) -> str:
        """Get the default deck name."""
        return self._settings.get("deck_name", "My AnkiGammon Deck")

    @deck_name.setter
    def deck_name(self, value: str) -> None:
        """Set the default deck name."""
        self.set("deck_name", value)

    @property
    def show_options(self) -> bool:
        """Get whether to show options on cards."""
        return self._settings.get("show_options", True)

    @show_options.setter
    def show_options(self, value: bool) -> None:
        """Set whether to show options on cards."""
        self.set("show_options", value)

    @property
    def interactive_moves(self) -> bool:
        """Get whether to enable interactive move visualization."""
        return self._settings.get("interactive_moves", True)

    @interactive_moves.setter
    def interactive_moves(self, value: bool) -> None:
        """Set whether to enable interactive move visualization."""
        self.set("interactive_moves", value)

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
    def board_orientation(self) -> str:
        """Get the board orientation (clockwise or counter-clockwise)."""
        return self._settings.get("board_orientation", "counter-clockwise")

    @board_orientation.setter
    def board_orientation(self, value: str) -> None:
        """Set the board orientation (clockwise or counter-clockwise)."""
        if value not in ["clockwise", "counter-clockwise"]:
            raise ValueError("board_orientation must be 'clockwise' or 'counter-clockwise'")
        self.set("board_orientation", value)

    @property
    def last_apkg_directory(self) -> Optional[str]:
        """Get the last directory used for APKG export."""
        return self._settings.get("last_apkg_directory", None)

    @last_apkg_directory.setter
    def last_apkg_directory(self, value: Optional[str]) -> None:
        """Set the last directory used for APKG export."""
        self.set("last_apkg_directory", value)

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
