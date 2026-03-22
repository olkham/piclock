"""PiClock3 — Main entry point."""

import argparse
import multiprocessing
import os
import signal
import sys

from src.clock.display import init_display, shutdown_display
from src.clock.engine import ClockEngine
from src.config.settings import Settings
from src.themes.manager import ThemeManager


def _run_flask_subprocess(host, port):
    """Flask server entry point — runs in a separate OS process.

    Running Flask in its own process gives it a separate GIL, so HTTP
    request handling can never preempt the render loop on the main
    process.  Settings and ThemeManager are file-backed, so each process
    gets its own instances reading the same JSON files.
    """
    # Pin Flask to cores 1-3 (leave core 0 for the render loop)
    try:
        os.sched_setaffinity(0, {1, 2, 3})
    except (OSError, AttributeError):
        pass  # Not available on Windows/macOS

    from src.config.settings import Settings as _Settings
    from src.themes.manager import ThemeManager as _TM
    from src.web.app import create_app

    settings = _Settings()
    theme_manager = _TM(settings)
    app = create_app(theme_manager, settings)
    app.run(host=host, port=port, use_reloader=False)


def main():
    parser = argparse.ArgumentParser(description="PiClock3 — Analogue clock for Pi Zero")
    parser.add_argument("--no-web", action="store_true", help="Disable the web interface")
    parser.add_argument("--port", type=int, default=8080, help="Web interface port (default: 8080)")
    parser.add_argument("--host", default="0.0.0.0", help="Web interface host (default: 0.0.0.0)")
    parser.add_argument("--theme", type=str, help="Initial theme name")
    parser.add_argument("--timezone", type=str, help="Timezone (e.g., America/New_York)")
    parser.add_argument("--windowed", action="store_true", help="Run in windowed mode instead of fullscreen")
    parser.add_argument("--kms", action="store_true",
                        help="Use KMS/DRM video driver (bypass X11 for tear-free rendering)")
    parser.add_argument("--debug-fps", action="store_true",
                        help="Log frame timing diagnostics to stderr")
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

    # Start web server in a separate OS process (own GIL — zero render interference)
    flask_proc = None
    if not args.no_web:
        ctx = multiprocessing.get_context("spawn")
        flask_proc = ctx.Process(
            target=_run_flask_subprocess,
            args=(args.host, args.port),
            daemon=True,
        )
        flask_proc.start()
        print(f"Web interface available at http://{args.host}:{args.port}")

    # Initialize display (must happen AFTER spawning Flask to avoid
    # inheriting Pygame state in the child on fork-based platforms)
    init_display(windowed=args.windowed, settings=settings, use_kms=args.kms)

    # Create engine
    engine = ClockEngine(theme_manager, settings)
    if args.debug_fps:
        engine.debug_fps = True

    # Handle signals for graceful shutdown
    def handle_shutdown(signum, frame):
        engine.stop()

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # Start power manager
    from src.power.manager import PowerManager

    power_manager = PowerManager(settings)
    power_manager.start()

    # Start alarm scheduler (stays in main process — needs engine.set_overlay)
    # Polled from the engine's render loop via set_alarm_scheduler() — no
    # background timer threads that could steal the GIL and cause stutter.
    from src.alarms.scheduler import AlarmScheduler

    alarm_scheduler = AlarmScheduler(settings, engine)
    alarm_scheduler.start()
    engine.set_alarm_scheduler(alarm_scheduler)

    try:
        # Run clock (blocks)
        engine.run()
    finally:
        alarm_scheduler.stop()
        power_manager.stop()
        if flask_proc and flask_proc.is_alive():
            flask_proc.terminate()
        shutdown_display()


if __name__ == "__main__":
    main()
