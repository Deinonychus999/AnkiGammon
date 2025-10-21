"""Tests for settings persistence."""

import unittest
import tempfile
import json
from pathlib import Path

from flashgammon.settings import Settings


class TestSettings(unittest.TestCase):
    """Test settings management and persistence."""

    def setUp(self):
        """Create a temporary config file for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = Path(self.temp_dir) / "config.json"

    def test_default_settings(self):
        """Test that default settings are used when no config file exists."""
        settings = Settings(config_path=self.config_path)
        self.assertEqual(settings.color_scheme, "classic")
        self.assertEqual(settings.deck_name, "XG Backgammon")
        self.assertTrue(settings.show_options)

    def test_save_color_scheme(self):
        """Test saving color scheme preference."""
        settings = Settings(config_path=self.config_path)
        settings.color_scheme = "forest"

        # Verify file was created
        self.assertTrue(self.config_path.exists())

        # Verify content
        with open(self.config_path, 'r') as f:
            data = json.load(f)
        self.assertEqual(data["default_color_scheme"], "forest")

    def test_load_saved_settings(self):
        """Test loading previously saved settings."""
        # Save a setting
        settings1 = Settings(config_path=self.config_path)
        settings1.color_scheme = "ocean"

        # Load in a new instance
        settings2 = Settings(config_path=self.config_path)
        self.assertEqual(settings2.color_scheme, "ocean")

    def test_update_multiple_settings(self):
        """Test updating multiple settings."""
        settings = Settings(config_path=self.config_path)
        settings.color_scheme = "midnight"
        settings.deck_name = "My Custom Deck"
        settings.show_options = False

        # Reload and verify
        settings2 = Settings(config_path=self.config_path)
        self.assertEqual(settings2.color_scheme, "midnight")
        self.assertEqual(settings2.deck_name, "My Custom Deck")
        self.assertFalse(settings2.show_options)

    def test_corrupted_config_file(self):
        """Test that corrupted config file falls back to defaults."""
        # Create a corrupted config file
        with open(self.config_path, 'w') as f:
            f.write("{ invalid json }")

        settings = Settings(config_path=self.config_path)
        # Should fall back to defaults
        self.assertEqual(settings.color_scheme, "classic")

    def test_get_set_methods(self):
        """Test generic get/set methods."""
        settings = Settings(config_path=self.config_path)
        settings.set("custom_key", "custom_value")

        self.assertEqual(settings.get("custom_key"), "custom_value")
        self.assertIsNone(settings.get("nonexistent_key"))
        self.assertEqual(settings.get("nonexistent_key", "default"), "default")


if __name__ == '__main__':
    unittest.main()
