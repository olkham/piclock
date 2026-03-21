"""Web UI view routes."""

from flask import Blueprint, current_app, render_template


def create_views_blueprint():
    bp = Blueprint("views", __name__)

    @bp.route("/")
    def index():
        settings = current_app.settings
        tm = current_app.theme_manager
        return render_template(
            "index.html",
            timezone=settings.get("timezone", "UTC"),
            active_theme=settings.get("active_theme", "Classic"),
            themes=tm.list_themes(),
        )

    @bp.route("/themes")
    def themes():
        tm = current_app.theme_manager
        return render_template(
            "themes.html",
            themes=tm.list_themes(),
            active_theme=current_app.settings.get("active_theme", "Classic"),
        )

    @bp.route("/alarms")
    def alarms():
        return render_template("alarms.html")

    @bp.route("/agenda")
    def agenda():
        return render_template("agenda.html")

    @bp.route("/clock")
    def clock_display():
        settings = current_app.settings
        return render_template(
            "clock.html",
            timezone=settings.get("timezone", "UTC"),
            active_theme=settings.get("active_theme", "Classic"),
        )

    return bp
