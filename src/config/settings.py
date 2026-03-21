"""Configuration and settings backed by SQLite."""

import json
import os
import sqlite3
import threading

_DB_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
_DB_PATH = os.path.join(_DB_DIR, "piclock.db")
_lock = threading.Lock()


def _get_db_path():
    return os.environ.get("PICLOCK_DB", _DB_PATH)


def get_db():
    """Get a SQLite connection. Creates tables if needed."""
    path = _get_db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _ensure_tables(conn)
    return conn


def _ensure_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS themes (
            name TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS alarms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time TEXT NOT NULL,
            days TEXT,
            sound TEXT,
            enabled INTEGER DEFAULT 1,
            label TEXT DEFAULT '',
            animation_shape TEXT DEFAULT 'border_glow',
            animation_color TEXT DEFAULT '#ff3333',
            animation_speed TEXT DEFAULT 'normal',
            sound_enabled INTEGER DEFAULT 1,
            animation_duration INTEGER DEFAULT 60,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS agenda_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            color TEXT DEFAULT '#4488ff',
            days TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # Migrate existing alarms table if missing new columns
    try:
        conn.execute("SELECT animation_shape FROM alarms LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE alarms ADD COLUMN animation_shape TEXT DEFAULT 'border_glow'")
        conn.execute("ALTER TABLE alarms ADD COLUMN animation_color TEXT DEFAULT '#ff3333'")
        conn.execute("ALTER TABLE alarms ADD COLUMN animation_speed TEXT DEFAULT 'normal'")
    try:
        conn.execute("SELECT sound_enabled FROM alarms LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE alarms ADD COLUMN sound_enabled INTEGER DEFAULT 1")
    try:
        conn.execute("SELECT animation_duration FROM alarms LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE alarms ADD COLUMN animation_duration INTEGER DEFAULT 60")
    conn.commit()


def get_setting(key, default=None):
    """Get a setting value by key."""
    conn = get_db()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_setting(key, value):
    """Set a setting value."""
    conn = get_db()
    try:
        with _lock:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, str(value)),
            )
            conn.commit()
    finally:
        conn.close()


class Settings:
    """Dict-like interface over the settings table."""

    def get(self, key, default=None):
        return get_setting(key, default)

    def set(self, key, value):
        set_setting(key, value)

    def __getitem__(self, key):
        val = get_setting(key)
        if val is None:
            raise KeyError(key)
        return val

    def __setitem__(self, key, value):
        set_setting(key, value)

    def all(self):
        conn = get_db()
        try:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
            return {row["key"]: row["value"] for row in rows}
        finally:
            conn.close()
