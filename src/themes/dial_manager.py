"""Dial theme manager — CRUD, loading, and activation for dial face designs."""

import os

from src.themes.base import BaseThemeManager
from src.themes.schema import (
    DEFAULT_DIAL_THEME,
    merge_dial_theme_with_defaults,
    validate_dial_theme,
)

_DIAL_THEMES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "dial_themes"
)


class DialThemeManager(BaseThemeManager):
    """Manages dial theme storage, retrieval, and activation."""

    def __init__(self, settings):
        super().__init__(
            settings,
            themes_dir=_DIAL_THEMES_DIR,
            default_theme=DEFAULT_DIAL_THEME,
            merge_fn=merge_dial_theme_with_defaults,
            validate_fn=validate_dial_theme,
            setting_key="active_dial_theme",
        )
