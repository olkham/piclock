"""File-based IPC for alarm commands between Flask subprocess and main process.

When Flask runs in a separate OS process (for GIL isolation), it cannot
directly call AlarmScheduler methods.  Instead, Flask writes command/state
files that the scheduler polls and consumes.
"""

import json
import os
import time

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
_CMD_FILE = os.path.join(_DATA_DIR, ".alarm_cmd.json")
_STATE_FILE = os.path.join(_DATA_DIR, ".alarm_state.json")
_NUDGE_FILE = os.path.join(_DATA_DIR, ".nudge")
_DIAL_STATE_FILE = os.path.join(_DATA_DIR, ".dial_state.json")
_TIMER_STATE_FILE = os.path.join(_DATA_DIR, ".timer_state.json")


def _atomic_write_json(filepath, data):
    """Atomically write JSON to *filepath* with Windows retry for locks."""
    os.makedirs(_DATA_DIR, exist_ok=True)
    tmp = filepath + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    for _ in range(5):
        try:
            os.replace(tmp, filepath)
            return
        except PermissionError:
            time.sleep(0.02)
    os.replace(tmp, filepath)


def _read_json_with_defaults(filepath, defaults):
    """Read JSON from *filepath*, merging into *defaults*. Retries on lock."""
    data = {}
    for _ in range(5):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            break
        except (FileNotFoundError, json.JSONDecodeError):
            break
        except PermissionError:
            time.sleep(0.02)
    result = dict(defaults)
    result.update(data)
    return result


_DEFAULT_TIMER_STATE = {
    "duration": 0,        # total seconds set by user
    "remaining": 0,       # seconds remaining (countdown)
    "label": "",          # user-defined label
    "running": False,     # actively counting down
    "started_at": 0,      # time.time() when started (engine-side)
    "finished": False,    # True when countdown reached zero
    "sound": "default",   # alarm sound to play on finish
    "sound_enabled": True,
    # Label styling overrides (None = inherit from dial theme)
    "show_label": True,
    "label_offset_y": None,
    "label_font_size": None,
    "label_color": None,
    # Countdown (digital timer) styling overrides
    "show_time": True,
    "time_offset_y": None,
    "time_font_size": None,
    "time_color": None,
    # Alert animation styling
    "alert_shape": "border_glow",   # ring | flash | border_glow
    "alert_color": "#ff9900",
    "alert_speed": "normal",        # slow | normal | fast
    "alert_position": "bottom",     # top | center | bottom
}

_DEFAULT_DIAL_STATE = {
    "progress": 0,
    "min_value": 0,
    "max_value": 100,
    "text": "",
    "label": "",
    "progress_color": None,
    "text_color": None,
}


# ---------------------------------------------------------------------------
# Nudge — lightweight cross-process "something changed" signal
# ---------------------------------------------------------------------------

def write_nudge():
    """Signal the engine to reload data immediately (agenda, alarms, theme)."""
    os.makedirs(_DATA_DIR, exist_ok=True)
    try:
        with open(_NUDGE_FILE, "w") as f:
            f.write("")
    except OSError:
        pass


def check_nudge():
    """Check for and consume a nudge signal. Returns True if one was pending."""
    for _ in range(3):
        try:
            os.remove(_NUDGE_FILE)
            return True
        except FileNotFoundError:
            return False
        except PermissionError:
            time.sleep(0.01)
    return False


# ---------------------------------------------------------------------------
# Flask side — write commands, read state
# ---------------------------------------------------------------------------

def write_alarm_command(cmd, **kwargs):
    """Write an alarm command for the scheduler to pick up."""
    payload = {"cmd": cmd, "ts": time.time(), **kwargs}
    _atomic_write_json(_CMD_FILE, payload)


def read_alarm_state():
    """Read active alarm state written by the scheduler."""
    for _ in range(5):
        try:
            with open(_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"active": False}
        except PermissionError:
            time.sleep(0.02)
    return {"active": False}


# ---------------------------------------------------------------------------
# Scheduler side — read commands, write state
# ---------------------------------------------------------------------------

def read_alarm_command():
    """Read and consume a pending alarm command. Returns dict or None.

    Uses rename-then-read to avoid a TOCTOU race: if Flask writes a new
    command between our read and delete, we won't silently lose it.
    """
    consumed = _CMD_FILE + ".consumed"
    try:
        os.rename(_CMD_FILE, consumed)
    except (FileNotFoundError, OSError):
        return None
    try:
        with open(consumed, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    finally:
        try:
            os.unlink(consumed)
        except OSError:
            pass
    # Discard stale commands (older than 30 seconds)
    if time.time() - payload.get("ts", 0) > 30:
        return None
    return payload


def write_alarm_state(alarm_info):
    """Write active alarm state for Flask to read.

    Args:
        alarm_info: dict with alarm details, or None when no alarm is active.
    """
    state = {"active": True, "alarm": alarm_info} if alarm_info else {"active": False}
    _atomic_write_json(_STATE_FILE, state)


# ---------------------------------------------------------------------------
# Dial state — cross-process state for dial mode
# ---------------------------------------------------------------------------

def read_dial_state():
    """Read dial state from disk. Returns dict with defaults for missing keys."""
    return _read_json_with_defaults(_DIAL_STATE_FILE, _DEFAULT_DIAL_STATE)


def write_dial_state(state):
    """Write dial state to disk (atomic, with retry for Windows file locks)."""
    _atomic_write_json(_DIAL_STATE_FILE, state)


def reset_dial_state():
    """Reset dial state to defaults."""
    write_dial_state(dict(_DEFAULT_DIAL_STATE))


# ---------------------------------------------------------------------------
# Timer state — cross-process state for timer mode
# ---------------------------------------------------------------------------

def read_timer_state():
    """Read timer state from disk. Returns dict with defaults for missing keys."""
    return _read_json_with_defaults(_TIMER_STATE_FILE, _DEFAULT_TIMER_STATE)


def write_timer_state(state):
    """Write timer state to disk (atomic, with retry for Windows file locks)."""
    _atomic_write_json(_TIMER_STATE_FILE, state)


def reset_timer_state():
    """Reset timer state to defaults."""
    write_timer_state(dict(_DEFAULT_TIMER_STATE))
