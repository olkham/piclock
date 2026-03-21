"""Theme manager — CRUD operations, loading, and activation."""

import json
import os

from src.config.settings import get_db
from src.themes.schema import DEFAULT_THEME, merge_with_defaults, validate_theme


_THEMES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "themes")


class ThemeManager:
    """Manages theme storage, retrieval, and activation."""

    def __init__(self, settings):
        self._settings = settings
        self._cache = {}
        self._load_defaults()

    def _load_defaults(self):
        """Load default themes from JSON files on disk."""
        os.makedirs(_THEMES_DIR, exist_ok=True)
        for filename in os.listdir(_THEMES_DIR):
            if filename.endswith(".json"):
                path = os.path.join(_THEMES_DIR, filename)
                try:
                    with open(path, "r") as f:
                        theme = json.load(f)
                    theme = merge_with_defaults(theme)
                    self._cache[theme["name"]] = theme
                    self._save_to_db(theme)
                except (json.JSONDecodeError, KeyError):
                    continue

        # Ensure at least the built-in default exists
        if DEFAULT_THEME["name"] not in self._cache:
            self._cache[DEFAULT_THEME["name"]] = DEFAULT_THEME
            self._save_to_db(DEFAULT_THEME)

    def _save_to_db(self, theme):
        conn = get_db()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO themes (name, data) VALUES (?, ?)",
                (theme["name"], json.dumps(theme)),
            )
            conn.commit()
        finally:
            conn.close()

    def list_themes(self):
        """Return a list of all theme names."""
        conn = get_db()
        try:
            rows = conn.execute("SELECT name FROM themes ORDER BY name").fetchall()
            return [row["name"] for row in rows]
        finally:
            conn.close()

    def get_theme(self, name):
        """Get a theme by name."""
        if name in self._cache:
            return self._cache[name]
        conn = get_db()
        try:
            row = conn.execute("SELECT data FROM themes WHERE name = ?", (name,)).fetchone()
            if row:
                theme = json.loads(row["data"])
                self._cache[name] = theme
                return theme
        finally:
            conn.close()
        return None

    def get_active_theme(self):
        """Get the currently active theme."""
        active_name = self._settings.get("active_theme", DEFAULT_THEME["name"])
        theme = self.get_theme(active_name)
        return theme if theme else DEFAULT_THEME

    def set_active(self, name):
        """Set the active theme by name."""
        if self.get_theme(name) is None:
            raise ValueError(f"Theme '{name}' not found")
        self._settings.set("active_theme", name)

    def save_theme(self, theme):
        """Save or update a theme."""
        errors = validate_theme(theme)
        if errors:
            raise ValueError(f"Invalid theme: {'; '.join(errors)}")
        theme = merge_with_defaults(theme)
        self._cache[theme["name"]] = theme
        self._save_to_db(theme)
        return theme

    def delete_theme(self, name):
        """Delete a theme by name. Cannot delete the built-in default."""
        if name == DEFAULT_THEME["name"]:
            raise ValueError("Cannot delete the built-in default theme")
        self._cache.pop(name, None)
        conn = get_db()
        try:
            conn.execute("DELETE FROM themes WHERE name = ?", (name,))
            conn.commit()
        finally:
            conn.close()

        # If this was the active theme, revert to default
        if self._settings.get("active_theme") == name:
            self._settings.set("active_theme", DEFAULT_THEME["name"])

    def export_theme(self, name):
        """Export a theme as a JSON string."""
        theme = self.get_theme(name)
        if theme is None:
            raise ValueError(f"Theme '{name}' not found")
        return json.dumps(theme, indent=2)

    def import_theme(self, json_str):
        """Import a theme from a JSON string."""
        theme = json.loads(json_str)
        return self.save_theme(theme)
