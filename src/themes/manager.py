"""Theme manager — CRUD operations, loading, and activation."""

import os

from src.themes.base import BaseThemeManager
from src.themes.schema import DEFAULT_THEME, merge_with_defaults, validate_theme

_THEMES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "themes")


class ThemeManager(BaseThemeManager):
    """Manages theme storage, retrieval, and activation."""

    def __init__(self, settings):
        super().__init__(
            settings,
            themes_dir=_THEMES_DIR,
            default_theme=DEFAULT_THEME,
            merge_fn=merge_with_defaults,
            validate_fn=validate_theme,
            setting_key="active_theme",
        )
