from pathlib import Path

from conftest import REAL_HOME


def test_default_settings_never_touch_the_real_config():
    from ankigammon.settings import Settings

    settings = Settings()
    settings.set("deck_name", "home isolation test")

    assert settings.config_path != REAL_HOME / ".ankigammon" / "config.json"
    assert settings.config_path.parent == Path.home() / ".ankigammon"


def test_each_test_starts_with_a_fresh_settings_singleton():
    from ankigammon.settings import get_settings

    assert get_settings().deck_name != "home isolation test"
