"""Alarm scheduler — checks alarms and triggers audio + visual alerts.

Alarm checking is pull-based: the engine calls poll() from its own render
loop during the settings-reload phase.  This avoids threading.Timer threads
that steal the GIL and cause smooth second hand stutter.
"""

import json
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from src.alarms.ipc import read_alarm_command, write_alarm_state


class AlarmScheduler:
    """Periodically checks if any alarm should fire.

    Call poll() from the render loop — no background timer threads are used
    for alarm checking, eliminating GIL contention with the render thread.
    """

    CHECK_INTERVAL = 10  # seconds between alarm checks

    def __init__(self, settings, engine):
        self._settings = settings
        self._engine = engine
        self._cmd_timer = None
        self._running = False
        self._active_alarm = None
        self._dismiss_timer = None
        self._lock = threading.Lock()
        self._last_check = 0.0
        self._last_alarms_json = None  # cached JSON string for change detection
        # Write initial state so Flask always has a valid file
        write_alarm_state(None)

    def start(self):
        self._running = True

    def stop(self):
        self._running = False
        if self._cmd_timer:
            self._cmd_timer.cancel()
        self._stop_alarm()

    def poll(self):
        """Called from the engine's render loop — check alarms if due.

        This replaces the old threading.Timer approach. Running alarm
        checks synchronously inside the render loop's settings-reload
        phase means no background thread can steal the GIL mid-frame.
        """
        if not self._running:
            return
        now_ts = time.time()
        if now_ts - self._last_check < self.CHECK_INTERVAL:
            return
        self._last_check = now_ts
        self._check_alarms()

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

        # Only update engine when alarm data actually changes — avoids
        # triggering the renderer's identity-based static cache rebuild.
        alarms_json = json.dumps(all_alarms, sort_keys=True)
        if alarms_json != self._last_alarms_json:
            self._last_alarms_json = alarms_json
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

        # Publish active alarm state for Flask subprocess
        write_alarm_state({
            "id": alarm.get("id"),
            "label": alarm.get("label", "Alarm"),
            "time": alarm.get("time", ""),
        })

        # Start fast command polling (1 second) while alarm is active
        self._start_command_polling()

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
        # Stop fast command polling
        if self._cmd_timer:
            self._cmd_timer.cancel()
            self._cmd_timer = None
        # Publish cleared state for Flask subprocess
        write_alarm_state(None)
        self._engine.set_overlay(None)
        from src.alarms.audio import stop_alarm_sound
        stop_alarm_sound()

    # --- File-based command polling (for Flask subprocess IPC) ---

    def _start_command_polling(self):
        """Start polling for alarm commands every 1 second."""
        if self._cmd_timer:
            self._cmd_timer.cancel()
        self._poll_commands()

    def _poll_commands(self):
        """Check for pending alarm commands from Flask subprocess."""
        if not self._running:
            return
        cmd = read_alarm_command()
        if cmd:
            action = cmd.get("cmd")
            if action == "snooze":
                delay = int(cmd.get("delay", 300))
                self.snooze(delay)
                return  # snooze stops alarm → stops polling
            elif action == "dismiss":
                self.dismiss()
                return  # dismiss stops alarm → stops polling
        # Continue polling while alarm is still active
        if self._active_alarm:
            self._cmd_timer = threading.Timer(1, self._poll_commands)
            self._cmd_timer.daemon = True
            self._cmd_timer.start()
