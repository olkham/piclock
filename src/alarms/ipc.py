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

_DEFAULT_TIMER_STATE = {
    "duration": 0,        # total seconds set by user
    "remaining": 0,       # seconds remaining (countdown)
    "label": "",          # user-defined label
    "running": False,     # actively counting down
    "started_at": 0,      # time.time() when started (engine-side)
    "finished": False,    # True when countdown reached zero
    "sound": "default",   # alarm sound to play on finish
    "sound_enabled": True,
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
    os.makedirs(_DATA_DIR, exist_ok=True)
    payload = {"cmd": cmd, "ts": time.time(), **kwargs}
    tmp = _CMD_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    for _ in range(5):
        try:
            os.replace(tmp, _CMD_FILE)
            return
        except PermissionError:
            time.sleep(0.02)
    os.replace(tmp, _CMD_FILE)


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
    os.makedirs(_DATA_DIR, exist_ok=True)
    state = {"active": True, "alarm": alarm_info} if alarm_info else {"active": False}
    tmp = _STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    for _ in range(5):
        try:
            os.replace(tmp, _STATE_FILE)
            return
        except PermissionError:
            time.sleep(0.02)
    os.replace(tmp, _STATE_FILE)


# ---------------------------------------------------------------------------
# Dial state — cross-process state for dial mode
# ---------------------------------------------------------------------------

def read_dial_state():
    """Read dial state from disk. Returns dict with defaults for missing keys."""
    data = {}
    for _ in range(5):
        try:
            with open(_DIAL_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            break
        except (FileNotFoundError, json.JSONDecodeError):
            break
        except PermissionError:
            time.sleep(0.02)
    result = dict(_DEFAULT_DIAL_STATE)
    result.update(data)
    return result


def write_dial_state(state):
    """Write dial state to disk (atomic, with retry for Windows file locks)."""
    os.makedirs(_DATA_DIR, exist_ok=True)
    tmp = _DIAL_STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    for _ in range(5):
        try:
            os.replace(tmp, _DIAL_STATE_FILE)
            return
        except PermissionError:
            time.sleep(0.02)
    # Last attempt — let it raise if still locked
    os.replace(tmp, _DIAL_STATE_FILE)


def reset_dial_state():
    """Reset dial state to defaults."""
    write_dial_state(dict(_DEFAULT_DIAL_STATE))


# ---------------------------------------------------------------------------
# Timer state — cross-process state for timer mode
# ---------------------------------------------------------------------------

def read_timer_state():
    """Read timer state from disk. Returns dict with defaults for missing keys."""
    data = {}
    for _ in range(5):
        try:
            with open(_TIMER_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            break
        except (FileNotFoundError, json.JSONDecodeError):
            break
        except PermissionError:
            time.sleep(0.02)
    result = dict(_DEFAULT_TIMER_STATE)
    result.update(data)
    return result


def write_timer_state(state):
    """Write timer state to disk (atomic, with retry for Windows file locks)."""
    os.makedirs(_DATA_DIR, exist_ok=True)
    tmp = _TIMER_STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    for _ in range(5):
        try:
            os.replace(tmp, _TIMER_STATE_FILE)
            return
        except PermissionError:
            time.sleep(0.02)
    os.replace(tmp, _TIMER_STATE_FILE)


def reset_timer_state():
    """Reset timer state to defaults."""
    write_timer_state(dict(_DEFAULT_TIMER_STATE))
