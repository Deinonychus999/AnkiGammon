"""
Settings and configuration management for XG2Anki.

Handles loading and saving user preferences such as color scheme selection.
"""

import json
from pathlib import Path
from typing import Optional


class Settings:
    """Manages application settings with persistence."""

    DEFAULT_SETTINGS = {
        "default_color_scheme": "classic",
        "deck_name": "XG Backgammon",
        "show_options": True,
        "antialias_scale": 3,
        "interactive_moves": False,
    }

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize settings manager.

        Args:
            config_path: Path to config file. If None, uses default location.
        """
        if config_path is None:
            config_dir = Path.home() / ".xg2anki"
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
        return self._settings.get("deck_name", "XG Backgammon")

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
    def antialias_scale(self) -> int:
        """Get the antialiasing scale (1=off, 2-4=quality levels)."""
        return self._settings.get("antialias_scale", 3)

    @antialias_scale.setter
    def antialias_scale(self, value: int) -> None:
        """Set the antialiasing scale."""
        # Clamp value between 1 and 4
        value = max(1, min(4, int(value)))
        self.set("antialias_scale", value)

    @property
    def interactive_moves(self) -> bool:
        """Get whether to enable interactive move visualization."""
        return self._settings.get("interactive_moves", False)

    @interactive_moves.setter
    def interactive_moves(self, value: bool) -> None:
        """Set whether to enable interactive move visualization."""
        self.set("interactive_moves", value)


# Global settings instance
_settings = None


def get_settings() -> Settings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
