"""Face manager — CRUD operations for element-based faces.

Extends the same BaseThemeManager pattern used by clock/dial themes,
adding conversion of legacy themes on first load.
"""

import os

from src.themes.base import BaseThemeManager
from src.faces.schema import merge_face_defaults, validate_face, DEFAULT_CLOCK_FACE

_FACES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "faces")


class FaceManager(BaseThemeManager):
    """Manages face storage, retrieval, and activation."""

    def __init__(self, settings):
        super().__init__(
            settings,
            themes_dir=_FACES_DIR,
            default_theme=DEFAULT_CLOCK_FACE,
            merge_fn=merge_face_defaults,
            validate_fn=validate_face,
            setting_key="active_face",
        )

    def convert_and_import_clock_theme(self, theme):
        """Convert a legacy clock theme to a face and save it."""
        from src.faces.converter import convert_clock_theme
        face = convert_clock_theme(theme)
        face = merge_face_defaults(face)
        self._cache[face["name"]] = face
        self._save_to_file(face)
        return face

    def convert_and_import_dial_theme(self, dial_theme):
        """Convert a legacy dial theme to a face and save it."""
        from src.faces.converter import convert_dial_theme
        face = convert_dial_theme(dial_theme)
        face = merge_face_defaults(face)
        self._cache[face["name"]] = face
        self._save_to_file(face)
        return face
