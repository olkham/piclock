"""PiClock3 — Main entry point."""

import argparse
import signal
import sys
import threading

from src.clock.display import init_display, shutdown_display
from src.clock.engine import ClockEngine
from src.config.settings import Settings
from src.themes.manager import ThemeManager


def main():
    parser = argparse.ArgumentParser(description="PiClock3 — Analogue clock for Pi Zero")
    parser.add_argument("--no-web", action="store_true", help="Disable the web interface")
    parser.add_argument("--port", type=int, default=8080, help="Web interface port (default: 8080)")
    parser.add_argument("--host", default="0.0.0.0", help="Web interface host (default: 0.0.0.0)")
    parser.add_argument("--theme", type=str, help="Initial theme name")
    parser.add_argument("--timezone", type=str, help="Timezone (e.g., America/New_York)")
    parser.add_argument("--windowed", action="store_true", help="Run in windowed mode instead of fullscreen")
    args = parser.parse_args()

    # Initialize settings and theme manager
    settings = Settings()
    if args.timezone:
        settings.set("timezone", args.timezone)
    if not settings.get("timezone"):
        settings.set("timezone", "UTC")

    theme_manager = ThemeManager(settings)
    if args.theme:
        try:
            theme_manager.set_active(args.theme)
        except ValueError:
            print(f"Warning: Theme '{args.theme}' not found, using default")

    # Initialize display
    init_display(windowed=args.windowed, settings=settings)

    # Create engine
    engine = ClockEngine(theme_manager, settings)

    # Handle signals for graceful shutdown
    def handle_shutdown(signum, frame):
        engine.stop()

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # Start web server in background thread
    web_thread = None
    if not args.no_web:
        from src.web.app import create_app

        app = create_app(theme_manager, settings)
        web_thread = threading.Thread(
            target=lambda: app.run(host=args.host, port=args.port, use_reloader=False),
            daemon=True,
        )
        web_thread.start()
        print(f"Web interface available at http://{args.host}:{args.port}")

    # Start power manager
    from src.power.manager import PowerManager

    power_manager = PowerManager(settings)
    power_manager.start()

    # Start alarm scheduler
    from src.alarms.scheduler import AlarmScheduler

    alarm_scheduler = AlarmScheduler(settings, engine)
    alarm_scheduler.start()

    # Attach scheduler to Flask app for snooze/dismiss API
    if not args.no_web:
        app.alarm_scheduler = alarm_scheduler

    try:
        # Run clock (blocks)
        engine.run()
    finally:
        alarm_scheduler.stop()
        power_manager.stop()
        shutdown_display()


if __name__ == "__main__":
    main()
