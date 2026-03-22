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
    os.replace(tmp, _CMD_FILE)


def read_alarm_state():
    """Read active alarm state written by the scheduler."""
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
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
    os.replace(tmp, _STATE_FILE)
