import gc
import json
import os
import sys
import time
import math
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

import pygame

from src.alarms.ipc import check_nudge, read_dial_state, read_timer_state, write_timer_state
from src.clock.renderer import render_frame
from src.clock.dial import render_dial_frame
from src.clock.display import show_frame_from_buffer
from src.themes.dial_manager import DialThemeManager


def _ease_in_out(t):
    """Smooth ease-in-out (sinusoidal)."""
    return 0.5 - 0.5 * math.cos(math.pi * t)


def _compute_hand_angles(time_info):
    """Compute hand angles (degrees) from time_info."""
    hour = time_info["hour"] % 12
    minute = time_info["minute"]
    second = time_info["second"]
    microsecond = time_info.get("microsecond", 0)
    hour_angle = (hour + minute / 60) * 30 - 90
    minute_angle = (minute + second / 60) * 6 - 90
    second_angle = (second + microsecond / 1_000_000) * 6 - 90
    return {"hour": hour_angle, "minute": minute_angle, "second": second_angle}


def _shortest_angle_delta(from_deg, to_deg):
    """Find shortest rotation delta between two angles in degrees."""
    delta = (to_deg - from_deg) % 360
    if delta > 180:
        delta -= 360
    return delta


class ClockEngine:
    """Main clock engine that drives the rendering loop."""

    def __init__(self, theme_manager, settings):
        self._theme_manager = theme_manager
        self._dial_theme_manager = DialThemeManager(settings)
        self._settings = settings
        self._running = False
        self._alarm_callback = None
        self._overlay_fn = None
        self._alarm_active = False
        self._alarms = []
        self._agenda_events = []
        self._agenda_last_load = 0
        self._last_agenda_json = None  # cached JSON for change detection
        self._last_tz_name = None
        self._tz_transition_start = 0  # time.time() when transition began
        self._tz_old_angles = None     # {hour, minute, second} angles at start
        self._tz_new_time_info = None  # time_info snapshot at transition start
        self._TZ_TRANSITION_DURATION = 1.0  # seconds
        # Cached render settings (refreshed periodically, not per-frame)
        self._render_settings_last_load = 0
        self._cfg_smooth_fps = 30
        self._cfg_animation_fps = 30
        self._cfg_idle_fps = 1
        self._cfg_timezone = "UTC"
        self._cfg_tz = ZoneInfo("UTC")
        self._cfg_theme = None
        # Reusable dict avoids per-frame dict allocation
        self._time_info = {"hour": 0, "minute": 0, "second": 0, "microsecond": 0}
        # Frame timing diagnostics (enabled via --debug-fps)
        self.debug_fps = False
        # Alarm scheduler — polled from settings-reload path (no timer threads)
        self._alarm_scheduler = None
        # Dial mode state
        self._cfg_display_mode = "clock"
        self._cfg_dial_theme = None
        self._dial_state = None
        self._dial_current_progress = 0.0
        self._dial_target_progress = 0.0
        self._dial_anim_start = 0.0
        self._dial_anim_from = 0.0
        self._dial_anim_duration = 0.5
        self._dial_frame_dirty = True   # True = must re-render dial
        self._dial_cached_buf = None    # last rendered RGB buffer
        # Timer mode state
        self._timer_state = None
        self._timer_last_tick = 0.0     # monotonic time of last countdown tick
        self._timer_display_pct = 0.0   # current display progress (0-100)
        self._timer_target_pct = 0.0    # target display progress
        self._timer_anim_start = 0.0
        self._timer_anim_from = 0.0
        self._timer_frame_dirty = True
        self._timer_cached_buf = None
        self._timer_finished_handled = False  # prevent re-triggering alarm

    def set_alarm_scheduler(self, scheduler):
        """Attach alarm scheduler for polling from the render loop."""
        self._alarm_scheduler = scheduler

    def set_alarm_callback(self, callback):
        """Set a callback that returns overlay draw info when an alarm is active."""
        self._alarm_callback = callback

    def set_overlay(self, overlay_fn):
        """Set an overlay function called after rendering each frame."""
        self._overlay_fn = overlay_fn
        self._alarm_active = overlay_fn is not None
        # Force re-render so dial/timer modes pick up the overlay
        self._dial_frame_dirty = True
        self._timer_frame_dirty = True

    def set_alarms(self, alarms):
        """Update the list of alarms for indicator rendering."""
        self._alarms = alarms

    def _maybe_reload_agenda(self, now):
        """Reload agenda events from JSON every 60 seconds.

        Filters out events that don't match today's day-of-week AND
        events whose end_time has already passed today (e.g. a 06:45-07:15
        event should not appear at 16:13).
        """
        now_ts = time.time()
        if now_ts - self._agenda_last_load < 60:
            return
        self._agenda_last_load = now_ts
        current_day = now.strftime("%a")
        current_time_str = now.strftime("%H:%M")
        from src.config.settings import list_agenda_events
        try:
            all_events = list_agenda_events()
        except Exception:
            all_events = []
        # Filter to events active right now
        filtered = []
        for ev in all_events:
            days = ev.get("days", "")
            if days:
                day_list = [d.strip() for d in days.split(",") if d.strip()]
                if current_day not in day_list:
                    continue
            # Hide events whose end time has already passed today
            end_time = ev.get("end_time", "")
            if end_time and current_time_str > end_time:
                continue
            filtered.append(ev)
        # Only update when content actually changes — avoids triggering
        # the renderer's identity-based static cache rebuild every 60s.
        agenda_json = json.dumps(filtered, sort_keys=True)
        if agenda_json != self._last_agenda_json:
            self._last_agenda_json = agenda_json
            self._agenda_events = filtered

    def run(self):
        """Run the clock loop. Blocks until stop() is called or window is closed."""
        self._running = True
        next_frame = time.monotonic()

        # --- Thread priority & isolation for stutter-free smooth second hand ---

        # 1. Increase GIL switch interval: default 5ms lets Flask/Scheduler
        #    steal CPU mid-frame. At 30fps (33ms budget) a 5ms GIL switch is
        #    15% of frame time. Setting to 100ms means background threads only
        #    get the GIL when we explicitly release it (sleep/IO).
        old_switch_interval = sys.getswitchinterval()
        sys.setswitchinterval(0.1)

        # 2. Pin render loop to core 0 (Linux only). Background threads
        #    (Flask, scheduler) will migrate to cores 1-3, eliminating
        #    L1 cache thrashing and OS scheduling jitter on our core.
        try:
            os.sched_setaffinity(0, {0})
        except (OSError, AttributeError):
            pass  # Not available on Windows/macOS

        # 3. Request real-time scheduling (SCHED_RR) for predictable frame
        #    timing. Requires CAP_SYS_NICE or root. Falls back silently.
        try:
            os.sched_setscheduler(0, os.SCHED_RR, os.sched_param(1))
        except (OSError, AttributeError, PermissionError):
            pass

        # Disable automatic GC — we'll collect manually during frame slack
        # to prevent unpredictable pauses that cause second hand stutter.
        gc.disable()

        try:
            self._run_loop(next_frame)
        finally:
            gc.enable()
            sys.setswitchinterval(old_switch_interval)
            # Restore default affinity
            try:
                os.sched_setaffinity(0, set(range(os.cpu_count() or 4)))
            except (OSError, AttributeError):
                pass

    def _run_loop(self, next_frame):
        """Inner render loop, separated for clean GC try/finally."""
        time_info = self._time_info

        # Frame timing diagnostics
        _debug = self.debug_fps
        if _debug:
            _frame_times = []
            _last_report = time.monotonic()

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

            # Check for cross-process nudge (agenda/alarm/theme changed via API)
            if check_nudge():
                self._agenda_last_load = 0
                self._render_settings_last_load = 0
                self._dial_state = None  # force reload
                self._dial_frame_dirty = True
                self._timer_state = None  # force reload
                self._timer_frame_dirty = True

            # Reload cached settings periodically (every 2s, not per-frame)
            self._maybe_reload_render_settings()

            # --- Clock-only work (skip entirely in dial mode) ---
            tz_transitioning = False
            hand_angles = None
            smooth = False

            if self._cfg_display_mode not in ("dial", "timer"):
                # Get current time using cached ZoneInfo (no per-frame try/except)
                now = datetime.now(self._cfg_tz)
                tz_name = self._cfg_timezone

                time_info["hour"] = now.hour
                time_info["minute"] = now.minute
                time_info["second"] = now.second
                time_info["microsecond"] = now.microsecond

                # Detect timezone change and start transition animation
                if self._last_tz_name is not None and tz_name != self._last_tz_name:
                    try:
                        old_tz = ZoneInfo(self._last_tz_name)
                        old_now = datetime.now(old_tz)
                        old_time_info = {
                            "hour": old_now.hour,
                            "minute": old_now.minute,
                            "second": old_now.second,
                            "microsecond": old_now.microsecond,
                        }
                        self._tz_old_angles = _compute_hand_angles(old_time_info)
                        self._tz_transition_start = time.time()
                    except Exception:
                        self._tz_old_angles = None
                self._last_tz_name = tz_name

                # Apply timezone transition animation (per-hand independent shortest path)
                if self._tz_old_angles is not None:
                    elapsed = time.time() - self._tz_transition_start
                    if elapsed < self._TZ_TRANSITION_DURATION:
                        tz_transitioning = True
                        progress = _ease_in_out(elapsed / self._TZ_TRANSITION_DURATION)
                        new_angles = _compute_hand_angles(time_info)
                        hand_angles = {}
                        for key in ("hour", "minute", "second"):
                            delta = _shortest_angle_delta(self._tz_old_angles[key], new_angles[key])
                            hand_angles[key] = self._tz_old_angles[key] + delta * progress
                    else:
                        self._tz_old_angles = None

                # Get active theme (cached, refreshed every 2s)
                theme = self._cfg_theme or self._theme_manager.get_active_theme()

                # Determine if smooth second hand is enabled (per-theme setting)
                smooth = theme.get("hands", {}).get("second", {}).get("smooth", False)
                if not smooth:
                    # Snap second hand to integer seconds
                    time_info["microsecond"] = 0

                # Reload agenda events periodically
                self._maybe_reload_agenda(now)

            # Render frame
            if _debug:
                _t0 = time.monotonic()

            if self._cfg_display_mode == "dial":
                # Overlay animation requires continuous re-rendering
                if self._alarm_active:
                    self._dial_frame_dirty = True
                # Skip full render when the dial frame hasn't changed
                if self._dial_frame_dirty:
                    rgb_buf = self._render_dial(self._cfg_dial_theme or {})
                    self._dial_cached_buf = rgb_buf
                    show_frame_from_buffer(rgb_buf)
                # else: display already shows correct frame — do nothing
            elif self._cfg_display_mode == "timer":
                # Overlay animation requires continuous re-rendering
                if self._alarm_active:
                    self._timer_frame_dirty = True
                # Timer mode: reuse dial renderer for countdown arc
                if self._timer_frame_dirty:
                    rgb_buf = self._render_timer(self._cfg_dial_theme or {})
                    self._timer_cached_buf = rgb_buf
                    show_frame_from_buffer(rgb_buf)
            else:
                rgb_buf = render_frame(
                    time_info, theme,
                    overlay_fn=self._overlay_fn,
                    alarms=self._alarms,
                    agenda_events=self._agenda_events,
                    hand_angles=hand_angles,
                )
                show_frame_from_buffer(rgb_buf)

            if _debug:
                _frame_times.append(time.monotonic() - _t0)
                _now_dbg = time.monotonic()
                if _now_dbg - _last_report >= 5.0:
                    import statistics
                    n = len(_frame_times)
                    avg = statistics.mean(_frame_times) * 1000
                    mx = max(_frame_times) * 1000
                    p95 = sorted(_frame_times)[int(n * 0.95)] * 1000 if n > 1 else avg
                    print(f"[FPS] {n / 5:.1f} fps | avg {avg:.1f}ms "
                          f"| p95 {p95:.1f}ms | max {mx:.1f}ms", flush=True)
                    _frame_times.clear()
                    _last_report = _now_dbg

            # Dynamic FPS using cached render settings (no per-frame I/O)
            dial_animating = (self._cfg_display_mode == "dial"
                              and self._dial_current_progress != self._dial_target_progress)
            timer_animating = (self._cfg_display_mode == "timer"
                               and self._timer_display_pct != self._timer_target_pct)
            timer_running = (self._cfg_display_mode == "timer"
                             and self._timer_state and self._timer_state.get("running"))
            if self._alarm_active or tz_transitioning or dial_animating or timer_animating:
                target_fps = self._cfg_animation_fps
            elif timer_running:
                # 1 FPS ticking countdown — just enough to update each second
                target_fps = max(1, self._cfg_idle_fps)
            elif smooth and self._cfg_display_mode not in ("dial", "timer"):
                target_fps = self._cfg_smooth_fps
            else:
                target_fps = self._cfg_idle_fps

            # Monotonic frame pacing — avoids pygame.time.Clock jitter that
            # causes the smooth second hand to stutter visibly.
            frame_interval = 1.0 / target_fps
            next_frame += frame_interval
            now_mono = time.monotonic()
            sleep_time = next_frame - now_mono
            # Cap sleep to ~1.5 frames at current rate so FPS transitions
            # (e.g. idle -> animation) respond without a stale long sleep.
            if sleep_time > frame_interval * 1.5:
                next_frame = now_mono + frame_interval
                sleep_time = frame_interval

            # Run gen-0 GC during frame slack (>3ms headroom) to prevent
            # automatic GC pauses during rendering that cause visible stutter.
            if sleep_time > 0.003:
                gc.collect(0)
                sleep_time = next_frame - time.monotonic()

            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                # Fell behind — reset to avoid burst of catch-up frames
                next_frame = time.monotonic()

    def _render_dial(self, dial_theme):
        """Read dial state, animate progress, and render dial frame."""
        dial_cfg = dial_theme.get("dial", {})
        # Lazy-load dial state (re-read on nudge or first call)
        if self._dial_state is None:
            self._dial_state = read_dial_state()
            new_target = self._dial_state.get("progress", 0)
            min_val = self._dial_state.get("min_value", 0)
            max_val = self._dial_state.get("max_value", 100)
            rng = max_val - min_val
            pct = ((new_target - min_val) / rng * 100) if rng > 0 else 0
            pct = max(0.0, min(100.0, pct))
            if pct != self._dial_target_progress:
                self._dial_anim_from = self._dial_current_progress
                self._dial_target_progress = pct
                self._dial_anim_start = time.monotonic()
                self._dial_anim_duration = dial_cfg.get("animation_duration", 0.5)

        # Animate progress
        animate = dial_cfg.get("animate", True)
        if animate and self._dial_current_progress != self._dial_target_progress:
            elapsed = time.monotonic() - self._dial_anim_start
            duration = self._dial_anim_duration
            if elapsed >= duration:
                self._dial_current_progress = self._dial_target_progress
            else:
                t = elapsed / duration
                # ease-in-out: smooth start AND end (sinusoidal)
                t = 0.5 - 0.5 * math.cos(math.pi * t)
                diff = self._dial_target_progress - self._dial_anim_from
                self._dial_current_progress = self._dial_anim_from + diff * t
            # Still animating — keep dirty for next frame
            self._dial_frame_dirty = True
        else:
            self._dial_current_progress = self._dial_target_progress
            # Animation done — frame is clean after this render
            self._dial_frame_dirty = False

        return render_dial_frame(dial_theme, self._dial_state, self._dial_current_progress,
                                 overlay_fn=self._overlay_fn)

    def _render_timer(self, dial_theme):
        """Read timer state, tick countdown, and render using dial renderer."""
        dial_cfg = dial_theme.get("dial", {})

        # Lazy-load timer state (re-read on nudge or first call)
        if self._timer_state is None:
            self._timer_state = read_timer_state()
            self._timer_last_tick = time.monotonic()
            # Reset finished-handled flag when state is freshly loaded
            if not self._timer_state.get("finished"):
                self._timer_finished_handled = False

        state = self._timer_state
        duration = state.get("duration", 0)
        remaining = state.get("remaining", 0)
        running = state.get("running", False)

        # Tick countdown each second while running
        if running and remaining > 0:
            now_mono = time.monotonic()
            elapsed_since_tick = now_mono - self._timer_last_tick
            if elapsed_since_tick >= 1.0:
                ticks = int(elapsed_since_tick)
                remaining = max(0, remaining - ticks)
                state["remaining"] = remaining
                self._timer_last_tick = now_mono - (elapsed_since_tick - ticks)
                self._timer_frame_dirty = True
                # Persist so the web UI can poll
                write_timer_state(state)

        # Timer finished
        if running and remaining <= 0 and not self._timer_finished_handled:
            state["running"] = False
            state["finished"] = True
            state["remaining"] = 0
            write_timer_state(state)
            self._timer_finished_handled = True
            self._timer_frame_dirty = True
            self._trigger_timer_alarm(state)

        # Compute target progress (100% = full, 0% = done)
        if duration > 0:
            new_pct = max(0.0, min(100.0, remaining / duration * 100))
        else:
            new_pct = 0.0

        if new_pct != self._timer_target_pct:
            self._timer_anim_from = self._timer_display_pct
            self._timer_target_pct = new_pct
            self._timer_anim_start = time.monotonic()

        # Animate progress
        anim_duration = dial_cfg.get("animation_duration", 0.5)
        if self._timer_display_pct != self._timer_target_pct:
            elapsed = time.monotonic() - self._timer_anim_start
            if elapsed >= anim_duration:
                self._timer_display_pct = self._timer_target_pct
            else:
                t = elapsed / anim_duration
                t = 0.5 - 0.5 * math.cos(math.pi * t)
                diff = self._timer_target_pct - self._timer_anim_from
                self._timer_display_pct = self._timer_anim_from + diff * t
            self._timer_frame_dirty = True
        else:
            self._timer_frame_dirty = False

        # Build a synthetic dial_state for the renderer
        # Format remaining time as HH:MM:SS or MM:SS
        secs = max(0, int(remaining))
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        if h > 0:
            time_str = f"{h:02d}:{m:02d}:{s:02d}"
        else:
            time_str = f"{m:02d}:{s:02d}"

        timer_dial_state = {
            "progress": remaining,
            "min_value": 0,
            "max_value": max(duration, 1),
            "label": state.get("label", ""),
            "value_text": time_str,
            "progress_color": None,
            "text_color": None,
        }
        return render_dial_frame(dial_theme, timer_dial_state, self._timer_display_pct,
                                 overlay_fn=self._overlay_fn)

    def _trigger_timer_alarm(self, state):
        """Trigger alarm overlay and optional sound when timer finishes."""
        # Audio
        if state.get("sound_enabled", True):
            from src.alarms.audio import play_alarm_sound
            sound_name = state.get("sound", "default")
            play_alarm_sound(sound_name)

        # Visual overlay (reuse AlarmOverlay)
        from src.alarms.visual import AlarmOverlay
        label = state.get("label", "") or "Timer"
        overlay = AlarmOverlay(
            label=label,
            shape="border_glow",
            color="#ff9900",
            speed="normal",
        )
        self.set_overlay(overlay.draw)

        # Auto-dismiss overlay after 30 seconds
        def _dismiss():
            self.set_overlay(None)
            from src.alarms.audio import stop_alarm_sound
            stop_alarm_sound()
        dismiss_timer = threading.Timer(30, _dismiss)
        dismiss_timer.daemon = True
        dismiss_timer.start()

    def _maybe_reload_render_settings(self):
        """Reload FPS and timezone settings from storage every 2 seconds (not per-frame)."""
        now_ts = time.time()
        if now_ts - self._render_settings_last_load < 2:
            return
        self._render_settings_last_load = now_ts
        try:
            self._cfg_smooth_fps = int(self._settings.get("render_smooth_fps", 30))
            self._cfg_animation_fps = int(self._settings.get("render_animation_fps", 30))
            self._cfg_idle_fps = max(1, int(self._settings.get("render_idle_fps", 1)))
        except (ValueError, TypeError):
            pass
        new_tz = self._settings.get("timezone", "UTC") or "UTC"
        if new_tz != self._cfg_timezone:
            self._cfg_timezone = new_tz
            try:
                self._cfg_tz = ZoneInfo(new_tz)
            except Exception:
                self._cfg_timezone = "UTC"
                self._cfg_tz = ZoneInfo("UTC")
        self._cfg_display_mode = self._settings.get("display_mode", "clock") or "clock"
        self._cfg_theme = self._theme_manager.get_active_theme()
        new_dial_theme = self._dial_theme_manager.get_active_theme()
        if new_dial_theme is not self._cfg_dial_theme:
            self._cfg_dial_theme = new_dial_theme
            self._dial_frame_dirty = True
        # Poll alarm scheduler (replaces timer thread — no GIL contention)
        if self._alarm_scheduler:
            self._alarm_scheduler.poll()

    def stop(self):
        """Signal the engine to stop."""
        self._running = False
