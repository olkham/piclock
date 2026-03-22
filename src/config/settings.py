"""Configuration and settings backed by JSON files."""

import json
import os
import threading

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
_SETTINGS_PATH = os.path.join(_DATA_DIR, "settings.json")
_ALARMS_PATH = os.path.join(_DATA_DIR, "alarms.json")
_AGENDA_PATH = os.path.join(_DATA_DIR, "agenda.json")
_lock = threading.Lock()
_next_alarm_id = 1
_next_event_id = 1


def _read_json(path, default=None):
    """Read a JSON file, returning default if it doesn't exist or is invalid."""
    if default is None:
        default = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write_json(path, data):
    """Write data to a JSON file atomically."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _init_ids():
    """Initialize auto-increment IDs from existing data."""
    global _next_alarm_id, _next_event_id
    alarms = _read_json(_ALARMS_PATH, [])
    if alarms:
        _next_alarm_id = max(a.get("id", 0) for a in alarms) + 1
    events = _read_json(_AGENDA_PATH, [])
    if events:
        _next_event_id = max(e.get("id", 0) for e in events) + 1


# --- Settings ---

def get_setting(key, default=None):
    """Get a setting value by key."""
    data = _read_json(_SETTINGS_PATH)
    return data.get(key, default)


def set_setting(key, value):
    """Set a setting value."""
    with _lock:
        data = _read_json(_SETTINGS_PATH)
        data[key] = value
        _write_json(_SETTINGS_PATH, data)


class Settings:
    """Dict-like interface over the settings JSON file."""

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
        return _read_json(_SETTINGS_PATH)


# --- Alarms ---

def list_alarms():
    """Return all alarms sorted by time."""
    alarms = _read_json(_ALARMS_PATH, [])
    return sorted(alarms, key=lambda a: a.get("time", ""))


def get_enabled_alarms():
    """Return all enabled alarms."""
    return [a for a in _read_json(_ALARMS_PATH, []) if a.get("enabled", True)]


def create_alarm(data):
    """Create a new alarm. Returns the alarm dict with assigned id."""
    global _next_alarm_id
    with _lock:
        alarms = _read_json(_ALARMS_PATH, [])
        alarm = {
            "id": _next_alarm_id,
            "time": data["time"],
            "days": data.get("days", ""),
            "sound": data.get("sound", "default"),
            "enabled": data.get("enabled", True),
            "label": data.get("label", ""),
            "animation_shape": data.get("animation_shape", "border_glow"),
            "animation_color": data.get("animation_color", "#ff3333"),
            "animation_speed": data.get("animation_speed", "normal"),
            "sound_enabled": data.get("sound_enabled", True),
            "animation_duration": int(data.get("animation_duration", 60)),
        }
        _next_alarm_id += 1
        alarms.append(alarm)
        _write_json(_ALARMS_PATH, alarms)
    return alarm


def update_alarm(alarm_id, data):
    """Update an alarm by id."""
    with _lock:
        alarms = _read_json(_ALARMS_PATH, [])
        for alarm in alarms:
            if alarm["id"] == alarm_id:
                alarm["time"] = data.get("time", alarm["time"])
                alarm["days"] = data.get("days", alarm.get("days", ""))
                alarm["sound"] = data.get("sound", alarm.get("sound", "default"))
                alarm["enabled"] = data.get("enabled", alarm.get("enabled", True))
                alarm["label"] = data.get("label", alarm.get("label", ""))
                alarm["animation_shape"] = data.get("animation_shape", alarm.get("animation_shape", "border_glow"))
                alarm["animation_color"] = data.get("animation_color", alarm.get("animation_color", "#ff3333"))
                alarm["animation_speed"] = data.get("animation_speed", alarm.get("animation_speed", "normal"))
                alarm["sound_enabled"] = data.get("sound_enabled", alarm.get("sound_enabled", True))
                alarm["animation_duration"] = int(data.get("animation_duration", alarm.get("animation_duration", 60)))
                _write_json(_ALARMS_PATH, alarms)
                return True
        return False


def disable_alarm(alarm_id):
    """Disable an alarm by id (for one-time alarms after firing)."""
    with _lock:
        alarms = _read_json(_ALARMS_PATH, [])
        for alarm in alarms:
            if alarm["id"] == alarm_id:
                alarm["enabled"] = False
                _write_json(_ALARMS_PATH, alarms)
                return True
        return False


def delete_alarm(alarm_id):
    """Delete an alarm by id."""
    with _lock:
        alarms = _read_json(_ALARMS_PATH, [])
        alarms = [a for a in alarms if a["id"] != alarm_id]
        _write_json(_ALARMS_PATH, alarms)


# --- Agenda Events ---

def list_agenda_events():
    """Return all agenda events sorted by start_time."""
    events = _read_json(_AGENDA_PATH, [])
    return sorted(events, key=lambda e: e.get("start_time", ""))


def create_agenda_event(data):
    """Create a new agenda event. Returns the event dict with assigned id."""
    global _next_event_id
    with _lock:
        events = _read_json(_AGENDA_PATH, [])
        event = {
            "id": _next_event_id,
            "title": data["title"],
            "start_time": data["start_time"],
            "end_time": data["end_time"],
            "color": data.get("color", "#4488ff"),
            "days": data.get("days", ""),
        }
        _next_event_id += 1
        events.append(event)
        _write_json(_AGENDA_PATH, events)
    return event


def update_agenda_event(event_id, data):
    """Update an agenda event by id."""
    with _lock:
        events = _read_json(_AGENDA_PATH, [])
        for event in events:
            if event["id"] == event_id:
                event["title"] = data.get("title", event["title"])
                event["start_time"] = data.get("start_time", event["start_time"])
                event["end_time"] = data.get("end_time", event["end_time"])
                event["color"] = data.get("color", event.get("color", "#4488ff"))
                event["days"] = data.get("days", event.get("days", ""))
                _write_json(_AGENDA_PATH, events)
                return True
        return False


def delete_agenda_event(event_id):
    """Delete an agenda event by id."""
    with _lock:
        events = _read_json(_AGENDA_PATH, [])
        events = [e for e in events if e["id"] != event_id]
        _write_json(_AGENDA_PATH, events)


# Initialize IDs on import
_init_ids()
