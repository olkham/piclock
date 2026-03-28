"""Flask application factory."""

import os

from flask import Flask

from src.faces.manager import FaceManager
from src.themes.dial_manager import DialThemeManager
from src.web.api import create_api_blueprint
from src.web.views import create_views_blueprint


def create_app(theme_manager, settings):
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static"),
    )
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB upload limit

    # Store shared objects for access in routes
    app.theme_manager = theme_manager
    app.dial_theme_manager = DialThemeManager(settings)
    app.face_manager = FaceManager(settings)
    app.settings = settings

    # Register blueprints
    app.register_blueprint(create_api_blueprint(), url_prefix="/api")
    app.register_blueprint(create_views_blueprint())

    return app
