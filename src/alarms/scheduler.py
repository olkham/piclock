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
        from src.config.settings import get_db

        tz_name = self._settings.get("timezone", "UTC")
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("UTC")
        now = datetime.now(tz)
        current_time = now.strftime("%H:%M")
        current_day = now.strftime("%a")

        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT * FROM alarms WHERE enabled = 1"
            ).fetchall()
            all_alarms = [dict(row) for row in rows]
        finally:
            conn.close()

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
                    conn = get_db()
                    try:
                        conn.execute(
                            "UPDATE alarms SET enabled = 0 WHERE id = ?",
                            (alarm["id"],),
                        )
                        conn.commit()
                    finally:
                        conn.close()

    def _trigger_alarm(self, alarm):
        if self._active_alarm:
            return  # Already ringing

        self._active_alarm = alarm

        # Audio
        from src.alarms.audio import play_alarm_sound
        sound_name = alarm.get("sound", "default")
        play_alarm_sound(sound_name)

        # Visual overlay on the clock
        from src.alarms.visual import AlarmOverlay
        overlay = AlarmOverlay(
            label=alarm.get("label", "Alarm"),
            shape=alarm.get("animation_shape", "ring"),
            color=alarm.get("animation_color", "#ff3333"),
            speed=alarm.get("animation_speed", "normal"),
        )
        self._engine.set_overlay(overlay.draw)

        # Auto-dismiss after 60 seconds
        dismiss_timer = threading.Timer(60, self._stop_alarm)
        dismiss_timer.daemon = True
        dismiss_timer.start()

    def _stop_alarm(self):
        self._active_alarm = None
        self._engine.set_overlay(None)
        from src.alarms.audio import stop_alarm_sound
        stop_alarm_sound()
