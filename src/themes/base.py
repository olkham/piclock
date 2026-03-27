"""Base theme manager — shared CRUD, loading, and disk-sync logic."""

import json
import os


class BaseThemeManager:
    """Generic theme manager parameterised by directory, defaults, and merge/validate functions."""

    def __init__(self, settings, *, themes_dir, default_theme,
                 merge_fn, validate_fn, setting_key):
        self._settings = settings
        self._themes_dir = themes_dir
        self._default_theme = default_theme
        self._merge_fn = merge_fn
        self._validate_fn = validate_fn
        self._setting_key = setting_key
        self._cache = {}
        self._mtimes = {}
        self._load_defaults()

    def _theme_path(self, name):
        safe = name.replace(os.sep, "_").replace("/", "_")
        return os.path.join(self._themes_dir, f"{safe}.json")

    def _load_defaults(self):
        os.makedirs(self._themes_dir, exist_ok=True)
        for filename in os.listdir(self._themes_dir):
            if filename.endswith(".json"):
                path = os.path.join(self._themes_dir, filename)
                try:
                    with open(path, "r") as f:
                        theme = json.load(f)
                    theme = self._merge_fn(theme)
                    self._cache[theme["name"]] = theme
                    self._mtimes[path] = os.path.getmtime(path)
                except (json.JSONDecodeError, KeyError, OSError):
                    continue

        if self._default_theme["name"] not in self._cache:
            self._cache[self._default_theme["name"]] = self._default_theme
            self._save_to_file(self._default_theme)

    def _refresh_from_disk(self):
        try:
            filenames = os.listdir(self._themes_dir)
        except OSError:
            return
        for filename in filenames:
            if not filename.endswith(".json"):
                continue
            path = os.path.join(self._themes_dir, filename)
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if mtime != self._mtimes.get(path):
                try:
                    with open(path, "r") as f:
                        theme = json.load(f)
                    theme = self._merge_fn(theme)
                    self._cache[theme["name"]] = theme
                    self._mtimes[path] = mtime
                except (json.JSONDecodeError, KeyError, OSError):
                    continue

    def _save_to_file(self, theme):
        path = self._theme_path(theme["name"])
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
        active_name = self._settings.get(self._setting_key, self._default_theme["name"])
        theme = self.get_theme(active_name)
        return theme if theme else self._default_theme

    def set_active(self, name):
        if self.get_theme(name) is None:
            raise ValueError(f"Theme '{name}' not found")
        self._settings.set(self._setting_key, name)

    def save_theme(self, theme):
        errors = self._validate_fn(theme)
        if errors:
            raise ValueError(f"Invalid theme: {'; '.join(errors)}")
        theme = self._merge_fn(theme)
        self._cache[theme["name"]] = theme
        self._save_to_file(theme)
        return theme

    def delete_theme(self, name):
        if name == self._default_theme["name"]:
            raise ValueError(f"Cannot delete the built-in default theme")
        self._cache.pop(name, None)
        path = self._theme_path(name)
        if os.path.exists(path):
            os.remove(path)
        if self._settings.get(self._setting_key) == name:
            self._settings.set(self._setting_key, self._default_theme["name"])

    def export_theme(self, name):
        theme = self.get_theme(name)
        if theme is None:
            raise ValueError(f"Theme '{name}' not found")
        return json.dumps(theme, indent=2)

    def import_theme(self, json_str):
        theme = json.loads(json_str)
        return self.save_theme(theme)
