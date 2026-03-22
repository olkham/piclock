import time
import math
import platform
import signal
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

import pygame

from src.clock.renderer import render_frame
from src.clock.display import show_frame


def _is_pi_zero():
    """Detect Raspberry Pi Zero for performance fallback."""
    try:
        with open("/proc/device-tree/model", "r") as f:
            model = f.read().lower()
            return "pi zero" in model
    except Exception:
        return False


def _ease_in_out(t):
    """Smooth ease-in-out (sinusoidal)."""
    return 0.5 - 0.5 * math.cos(math.pi * t)


def _time_to_seconds(hour, minute, second, microsecond=0):
    """Convert time components to total seconds since midnight."""
    return hour * 3600 + minute * 60 + second + microsecond / 1_000_000


def _seconds_to_time_info(total_secs):
    """Convert total seconds to time_info dict, wrapping at 24h."""
    total_secs = total_secs % 86400
    if total_secs < 0:
        total_secs += 86400
    hour = int(total_secs // 3600)
    remainder = total_secs - hour * 3600
    minute = int(remainder // 60)
    sec_frac = remainder - minute * 60
    second = int(sec_frac)
    microsecond = int((sec_frac - second) * 1_000_000)
    return {
        "hour": hour,
        "minute": minute,
        "second": second,
        "microsecond": microsecond,
    }


class ClockEngine:
    """Main clock engine that drives the rendering loop."""

    def __init__(self, theme_manager, settings):
        self._theme_manager = theme_manager
        self._settings = settings
        self._running = False
        self._alarm_callback = None
        self._overlay_fn = None
        self._alarm_active = False
        self._alarms = []
        self._agenda_events = []
        self._agenda_last_load = 0
        self._is_pi_zero = _is_pi_zero()
        self._last_tz_name = None
        self._tz_transition_start = 0  # time.time() when transition began
        self._tz_transition_offset = 0  # seconds offset to animate away
        self._TZ_TRANSITION_DURATION = 1.0  # seconds

    def set_alarm_callback(self, callback):
        """Set a callback that returns overlay draw info when an alarm is active."""
        self._alarm_callback = callback

    def set_overlay(self, overlay_fn):
        """Set an overlay function called after rendering each frame."""
        self._overlay_fn = overlay_fn
        self._alarm_active = overlay_fn is not None

    def set_alarms(self, alarms):
        """Update the list of alarms for indicator rendering."""
        self._alarms = alarms

    def _maybe_reload_agenda(self, current_day):
        """Reload agenda events from DB every 60 seconds."""
        now_ts = time.time()
        if now_ts - self._agenda_last_load < 60:
            return
        self._agenda_last_load = now_ts
        from src.config.settings import get_db
        conn = get_db()
        try:
            rows = conn.execute("SELECT * FROM agenda_events").fetchall()
            all_events = [dict(row) for row in rows]
        except Exception:
            all_events = []
        finally:
            conn.close()
        # Filter to events active today
        filtered = []
        for ev in all_events:
            days = ev.get("days", "")
            if days:
                day_list = [d.strip() for d in days.split(",") if d.strip()]
                if current_day not in day_list:
                    continue
            filtered.append(ev)
        self._agenda_events = filtered

    def run(self):
        """Run the clock loop. Blocks until stop() is called or window is closed."""
        self._running = True
        clock = pygame.time.Clock()

        while self._running:
            # Handle Pygame events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._running = False
                    break
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self._running = False
                    break

            if not self._running:
                break

            # Get current time in configured timezone
            tz_name = self._settings.get("timezone", "UTC")
            try:
                tz = ZoneInfo(tz_name)
            except Exception:
                tz = ZoneInfo("UTC")
                tz_name = "UTC"
            now = datetime.now(tz)

            time_info = {
                "hour": now.hour,
                "minute": now.minute,
                "second": now.second,
                "microsecond": now.microsecond,
            }

            # Detect timezone change and start transition animation
            if self._last_tz_name is not None and tz_name != self._last_tz_name:
                try:
                    old_tz = ZoneInfo(self._last_tz_name)
                    old_now = datetime.now(old_tz)
                    old_secs = _time_to_seconds(old_now.hour, old_now.minute, old_now.second, old_now.microsecond)
                    new_secs = _time_to_seconds(now.hour, now.minute, now.second, now.microsecond)
                    # Offset is old - new (we start at old and animate to new)
                    offset = old_secs - new_secs
                    # Take shortest path (wrap around 12h for visual, but use 24h math)
                    if offset > 43200:
                        offset -= 86400
                    elif offset < -43200:
                        offset += 86400
                    self._tz_transition_offset = offset
                    self._tz_transition_start = time.time()
                except Exception:
                    self._tz_transition_offset = 0
            self._last_tz_name = tz_name

            # Apply timezone transition animation
            tz_transitioning = False
            if self._tz_transition_offset != 0:
                elapsed = time.time() - self._tz_transition_start
                if elapsed < self._TZ_TRANSITION_DURATION:
                    tz_transitioning = True
                    progress = _ease_in_out(elapsed / self._TZ_TRANSITION_DURATION)
                    remaining_offset = self._tz_transition_offset * (1.0 - progress)
                    current_secs = _time_to_seconds(
                        time_info["hour"], time_info["minute"],
                        time_info["second"], time_info["microsecond"]
                    )
                    time_info = _seconds_to_time_info(current_secs + remaining_offset)
                else:
                    self._tz_transition_offset = 0

            # Get active theme
            theme = self._theme_manager.get_active_theme()

            # Determine if smooth second hand is enabled (per-theme setting)
            smooth = theme.get("hands", {}).get("second", {}).get("smooth", False)
            if not smooth or self._is_pi_zero:
                # Snap second hand to integer seconds even during alarm animation
                time_info["microsecond"] = 0

            # Reload agenda events periodically
            self._maybe_reload_agenda(now.strftime("%a"))

            # Render frame (with optional alarm overlay + alarm indicators)
            surface = render_frame(
                time_info, theme,
                overlay_fn=self._overlay_fn,
                alarms=self._alarms,
                agenda_events=self._agenda_events,
            )

            # Show frame
            show_frame(surface)

            # Dynamic FPS: 30fps alarm/transition, 15fps smooth hands, 1fps default
            if self._alarm_active or tz_transitioning:
                target_fps = 30
            elif smooth and not self._is_pi_zero:
                target_fps = 15
            else:
                target_fps = 1
            clock.tick(target_fps)

    def stop(self):
        """Signal the engine to stop."""
        self._running = False
