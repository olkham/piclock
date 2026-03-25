"""PiClock3 SDK client — thin wrapper around the REST API."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

import requests


class PiClockError(Exception):
    """Raised when an API call fails."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")


class PiClock:
    """Client for the PiClock3 REST API.

    Args:
        host: Hostname or IP of the PiClock device.
        port: Web interface port (default 8080).
        timeout: Request timeout in seconds.
    """

    def __init__(self, host: str = "localhost", port: int = 8080, timeout: int = 10):
        self.base_url = f"http://{host}:{port}/api"
        self.timeout = timeout
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _request(self, method: str, path: str, **kwargs) -> Any:
        kwargs.setdefault("timeout", self.timeout)
        resp = self._session.request(method, self._url(path), **kwargs)
        if not resp.ok:
            try:
                detail = resp.json().get("error", resp.text)
            except Exception:
                detail = resp.text
            raise PiClockError(resp.status_code, detail)
        if resp.headers.get("content-type", "").startswith("application/json"):
            return resp.json()
        return resp.content

    def _get(self, path: str, **kwargs) -> Any:
        return self._request("GET", path, **kwargs)

    def _post(self, path: str, **kwargs) -> Any:
        return self._request("POST", path, **kwargs)

    def _put(self, path: str, **kwargs) -> Any:
        return self._request("PUT", path, **kwargs)

    def _delete(self, path: str, **kwargs) -> Any:
        return self._request("DELETE", path, **kwargs)

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def get_settings(self) -> dict:
        """Get all settings."""
        return self._get("settings")

    def update_settings(self, **kwargs) -> dict:
        """Update one or more settings.

        Example::

            clock.update_settings(timezone="America/New_York", brightness=80)
        """
        return self._put("settings", json=kwargs)

    def get_timezone(self) -> str:
        """Get the current timezone."""
        return self.get_settings().get("timezone", "UTC")

    def set_timezone(self, tz: str) -> dict:
        """Set the timezone (IANA name, e.g. 'Europe/London')."""
        return self.update_settings(timezone=tz)

    def list_timezones(self, query: str | None = None) -> list[dict]:
        """List available timezones with UTC offsets.

        Args:
            query: Optional search filter (e.g. 'new_york').
        """
        params = {"q": query} if query else {}
        return self._get("timezones", params=params)

    # ------------------------------------------------------------------
    # Themes
    # ------------------------------------------------------------------

    def list_themes(self) -> dict:
        """List all themes. Returns ``{"themes": [...], "active": "..."}``."""
        return self._get("themes")

    def get_theme(self, name: str) -> dict:
        """Get full theme definition by name."""
        return self._get(f"themes/{name}")

    def create_theme(self, theme: dict) -> dict:
        """Create a new theme."""
        return self._post("themes", json=theme)

    def update_theme(self, name: str, theme: dict) -> dict:
        """Update an existing theme."""
        return self._put(f"themes/{name}", json=theme)

    def delete_theme(self, name: str) -> dict:
        """Delete a theme."""
        return self._delete(f"themes/{name}")

    def activate_theme(self, name: str) -> dict:
        """Set a theme as the active theme."""
        return self._post(f"themes/{name}/activate")

    def export_theme(self, name: str) -> bytes:
        """Export a theme as raw JSON bytes."""
        return self._get(f"themes/{name}/export")

    def import_theme(self, path: str | Path) -> dict:
        """Import a theme from a JSON file."""
        p = Path(path)
        with open(p, "rb") as f:
            return self._post("themes/import", files={"file": (p.name, f, "application/json")})

    # ------------------------------------------------------------------
    # Uploads (background images, etc.)
    # ------------------------------------------------------------------

    def upload_image(self, path: str | Path) -> dict:
        """Upload an image file. Returns ``{"url": "/api/uploads/...", ...}``."""
        p = Path(path)
        mime = mimetypes.guess_type(p.name)[0] or "image/png"
        with open(p, "rb") as f:
            return self._post("uploads", files={"file": (p.name, f, mime)})

    # ------------------------------------------------------------------
    # Convenience: set background image
    # ------------------------------------------------------------------

    def set_background_image(self, image_path: str | Path, theme: str | None = None) -> dict:
        """Upload an image and set it as the background for a theme.

        Args:
            image_path: Local path to the image file.
            theme: Theme name to update. If ``None``, uses the active theme.

        Returns:
            The updated theme dict.
        """
        # Upload the image
        upload = self.upload_image(image_path)
        image_url = upload["url"]

        # Resolve theme name
        if theme is None:
            theme = self.list_themes()["active"]

        # Update theme background
        current = self.get_theme(theme)
        bg = current.get("background", {})
        bg["type"] = "image"
        bg["image"] = image_url
        bg.setdefault("image_opacity", 100)
        current["background"] = bg
        return self.update_theme(theme, current)

    # ------------------------------------------------------------------
    # Alarms
    # ------------------------------------------------------------------

    def list_alarms(self) -> list[dict]:
        """List all alarms."""
        return self._get("alarms")

    def create_alarm(self, time: str, **kwargs) -> dict:
        """Create an alarm. ``time`` format: ``"HH:MM"``."""
        return self._post("alarms", json={"time": time, **kwargs})

    def update_alarm(self, alarm_id: int, **kwargs) -> dict:
        """Update an alarm."""
        return self._put(f"alarms/{alarm_id}", json=kwargs)

    def delete_alarm(self, alarm_id: int) -> dict:
        """Delete an alarm."""
        return self._delete(f"alarms/{alarm_id}")

    def get_active_alarm(self) -> dict:
        """Get currently ringing alarm info."""
        return self._get("alarms/active")

    def snooze_alarm(self, delay: int = 300) -> dict:
        """Snooze the active alarm."""
        return self._post("alarms/snooze", json={"delay": delay})

    def dismiss_alarm(self) -> dict:
        """Dismiss the active alarm."""
        return self._post("alarms/dismiss")

    # ------------------------------------------------------------------
    # Agenda
    # ------------------------------------------------------------------

    def list_agenda(self) -> list[dict]:
        """List all agenda events."""
        return self._get("agenda")

    def create_event(self, title: str, start_time: str, end_time: str, **kwargs) -> dict:
        """Create an agenda event. Times in ``"HH:MM"`` format."""
        return self._post("agenda", json={
            "title": title, "start_time": start_time, "end_time": end_time, **kwargs
        })

    def update_event(self, event_id: int, **kwargs) -> dict:
        """Update an agenda event."""
        return self._put(f"agenda/{event_id}", json=kwargs)

    def delete_event(self, event_id: int) -> dict:
        """Delete an agenda event."""
        return self._delete(f"agenda/{event_id}")

    # ------------------------------------------------------------------
    # Dial
    # ------------------------------------------------------------------

    def get_dial(self) -> dict:
        """Get the current dial state."""
        return self._get("dial")

    def set_dial(self, **kwargs) -> dict:
        """Update dial state fields.

        Args:
            progress: Current value (between min_value and max_value).
            min_value: Minimum value (default 0).
            max_value: Maximum value (default 100).
            text: Primary text displayed in the centre.
            label: Secondary label below the text.
            progress_color: Override progress arc colour (hex, e.g. ``"#ff0000"``).
            text_color: Override text colour (hex).
        """
        return self._put("dial", json=kwargs)

    def reset_dial(self) -> dict:
        """Reset dial state to defaults."""
        return self._post("dial/reset")

    def set_display_mode(self, mode: str) -> dict:
        """Switch between ``"clock"`` and ``"dial"`` display modes."""
        return self.update_settings(display_mode=mode)

    # ------------------------------------------------------------------
    # Sounds
    # ------------------------------------------------------------------

    def list_sounds(self) -> list[str]:
        """List available alarm sounds."""
        return self._get("sounds")

    def upload_sound(self, path: str | Path) -> dict:
        """Upload an alarm sound file (wav, ogg, mp3)."""
        p = Path(path)
        mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        with open(p, "rb") as f:
            return self._post("sounds", files={"file": (p.name, f, mime)})

    # ------------------------------------------------------------------
    # Power / Brightness
    # ------------------------------------------------------------------

    def get_power(self) -> dict:
        """Get brightness and dimming settings."""
        return self._get("power")

    def set_power(self, **kwargs) -> dict:
        """Update brightness / dimming schedule.

        Args:
            brightness: 0–100 normal brightness.
            dim_brightness: 0–100 dimmed brightness.
            dim_start: "HH:MM" start of dim period.
            dim_end: "HH:MM" end of dim period.
        """
        return self._put("power", json=kwargs)

    # ------------------------------------------------------------------
    # System
    # ------------------------------------------------------------------

    def get_version(self) -> str:
        """Get the PiClock software version."""
        return self._get("version")["version"]

    def check_update(self) -> dict:
        """Check for available updates."""
        return self._get("update/check")

    def run_update(self) -> dict:
        """Trigger the update script on the device."""
        return self._post("update/run")

    def get_status(self) -> dict:
        """Get system status (timezone, active theme, themes)."""
        return self._get("status")

    def reboot(self) -> dict:
        """Reboot the PiClock device."""
        return self._post("reboot")

    def shutdown(self) -> dict:
        """Shut down the PiClock device."""
        return self._post("shutdown")

    # ------------------------------------------------------------------
    # Theme Cycling
    # ------------------------------------------------------------------

    def get_theme_cycle(self) -> dict:
        """Get theme auto-cycle configuration."""
        return self._get("theme-cycle")

    def set_theme_cycle(self, **kwargs) -> dict:
        """Configure theme auto-cycling.

        Args:
            enabled: ``True`` to enable cycling.
            interval: Seconds between theme changes (min 60).
            random: Randomize order instead of sequential.
        """
        return self._put("theme-cycle", json=kwargs)
