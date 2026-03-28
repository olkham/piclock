"""Data source resolution for face element bindings.

Maps data source names (e.g. 'time.hour_angle', 'dial.progress') to
live values gathered from the engine's current state.
"""

import math
from datetime import datetime


def _deg_to_rad(deg):
    """Convert degrees (0=top, clockwise) to Cairo radians."""
    return math.radians(deg - 90)


def _compute_arc_range(binding):
    """Get arc start/end in degrees from a binding's arc config."""
    if binding.get("arc_symmetric", False):
        center = binding.get("arc_center", 0)
        extent = binding.get("arc_extent", 135)
        return center - extent, center + extent
    return binding.get("arc_start", 135), binding.get("arc_end", 405)


class DataContext:
    """Gathers all live data for resolving element bindings.

    Created once per frame by the engine, then passed to the renderer.
    """

    def __init__(self, time_info=None, hand_angles=None,
                 dial_state=None, display_progress=None,
                 timer_state=None, timer_display_pct=None,
                 alarms=None, agenda_events=None, now=None):
        self.time_info = time_info or {}
        self.hand_angles = hand_angles
        self.dial_state = dial_state or {}
        self.display_progress = display_progress if display_progress is not None else 0
        self.timer_state = timer_state or {}
        self.timer_display_pct = timer_display_pct if timer_display_pct is not None else 0
        self.alarms = alarms or []
        self.agenda_events = agenda_events or []
        self.now = now

    def resolve(self, source):
        """Resolve a data source name to its current value."""
        if source == "time.hour_angle":
            if self.hand_angles:
                return self.hand_angles.get("hour", 0)
            return self._compute_hour_angle()
        if source == "time.minute_angle":
            if self.hand_angles:
                return self.hand_angles.get("minute", 0)
            return self._compute_minute_angle()
        if source == "time.second_angle":
            if self.hand_angles:
                return self.hand_angles.get("second", 0)
            return self._compute_second_angle()
        if source == "time.formatted_12h":
            return self._format_time_12h()
        if source == "time.formatted_24h":
            return self._format_time_24h()
        if source == "date.formatted":
            return self._format_date()
        if source == "date.full":
            return self._format_date_full()
        if source == "date.day_of_week":
            if self.now:
                return self.now.strftime("%A")
            return ""
        if source == "dial.progress":
            return self.display_progress
        if source == "dial.label":
            return self.dial_state.get("label", "")
        if source == "dial.value":
            return str(self.dial_state.get("progress", 0))
        if source == "dial.min":
            return str(self.dial_state.get("min_value", 0))
        if source == "dial.max":
            return str(self.dial_state.get("max_value", 100))
        if source == "dial.suffix":
            return self.dial_state.get("value_suffix", "%")
        if source == "dial.progress_color":
            return self.dial_state.get("progress_color")
        if source == "timer.progress":
            return self.timer_display_pct
        if source == "timer.remaining_formatted":
            return self._format_timer_remaining()
        if source == "timer.label":
            return self.timer_state.get("label", "")
        if source == "alarm.list":
            return self.alarms
        if source == "agenda.events":
            return self.agenda_events
        return None

    def resolve_binding(self, binding):
        """Resolve a binding dict to a value, applying transforms."""
        source = binding.get("source", "")
        value = self.resolve(source)
        transform = binding.get("transform")
        if transform == "arc_angle":
            # Map 0-100 progress to arc angle in degrees
            arc_start, arc_end = _compute_arc_range(binding)
            progress = max(0.0, min(100.0, float(value) if isinstance(value, (int, float)) else 0.0))
            angle = arc_start + (arc_end - arc_start) * (progress / 100)
            return angle
        return value

    def _compute_hour_angle(self):
        ti = self.time_info
        hour = ti.get("hour", 0) % 12
        minute = ti.get("minute", 0)
        return (hour + minute / 60) * 30 - 90

    def _compute_minute_angle(self):
        ti = self.time_info
        minute = ti.get("minute", 0)
        second = ti.get("second", 0)
        return (minute + second / 60) * 6 - 90

    def _compute_second_angle(self):
        ti = self.time_info
        second = ti.get("second", 0)
        microsecond = ti.get("microsecond", 0)
        return (second + microsecond / 1_000_000) * 6 - 90

    def _format_time_12h(self):
        ti = self.time_info
        hour = ti.get("hour", 0)
        minute = ti.get("minute", 0)
        period = "AM" if hour < 12 else "PM"
        h12 = hour % 12
        if h12 == 0:
            h12 = 12
        return f"{h12}:{minute:02d} {period}"

    def _format_time_24h(self):
        ti = self.time_info
        return f"{ti.get('hour', 0):02d}:{ti.get('minute', 0):02d}"

    def _format_date(self):
        if self.now:
            return self.now.strftime("%b %d")
        return ""

    def _format_date_full(self):
        if self.now:
            return self.now.strftime("%A, %b %d")
        return ""

    def _format_timer_remaining(self):
        remaining = self.timer_state.get("remaining", 0)
        secs = max(0, int(remaining))
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"
