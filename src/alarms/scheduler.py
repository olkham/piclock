"""Alarm scheduler — checks alarms and triggers audio + visual alerts."""

import threading
from datetime import datetime
from zoneinfo import ZoneInfo


class AlarmScheduler:
    """Periodically checks if any alarm should fire."""

    def __init__(self, settings, engine):
        self._settings = settings
        self._engine = engine
        self._timer = None
        self._running = False
        self._active_alarm = None
        self._dismiss_timer = None
        self._lock = threading.Lock()

    def start(self):
        self._running = True
        self._schedule_check()

    def stop(self):
        self._running = False
        if self._timer:
            self._timer.cancel()
        self._stop_alarm()

    def _schedule_check(self):
        if not self._running:
            return
        self._check_alarms()
        self._timer = threading.Timer(10, self._schedule_check)
        self._timer.daemon = True
        self._timer.start()

    def _check_alarms(self):
        from src.config.settings import get_enabled_alarms, disable_alarm

        tz_name = self._settings.get("timezone", "UTC")
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("UTC")
        now = datetime.now(tz)
        current_time = now.strftime("%H:%M")
        current_day = now.strftime("%a")

        all_alarms = get_enabled_alarms()

        # Feed all enabled alarms to engine for indicator rendering
        self._engine.set_alarms(all_alarms)

        for alarm in all_alarms:
            if alarm["time"] == current_time:
                days = alarm.get("days", "")
                if days:
                    day_list = [d.strip() for d in days.split(",") if d.strip()]
                    if current_day in day_list:
                        self._trigger_alarm(alarm)
                else:
                    self._trigger_alarm(alarm)
                    # One-time alarm — disable after firing
                    disable_alarm(alarm["id"])

    def _trigger_alarm(self, alarm):
        with self._lock:
            if self._active_alarm:
                return  # Already ringing

            self._active_alarm = alarm

        # Audio (only if sound is enabled for this alarm)
        sound_enabled = alarm.get("sound_enabled", 1)
        if sound_enabled:
            from src.alarms.audio import play_alarm_sound
            sound_name = alarm.get("sound", "default")
            play_alarm_sound(sound_name)

        # Visual overlay on the clock
        from src.alarms.visual import AlarmOverlay
        overlay = AlarmOverlay(
            label=alarm.get("label", "Alarm"),
            shape=alarm.get("animation_shape", "border_glow"),
            color=alarm.get("animation_color", "#ff3333"),
            speed=alarm.get("animation_speed", "normal"),
        )
        self._engine.set_overlay(overlay.draw)

        # Auto-dismiss after configured duration
        duration = int(alarm.get("animation_duration", 60))
        self._dismiss_timer = threading.Timer(duration, self._stop_alarm)
        self._dismiss_timer.daemon = True
        self._dismiss_timer.start()

    def snooze(self, delay_seconds=300):
        """Snooze the active alarm for the given delay."""
        with self._lock:
            if not self._active_alarm:
                return False
            alarm = self._active_alarm
        self._stop_alarm()
        snooze_timer = threading.Timer(delay_seconds, self._trigger_alarm, args=[alarm])
        snooze_timer.daemon = True
        snooze_timer.start()
        return True

    def dismiss(self):
        """Dismiss the active alarm."""
        with self._lock:
            if not self._active_alarm:
                return False
        self._stop_alarm()
        return True

    def has_active_alarm(self):
        """Check if an alarm is currently active."""
        return self._active_alarm is not None

    def get_active_alarm_info(self):
        """Get info about the currently active alarm."""
        with self._lock:
            if self._active_alarm:
                return {
                    "id": self._active_alarm.get("id"),
                    "label": self._active_alarm.get("label", "Alarm"),
                    "time": self._active_alarm.get("time", ""),
                }
            return None

    def _stop_alarm(self):
        with self._lock:
            self._active_alarm = None
            if self._dismiss_timer:
                self._dismiss_timer.cancel()
                self._dismiss_timer = None
        self._engine.set_overlay(None)
        from src.alarms.audio import stop_alarm_sound
        stop_alarm_sound()
