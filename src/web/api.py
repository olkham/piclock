"""REST API routes."""

import json
import os
import re
from datetime import datetime, timezone, timedelta
from zoneinfo import available_timezones, ZoneInfo

from flask import Blueprint, Response, current_app, jsonify, request, send_from_directory
from PIL import Image

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
        settings = current_app.settings
        data = request.get_json()
        if not data or not isinstance(data, dict):
            return jsonify({"error": "Invalid JSON body"}), 400
        for key, value in data.items():
            settings.set(key, value)
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
        tm = current_app.theme_manager
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON body"}), 400
        try:
            theme = tm.save_theme(data)
            return jsonify(theme), 201
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @bp.route("/themes/<name>", methods=["PUT"])
    def update_theme(name):
        tm = current_app.theme_manager
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON body"}), 400
        data["name"] = name
        try:
            theme = tm.save_theme(data)
            return jsonify(theme)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @bp.route("/themes/<name>", methods=["DELETE"])
    def delete_theme(name):
        tm = current_app.theme_manager
        try:
            tm.delete_theme(name)
            return jsonify({"status": "ok"})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @bp.route("/themes/<name>/activate", methods=["POST"])
    def activate_theme(name):
        tm = current_app.theme_manager
        try:
            tm.set_active(name)
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
            return jsonify(theme), 201
        except (json.JSONDecodeError, ValueError) as e:
            return jsonify({"error": str(e)}), 400

    # --- Alarms ---

    @bp.route("/alarms", methods=["GET"])
    def list_alarms():
        from src.config.settings import get_db
        conn = get_db()
        try:
            rows = conn.execute("SELECT * FROM alarms ORDER BY time").fetchall()
            alarms = [dict(row) for row in rows]
            return jsonify(alarms)
        finally:
            conn.close()

    @bp.route("/alarms", methods=["POST"])
    def create_alarm():
        from src.config.settings import get_db
        data = request.get_json()
        if not data or "time" not in data:
            return jsonify({"error": "Missing 'time' field"}), 400
        conn = get_db()
        try:
            cursor = conn.execute(
                """INSERT INTO alarms (time, days, sound, enabled, label,
                   animation_shape, animation_color, animation_speed,
                   sound_enabled, animation_duration)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    data["time"],
                    data.get("days", ""),
                    data.get("sound", "default"),
                    1 if data.get("enabled", True) else 0,
                    data.get("label", ""),
                    data.get("animation_shape", "border_glow"),
                    data.get("animation_color", "#ff3333"),
                    data.get("animation_speed", "normal"),
                    1 if data.get("sound_enabled", True) else 0,
                    int(data.get("animation_duration", 60)),
                ),
            )
            conn.commit()
            return jsonify({"id": cursor.lastrowid, "status": "created"}), 201
        finally:
            conn.close()

    @bp.route("/alarms/<int:alarm_id>", methods=["PUT"])
    def update_alarm(alarm_id):
        from src.config.settings import get_db
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON body"}), 400
        conn = get_db()
        try:
            conn.execute(
                """UPDATE alarms SET time=?, days=?, sound=?, enabled=?, label=?,
                   animation_shape=?, animation_color=?, animation_speed=?,
                   sound_enabled=?, animation_duration=?
                   WHERE id=?""",
                (
                    data.get("time", ""),
                    data.get("days", ""),
                    data.get("sound", "default"),
                    1 if data.get("enabled", True) else 0,
                    data.get("label", ""),
                    data.get("animation_shape", "border_glow"),
                    data.get("animation_color", "#ff3333"),
                    data.get("animation_speed", "normal"),
                    1 if data.get("sound_enabled", True) else 0,
                    int(data.get("animation_duration", 60)),
                    alarm_id,
                ),
            )
            conn.commit()
            return jsonify({"status": "ok"})
        finally:
            conn.close()

    @bp.route("/alarms/<int:alarm_id>", methods=["DELETE"])
    def delete_alarm(alarm_id):
        from src.config.settings import get_db
        conn = get_db()
        try:
            conn.execute("DELETE FROM alarms WHERE id = ?", (alarm_id,))
            conn.commit()
            return jsonify({"status": "ok"})
        finally:
            conn.close()

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

    # --- Alarm control (snooze/dismiss) ---

    @bp.route("/alarms/active", methods=["GET"])
    def alarm_active():
        scheduler = getattr(current_app, "alarm_scheduler", None)
        if not scheduler:
            return jsonify({"active": False})
        info = scheduler.get_active_alarm_info()
        return jsonify({"active": info is not None, "alarm": info})

    @bp.route("/alarms/snooze", methods=["POST"])
    def snooze_alarm():
        scheduler = getattr(current_app, "alarm_scheduler", None)
        if not scheduler:
            return jsonify({"error": "Scheduler not available"}), 503
        data = request.get_json() or {}
        delay = int(data.get("delay", 300))
        delay = max(60, min(delay, 1800))
        if scheduler.snooze(delay):
            return jsonify({"status": "snoozed", "delay": delay})
        return jsonify({"error": "No active alarm"}), 404

    @bp.route("/alarms/dismiss", methods=["POST"])
    def dismiss_alarm():
        scheduler = getattr(current_app, "alarm_scheduler", None)
        if not scheduler:
            return jsonify({"error": "Scheduler not available"}), 503
        if scheduler.dismiss():
            return jsonify({"status": "dismissed"})
        return jsonify({"error": "No active alarm"}), 404

    # --- Agenda Events ---

    @bp.route("/agenda", methods=["GET"])
    def list_agenda():
        from src.config.settings import get_db
        conn = get_db()
        try:
            rows = conn.execute("SELECT * FROM agenda_events ORDER BY start_time").fetchall()
            return jsonify([dict(row) for row in rows])
        finally:
            conn.close()

    @bp.route("/agenda", methods=["POST"])
    def create_agenda_event():
        from src.config.settings import get_db
        data = request.get_json()
        if not data or "title" not in data or "start_time" not in data or "end_time" not in data:
            return jsonify({"error": "Missing required fields: title, start_time, end_time"}), 400
        _TIME_RE = re.compile(r'^\d{1,2}:\d{2}$')
        if not _TIME_RE.match(data["start_time"]) or not _TIME_RE.match(data["end_time"]):
            return jsonify({"error": "Invalid time format. Use HH:MM"}), 400
        conn = get_db()
        try:
            cursor = conn.execute(
                """INSERT INTO agenda_events (title, start_time, end_time, color, days)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    data["title"],
                    data["start_time"],
                    data["end_time"],
                    data.get("color", "#4488ff"),
                    data.get("days", ""),
                ),
            )
            conn.commit()
            return jsonify({"id": cursor.lastrowid, "status": "created"}), 201
        finally:
            conn.close()

    @bp.route("/agenda/<int:event_id>", methods=["PUT"])
    def update_agenda_event(event_id):
        from src.config.settings import get_db
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON body"}), 400
        conn = get_db()
        try:
            conn.execute(
                """UPDATE agenda_events SET title=?, start_time=?, end_time=?, color=?, days=?
                   WHERE id=?""",
                (
                    data.get("title", ""),
                    data.get("start_time", ""),
                    data.get("end_time", ""),
                    data.get("color", "#4488ff"),
                    data.get("days", ""),
                    event_id,
                ),
            )
            conn.commit()
            return jsonify({"status": "ok"})
        finally:
            conn.close()

    @bp.route("/agenda/<int:event_id>", methods=["DELETE"])
    def delete_agenda_event(event_id):
        from src.config.settings import get_db
        conn = get_db()
        try:
            conn.execute("DELETE FROM agenda_events WHERE id = ?", (event_id,))
            conn.commit()
            return jsonify({"status": "ok"})
        finally:
            conn.close()

    return bp


def _sanitize_filename(filename):
    """Sanitize a filename to only allow safe characters."""
    safe_name = "".join(
        c for c in os.path.basename(filename)
        if c.isalnum() or c in (".", "-", "_")
    )
    return safe_name if safe_name else None
