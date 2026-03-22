import time
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
            now = datetime.now(tz)

            time_info = {
                "hour": now.hour,
                "minute": now.minute,
                "second": now.second,
                "microsecond": now.microsecond,
            }

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

            # Dynamic FPS: 30fps alarm, 6fps smooth hands, 1fps default
            if self._alarm_active:
                target_fps = 30
            elif smooth and not self._is_pi_zero:
                target_fps = 6
            else:
                target_fps = 1
            clock.tick(target_fps)

    def stop(self):
        """Signal the engine to stop."""
        self._running = False
