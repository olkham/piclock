"""REST API routes."""

import json
import os
import random
import re
import subprocess
import threading
import urllib.request
from datetime import datetime, timezone, timedelta
from zoneinfo import available_timezones, ZoneInfo

from flask import Blueprint, Response, current_app, jsonify, request, send_from_directory
from PIL import Image

from src._version import __version__

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "uploads")
SOUNDS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "sounds")
ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "bmp", "webp"}
ALLOWED_SOUND_EXT = {"wav", "ogg", "mp3"}
MAX_IMAGE_SIZE = 720  # max width/height in pixels


def create_api_blueprint():
    bp = Blueprint("api", __name__)

    # --- Settings ---

    @bp.route("/settings", methods=["GET"])
    def get_settings():
        settings = current_app.settings
        return jsonify(settings.all())

    @bp.route("/settings", methods=["PUT"])
    def update_settings():
        from src.alarms.ipc import write_nudge
        settings = current_app.settings
        data = request.get_json()
        if not data or not isinstance(data, dict):
            return jsonify({"error": "Invalid JSON body"}), 400
        for key, value in data.items():
            settings.set(key, value)
        write_nudge()
        return jsonify({"status": "ok"})

    # --- Themes ---

    @bp.route("/themes", methods=["GET"])
    def list_themes():
        tm = current_app.theme_manager
        names = tm.list_themes()
        active = current_app.settings.get("active_theme", "Classic")
        return jsonify({"themes": names, "active": active})

    @bp.route("/themes/<name>", methods=["GET"])
    def get_theme(name):
        tm = current_app.theme_manager
        theme = tm.get_theme(name)
        if theme is None:
            return jsonify({"error": "Theme not found"}), 404
        return jsonify(theme)

    @bp.route("/themes", methods=["POST"])
    def create_theme():
        from src.alarms.ipc import write_nudge
        tm = current_app.theme_manager
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON body"}), 400
        try:
            theme = tm.save_theme(data)
            write_nudge()
            return jsonify(theme), 201
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @bp.route("/themes/<name>", methods=["PUT"])
    def update_theme(name):
        from src.alarms.ipc import write_nudge
        tm = current_app.theme_manager
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON body"}), 400
        data["name"] = name
        try:
            theme = tm.save_theme(data)
            write_nudge()
            return jsonify(theme)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @bp.route("/themes/<name>", methods=["DELETE"])
    def delete_theme(name):
        from src.alarms.ipc import write_nudge
        tm = current_app.theme_manager
        try:
            tm.delete_theme(name)
            write_nudge()
            return jsonify({"status": "ok"})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @bp.route("/themes/<name>/activate", methods=["POST"])
    def activate_theme(name):
        from src.alarms.ipc import write_nudge
        tm = current_app.theme_manager
        try:
            tm.set_active(name)
            write_nudge()
            return jsonify({"status": "ok", "active": name})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @bp.route("/themes/<name>/export", methods=["GET"])
    def export_theme(name):
        tm = current_app.theme_manager
        try:
            json_str = tm.export_theme(name)
            return Response(
                json_str,
                mimetype="application/json",
                headers={"Content-Disposition": f"attachment; filename={name}.json"},
            )
        except ValueError as e:
            return jsonify({"error": str(e)}), 404

    @bp.route("/themes/import", methods=["POST"])
    def import_theme():
        from src.alarms.ipc import write_nudge
        tm = current_app.theme_manager
        if request.content_type and "multipart" in request.content_type:
            if "file" not in request.files:
                return jsonify({"error": "No file part"}), 400
            file = request.files["file"]
            json_str = file.read().decode("utf-8")
        else:
            json_str = request.get_data(as_text=True)
        try:
            theme = tm.import_theme(json_str)
            write_nudge()
            return jsonify(theme), 201
        except (json.JSONDecodeError, ValueError) as e:
            return jsonify({"error": str(e)}), 400

    # --- Alarms ---

    @bp.route("/alarms", methods=["GET"])
    def list_alarms():
        from src.config.settings import list_alarms as _list_alarms
        return jsonify(_list_alarms())

    @bp.route("/alarms", methods=["POST"])
    def create_alarm():
        from src.config.settings import create_alarm as _create_alarm
        from src.alarms.ipc import write_nudge
        data = request.get_json()
        if not data or "time" not in data:
            return jsonify({"error": "Missing 'time' field"}), 400
        alarm = _create_alarm(data)
        write_nudge()
        return jsonify({"id": alarm["id"], "status": "created"}), 201

    @bp.route("/alarms/<int:alarm_id>", methods=["PUT"])
    def update_alarm(alarm_id):
        from src.config.settings import update_alarm as _update_alarm
        from src.alarms.ipc import write_nudge
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON body"}), 400
        _update_alarm(alarm_id, data)
        write_nudge()
        return jsonify({"status": "ok"})

    @bp.route("/alarms/<int:alarm_id>", methods=["DELETE"])
    def delete_alarm(alarm_id):
        from src.config.settings import delete_alarm as _delete_alarm
        from src.alarms.ipc import write_nudge
        _delete_alarm(alarm_id)
        write_nudge()
        return jsonify({"status": "ok"})

    # --- Uploads (images) ---

    @bp.route("/uploads", methods=["POST"])
    def upload_file():
        if "file" not in request.files:
            return jsonify({"error": "No file part"}), 400
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No selected file"}), 400

        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in ALLOWED_IMAGE_EXT:
            return jsonify({"error": f"File type not allowed. Allowed: {ALLOWED_IMAGE_EXT}"}), 400

        safe_name = _sanitize_filename(file.filename)
        if not safe_name:
            return jsonify({"error": "Invalid filename"}), 400

        # Always save as PNG after resizing
        safe_name = os.path.splitext(safe_name)[0] + ".png"
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        path = os.path.join(UPLOAD_DIR, safe_name)

        # Resize image to fit clock face
        try:
            img = Image.open(file.stream)
            img = img.convert("RGBA")
        except Exception:
            return jsonify({"error": "Could not process image file"}), 400
        if img.width > MAX_IMAGE_SIZE or img.height > MAX_IMAGE_SIZE:
            img.thumbnail((MAX_IMAGE_SIZE, MAX_IMAGE_SIZE), Image.LANCZOS)
        img.save(path, "PNG")

        return jsonify({"status": "ok", "path": path, "filename": safe_name, "url": f"/api/uploads/{safe_name}"}), 201

    @bp.route("/uploads/<filename>", methods=["GET"])
    def serve_upload(filename):
        """Serve an uploaded file."""
        abs_dir = os.path.abspath(UPLOAD_DIR)
        return send_from_directory(abs_dir, filename)

    # --- Sounds ---

    @bp.route("/sounds", methods=["GET"])
    def list_sounds():
        os.makedirs(SOUNDS_DIR, exist_ok=True)
        sounds = []
        for f in os.listdir(SOUNDS_DIR):
            ext = f.rsplit(".", 1)[-1].lower() if "." in f else ""
            if ext in ALLOWED_SOUND_EXT:
                sounds.append(f.rsplit(".", 1)[0])
        return jsonify(sorted(set(sounds)))

    @bp.route("/sounds", methods=["POST"])
    def upload_sound():
        if "file" not in request.files:
            return jsonify({"error": "No file part"}), 400
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No selected file"}), 400

        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in ALLOWED_SOUND_EXT:
            return jsonify({"error": f"File type not allowed. Allowed: {ALLOWED_SOUND_EXT}"}), 400

        safe_name = _sanitize_filename(file.filename)
        if not safe_name:
            return jsonify({"error": "Invalid filename"}), 400

        os.makedirs(SOUNDS_DIR, exist_ok=True)
        path = os.path.join(SOUNDS_DIR, safe_name)
        file.save(path)
        return jsonify({"status": "ok", "filename": safe_name}), 201

    # --- Timezones ---

    @bp.route("/timezones", methods=["GET"])
    def list_timezones():
        query = request.args.get("q", "").lower()
        now_utc = datetime.now(timezone.utc)
        result = []
        for tz_name in sorted(available_timezones()):
            if query and query not in tz_name.lower():
                continue
            try:
                tz = ZoneInfo(tz_name)
                offset = now_utc.astimezone(tz).utcoffset()
                total_seconds = int(offset.total_seconds())
                hours, remainder = divmod(abs(total_seconds), 3600)
                minutes = remainder // 60
                sign = "+" if total_seconds >= 0 else "-"
                offset_str = f"GMT{sign}{hours:02d}:{minutes:02d}"
            except Exception:
                offset_str = ""
            result.append({"name": tz_name, "offset": offset_str})
        return jsonify(result)

    # --- Status ---

    @bp.route("/status", methods=["GET"])
    def get_status():
        settings = current_app.settings
        tm = current_app.theme_manager
        return jsonify({
            "timezone": settings.get("timezone", "UTC"),
            "active_theme": settings.get("active_theme", "Classic"),
            "themes": tm.list_themes(),
        })

    # --- Power ---

    @bp.route("/power", methods=["GET"])
    def get_power():
        from src.power.manager import PowerManager
        settings = current_app.settings
        return jsonify({
            "brightness": int(settings.get("brightness", "100")),
            "dim_brightness": int(settings.get("dim_brightness", "30")),
            "dim_start": settings.get("dim_start", ""),
            "dim_end": settings.get("dim_end", ""),
            "current_brightness": PowerManager.get_brightness(),
        })

    @bp.route("/power", methods=["PUT"])
    def set_power():
        from src.power.manager import PowerManager
        settings = current_app.settings
        data = request.get_json()
        if not data or not isinstance(data, dict):
            return jsonify({"error": "Invalid JSON body"}), 400

        allowed = {"brightness", "dim_brightness", "dim_start", "dim_end"}
        for key, value in data.items():
            if key in allowed:
                settings.set(key, str(value))

        if "brightness" in data:
            PowerManager.set_brightness(int(data["brightness"]))

        return jsonify({"status": "ok"})

    # --- Alarm control (snooze/dismiss via file-based IPC) ---

    @bp.route("/alarms/active", methods=["GET"])
    def alarm_active():
        from src.alarms.ipc import read_alarm_state
        state = read_alarm_state()
        return jsonify(state)

    @bp.route("/alarms/snooze", methods=["POST"])
    def snooze_alarm():
        from src.alarms.ipc import write_alarm_command, read_alarm_state
        state = read_alarm_state()
        if not state.get("active"):
            return jsonify({"error": "No active alarm"}), 404
        data = request.get_json() or {}
        delay = int(data.get("delay", 300))
        delay = max(60, min(delay, 1800))
        write_alarm_command("snooze", delay=delay)
        return jsonify({"status": "snoozed", "delay": delay})

    @bp.route("/alarms/dismiss", methods=["POST"])
    def dismiss_alarm():
        from src.alarms.ipc import write_alarm_command, read_alarm_state
        state = read_alarm_state()
        if not state.get("active"):
            return jsonify({"error": "No active alarm"}), 404
        write_alarm_command("dismiss")
        return jsonify({"status": "dismissed"})

    # --- Agenda Events ---

    @bp.route("/agenda", methods=["GET"])
    def list_agenda():
        from src.config.settings import list_agenda_events
        return jsonify(list_agenda_events())

    @bp.route("/agenda", methods=["POST"])
    def create_agenda_event():
        from src.config.settings import create_agenda_event as _create_event
        from src.alarms.ipc import write_nudge
        data = request.get_json()
        if not data or "title" not in data or "start_time" not in data or "end_time" not in data:
            return jsonify({"error": "Missing required fields: title, start_time, end_time"}), 400
        _TIME_RE = re.compile(r'^\d{1,2}:\d{2}$')
        if not _TIME_RE.match(data["start_time"]) or not _TIME_RE.match(data["end_time"]):
            return jsonify({"error": "Invalid time format. Use HH:MM"}), 400
        event = _create_event(data)
        write_nudge()
        return jsonify({"id": event["id"], "status": "created"}), 201

    @bp.route("/agenda/<int:event_id>", methods=["PUT"])
    def update_agenda_event(event_id):
        from src.config.settings import update_agenda_event as _update_event
        from src.alarms.ipc import write_nudge
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON body"}), 400
        _update_event(event_id, data)
        write_nudge()
        return jsonify({"status": "ok"})

    @bp.route("/agenda/<int:event_id>", methods=["DELETE"])
    def delete_agenda_event(event_id):
        from src.config.settings import delete_agenda_event as _delete_event
        from src.alarms.ipc import write_nudge
        _delete_event(event_id)
        write_nudge()
        return jsonify({"status": "ok"})

    # --- Dial ---

    @bp.route("/dial", methods=["GET"])
    def get_dial():
        from src.alarms.ipc import read_dial_state
        return jsonify(read_dial_state())

    @bp.route("/dial", methods=["PUT"])
    def update_dial():
        from src.alarms.ipc import write_dial_state, read_dial_state, write_nudge
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON body"}), 400
        state = read_dial_state()
        allowed = set(state.keys())
        for key, value in data.items():
            if key in allowed:
                state[key] = value
        write_dial_state(state)
        write_nudge()
        return jsonify(state)

    @bp.route("/dial/reset", methods=["POST"])
    def reset_dial():
        from src.alarms.ipc import reset_dial_state, write_nudge
        reset_dial_state()
        write_nudge()
        return jsonify({"status": "ok"})

    # --- System (reboot / shutdown) ---

    @bp.route("/reboot", methods=["POST"])
    def reboot():
        subprocess.Popen(["sudo", "reboot"])
        return jsonify({"status": "rebooting"})

    @bp.route("/shutdown", methods=["POST"])
    def shutdown():
        subprocess.Popen(["sudo", "poweroff"])
        return jsonify({"status": "shutting_down"})

    # --- Version & Updates ---

    @bp.route("/version", methods=["GET"])
    def get_version():
        return jsonify({"version": __version__})

    @bp.route("/update/check", methods=["GET"])
    def check_update():
        """Check GitHub for a newer version by reading the remote _version.py."""
        ver = __version__
        settings = current_app.settings
        repo = settings.get("github_repo", "")
        if not repo:
            return jsonify({"current": ver, "latest": None, "update_available": False})
        url = f"https://raw.githubusercontent.com/{repo}/refs/heads/main/src/_version.py"
        req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8")
            # Parse __version__ = "x.y.z" from the file
            match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
            latest = match.group(1) if match else None
            return jsonify({
                "current": ver,
                "latest": latest,
                "update_available": bool(latest and latest != ver),
            })
        except Exception:
            return jsonify({"current": ver, "latest": None, "update_available": False})

    @bp.route("/update/run", methods=["POST"])
    def run_update():
        """Run the update script in the background."""
        script = os.path.join(
            os.path.dirname(__file__), "..", "..", "scripts", "update.sh"
        )
        script = os.path.abspath(script)
        if not os.path.isfile(script):
            return jsonify({"error": "Update script not found"}), 404
        try:
            subprocess.Popen(
                ["sudo", "bash", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return jsonify({"status": "updating", "message": "Update started. The service will restart shortly."})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    # --- Theme auto-cycle ---

    _cycle_timer = None

    def _start_theme_cycle():
        """Start or restart the theme auto-cycle timer based on settings."""
        nonlocal _cycle_timer
        if _cycle_timer is not None:
            _cycle_timer.cancel()
            _cycle_timer = None
        app = current_app._get_current_object()
        settings = app.settings
        tm = app.theme_manager
        enabled = settings.get("theme_cycle_enabled", False)
        if not enabled:
            return
        interval = max(60, int(settings.get("theme_cycle_interval", 3600)))
        randomize = settings.get("theme_cycle_random", False)

        def _cycle():
            nonlocal _cycle_timer
            with app.app_context():
                themes = tm.list_themes()
                if len(themes) < 2:
                    return
                current = settings.get("active_theme", "Classic")
                if randomize:
                    choices = [t for t in themes if t != current]
                    next_theme = random.choice(choices) if choices else current
                else:
                    try:
                        idx = themes.index(current)
                    except ValueError:
                        idx = -1
                    next_theme = themes[(idx + 1) % len(themes)]
                tm.set_active(next_theme)
                settings.set("active_theme", next_theme)
                _start_theme_cycle()

        _cycle_timer = threading.Timer(interval, _cycle)
        _cycle_timer.daemon = True
        _cycle_timer.start()

    @bp.route("/theme-cycle", methods=["GET"])
    def get_theme_cycle():
        settings = current_app.settings
        return jsonify({
            "enabled": bool(settings.get("theme_cycle_enabled", False)),
            "interval": int(settings.get("theme_cycle_interval", 3600)),
            "random": bool(settings.get("theme_cycle_random", False)),
        })

    @bp.route("/theme-cycle", methods=["PUT"])
    def set_theme_cycle():
        settings = current_app.settings
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON body"}), 400
        if "enabled" in data:
            settings.set("theme_cycle_enabled", bool(data["enabled"]))
        if "interval" in data:
            settings.set("theme_cycle_interval", max(60, int(data["interval"])))
        if "random" in data:
            settings.set("theme_cycle_random", bool(data["random"]))
        _start_theme_cycle()
        return jsonify({"status": "ok"})

    return bp


def _sanitize_filename(filename):
    """Sanitize a filename to only allow safe characters."""
    safe_name = "".join(
        c for c in os.path.basename(filename)
        if c.isalnum() or c in (".", "-", "_")
    )
    return safe_name if safe_name else None
