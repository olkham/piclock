"""Dial theme manager — CRUD, loading, and activation for dial face designs."""

import json
import os

from src.themes.schema import (
    DEFAULT_DIAL_THEME,
    merge_dial_theme_with_defaults,
    validate_dial_theme,
)

_DIAL_THEMES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "dial_themes"
)


def _theme_path(name):
    safe = name.replace(os.sep, "_").replace("/", "_")
    return os.path.join(_DIAL_THEMES_DIR, f"{safe}.json")


class DialThemeManager:
    """Manages dial theme storage, retrieval, and activation."""

    def __init__(self, settings):
        self._settings = settings
        self._cache = {}
        self._mtimes = {}
        self._load_defaults()

    def _load_defaults(self):
        os.makedirs(_DIAL_THEMES_DIR, exist_ok=True)
        for filename in os.listdir(_DIAL_THEMES_DIR):
            if filename.endswith(".json"):
                path = os.path.join(_DIAL_THEMES_DIR, filename)
                try:
                    with open(path, "r") as f:
                        theme = json.load(f)
                    theme = merge_dial_theme_with_defaults(theme)
                    self._cache[theme["name"]] = theme
                    self._mtimes[path] = os.path.getmtime(path)
                except (json.JSONDecodeError, KeyError, OSError):
                    continue

        if DEFAULT_DIAL_THEME["name"] not in self._cache:
            self._cache[DEFAULT_DIAL_THEME["name"]] = DEFAULT_DIAL_THEME
            self._save_to_file(DEFAULT_DIAL_THEME)

    def _refresh_from_disk(self):
        try:
            filenames = os.listdir(_DIAL_THEMES_DIR)
        except OSError:
            return
        for filename in filenames:
            if not filename.endswith(".json"):
                continue
            path = os.path.join(_DIAL_THEMES_DIR, filename)
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if mtime != self._mtimes.get(path):
                try:
                    with open(path, "r") as f:
                        theme = json.load(f)
                    theme = merge_dial_theme_with_defaults(theme)
                    self._cache[theme["name"]] = theme
                    self._mtimes[path] = mtime
                except (json.JSONDecodeError, KeyError, OSError):
                    continue

    def _save_to_file(self, theme):
        path = _theme_path(theme["name"])
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(theme, f, indent=2)
        os.replace(tmp, path)
        try:
            self._mtimes[path] = os.path.getmtime(path)
        except OSError:
            pass

    def list_themes(self):
        return sorted(self._cache.keys())

    def get_theme(self, name):
        return self._cache.get(name)

    def get_active_theme(self):
        self._refresh_from_disk()
        active_name = self._settings.get(
            "active_dial_theme", DEFAULT_DIAL_THEME["name"]
        )
        theme = self.get_theme(active_name)
        return theme if theme else DEFAULT_DIAL_THEME

    def set_active(self, name):
        if self.get_theme(name) is None:
            raise ValueError(f"Dial theme '{name}' not found")
        self._settings.set("active_dial_theme", name)

    def save_theme(self, theme):
        errors = validate_dial_theme(theme)
        if errors:
            raise ValueError(f"Invalid dial theme: {'; '.join(errors)}")
        theme = merge_dial_theme_with_defaults(theme)
        self._cache[theme["name"]] = theme
        self._save_to_file(theme)
        return theme

    def delete_theme(self, name):
        if name == DEFAULT_DIAL_THEME["name"]:
            raise ValueError("Cannot delete the built-in default dial theme")
        self._cache.pop(name, None)
        path = _theme_path(name)
        if os.path.exists(path):
            os.remove(path)
        if self._settings.get("active_dial_theme") == name:
            self._settings.set("active_dial_theme", DEFAULT_DIAL_THEME["name"])

    def export_theme(self, name):
        theme = self.get_theme(name)
        if theme is None:
            raise ValueError(f"Dial theme '{name}' not found")
        return json.dumps(theme, indent=2)

    def import_theme(self, json_str):
        theme = json.loads(json_str)
        return self.save_theme(theme)
