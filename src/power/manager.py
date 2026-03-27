"""Power management — display brightness, dimming schedules, battery monitoring."""

import os
import threading
from datetime import datetime
from zoneinfo import ZoneInfo


# Backlight sysfs path (common for Pi HDMI displays)
_BACKLIGHT_PATH = "/sys/class/backlight"


class PowerManager:
    """Manages display brightness and power schedules."""

    def __init__(self, settings):
        self._settings = settings
        self._timer = None
        self._running = False

    def start(self):
        self._running = True
        self._schedule_check()

    def stop(self):
        self._running = False
        if self._timer:
            self._timer.cancel()

    def _schedule_check(self):
        if not self._running:
            return
        self._apply_schedule()
        self._timer = threading.Timer(60, self._schedule_check)
        self._timer.daemon = True
        self._timer.start()

    def _apply_schedule(self):
        """Check if we should dim/brighten based on schedule."""
        dim_start = self._settings.get("dim_start")  # e.g., "22:00"
        dim_end = self._settings.get("dim_end")      # e.g., "07:00"
        dim_level = int(self._settings.get("dim_brightness", "30"))
        bright_level = int(self._settings.get("brightness", "100"))

        if not dim_start or not dim_end:
            return

        tz_name = self._settings.get("timezone", "UTC")
        try:
            tz = ZoneInfo(tz_name)
        except (KeyError, ValueError):
            tz = ZoneInfo("UTC")
        now = datetime.now(tz)
        current = now.hour * 60 + now.minute
        start = _parse_time_minutes(dim_start)
        end = _parse_time_minutes(dim_end)

        if start is None or end is None:
            return

        # Check if current time is in dim period
        if start <= end:
            in_dim = start <= current < end
        else:
            # Wraps midnight (e.g., 22:00 - 07:00)
            in_dim = current >= start or current < end

        target = dim_level if in_dim else bright_level
        self.set_brightness(target)

    @staticmethod
    def _find_backlight_files():
        """Return (brightness_file, max_brightness_file) or (None, None)."""
        if not os.path.isdir(_BACKLIGHT_PATH):
            return None, None
        for entry in os.listdir(_BACKLIGHT_PATH):
            bf = os.path.join(_BACKLIGHT_PATH, entry, "brightness")
            mf = os.path.join(_BACKLIGHT_PATH, entry, "max_brightness")
            if os.path.isfile(bf) and os.path.isfile(mf):
                return bf, mf
        return None, None

    @staticmethod
    def set_brightness(level):
        """Set display brightness (0-100). Only works on Pi with backlight sysfs."""
        bf, mf = PowerManager._find_backlight_files()
        if bf is None:
            return
        try:
            with open(mf, "r") as f:
                max_val = int(f.read().strip())
            target = int(max_val * level / 100)
            with open(bf, "w") as f:
                f.write(str(target))
        except (OSError, ValueError):
            pass

    @staticmethod
    def get_brightness():
        """Read current brightness level. Returns None if not available."""
        bf, mf = PowerManager._find_backlight_files()
        if bf is None:
            return None
        try:
            with open(mf, "r") as f:
                max_val = int(f.read().strip())
            with open(bf, "r") as f:
                current = int(f.read().strip())
            return int(current * 100 / max_val) if max_val > 0 else 0
        except (OSError, ValueError):
            return None


def _parse_time_minutes(time_str):
    """Parse 'HH:MM' to minutes since midnight."""
    try:
        parts = time_str.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return None
