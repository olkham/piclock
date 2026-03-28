import glob
import math
import os
import subprocess
import sys
import platform

import numpy as np
import pygame

DISPLAY_SIZE = 720

_screen = None

# Persistent Pygame surface reused every frame (avoids per-frame surface creation)
_frame_pg_surface = None

# Cached numpy views for the RGB buffer — avoids per-frame frombuffer/reshape/transpose
_display_arr = None
_display_arr_t = None


def apply_sdl_hints(settings=None, use_kms=False):
    """Apply SDL environment hints. Must be called BEFORE pygame.init().

    When use_kms=True, tries KMS/DRM first, then falls back through
    fbdev and other console-capable drivers. This covers boards where
    SDL2 was compiled without kmsdrm support (e.g. older Debian images).
    """
    if use_kms:
        # Don't set SDL_VIDEODRIVER yet — we'll try drivers in order
        # during init_display(). Just clear any existing override.
        os.environ.pop('SDL_VIDEODRIVER', None)
        # KMS/DRM handles vsync via page flipping — no compositor involved
        return

    if settings is None:
        os.environ.setdefault('SDL_VIDEO_X11_NET_WM_BYPASS_COMPOSITOR', '0')
        return

    # Configurable video driver (auto, x11, kmsdrm, wayland)
    driver = settings.get("render_video_driver", "auto")
    if driver and driver != "auto":
        os.environ['SDL_VIDEODRIVER'] = driver
    else:
        # Under X11, respect compositor bypass setting
        bypass = settings.get("render_bypass_compositor", False)
        os.environ['SDL_VIDEO_X11_NET_WM_BYPASS_COMPOSITOR'] = '1' if bypass else '0'


# Console-capable SDL2 video drivers, in preference order.
_KMS_DRIVER_ORDER = ['kmsdrm', 'fbdev', 'directfb', 'svgalib']


def init_display(windowed=False, settings=None, use_kms=False):
    """Initialize Pygame display. Fullscreen by default.

    Args:
        windowed: Run in a window instead of fullscreen.
        settings: Settings object for reading render preferences.
        use_kms: Force KMS/DRM mode (bypasses X11, requires console access).
    """
    global _screen, _frame_pg_surface

    apply_sdl_hints(settings, use_kms=use_kms)

    if use_kms:
        _screen = _init_kms_display(windowed)
    else:
        pygame.init()
        _screen = _init_normal_display(windowed)

    if windowed:
        pygame.display.set_caption("PiClock")
    else:
        pygame.mouse.set_visible(False)

    # Create a persistent 24-bit surface matching the screen format
    _frame_pg_surface = pygame.Surface((DISPLAY_SIZE, DISPLAY_SIZE), 0, 24)

    driver = pygame.display.get_driver()
    print(f"Display: {DISPLAY_SIZE}x{DISPLAY_SIZE} via {driver}"
          f" ({'windowed' if windowed else 'fullscreen'})")

    return _screen


def _probe_driver(driver):
    """Test if a video driver initializes without crashing.

    Runs in a subprocess so native SEGV in SDL2 doesn't kill us.
    """
    env = os.environ.copy()
    env['SDL_VIDEODRIVER'] = driver
    env['PYTHONUNBUFFERED'] = '1'
    env['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
    probe = (
        'import pygame, sys; '
        'pygame.init(); '
        'i = pygame.display.Info(); '
        'print(f"{i.current_w}x{i.current_h}"); '
        'sys.exit(0)'
    )
    try:
        result = subprocess.run(
            [sys.executable, '-c', probe],
            env=env, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            res = result.stdout.strip()
            print(f"KMS: probe driver '{driver}' -> ok ({res})", flush=True)
            return True
        err = (result.stderr or '').strip().rsplit('\n', 1)[-1][:120]
        print(f"KMS: probe driver '{driver}' -> fail "
              f"(rc={result.returncode}, {err})", flush=True)
        return False
    except subprocess.TimeoutExpired:
        print(f"KMS: probe driver '{driver}' -> timeout", flush=True)
        return False
    except Exception as e:
        print(f"KMS: probe driver '{driver}' -> error ({e})", flush=True)
        return False


def _probe_set_mode(driver, label, flags):
    """Test pygame.display.set_mode() in a subprocess.

    SDL2's kmsdrm can SEGV during set_mode (e.g. with Mali GPU drivers).
    Running in a subprocess lets us detect the crash without dying.
    """
    env = os.environ.copy()
    env['SDL_VIDEODRIVER'] = driver
    env['PYTHONUNBUFFERED'] = '1'
    env['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
    probe = (
        f'import pygame,sys;pygame.init();'
        f'pygame.display.set_mode(({DISPLAY_SIZE},{DISPLAY_SIZE}),{flags});'
        f'sys.exit(0)'
    )
    try:
        r = subprocess.run(
            [sys.executable, '-c', probe],
            env=env, capture_output=True, text=True, timeout=10,
        )
        ok = r.returncode == 0
    except Exception:
        ok = False
    tag = 'ok' if ok else 'CRASH/fail'
    print(f"KMS: probe set_mode {driver}/{label} (flags={flags}) -> {tag}",
          flush=True)
    return ok


def _init_kms_display(windowed):
    """Try console-capable video drivers in order until one works."""
    # Auto-detect the DRM card device for SDL2
    dri_cards = sorted(glob.glob('/dev/dri/card*'))
    if dri_cards:
        os.environ.setdefault('SDL_VIDEO_KMSDRM_DEVICE', dri_cards[0])
        print(f"KMS: DRM device: {dri_cards[0]}", flush=True)

    # Log diagnostic info
    print(f"KMS: pygame {pygame.version.ver}, "
          f"SDL {'.'.join(str(x) for x in pygame.get_sdl_version())}",
          flush=True)
    print(f"KMS: TTY = {os.ttyname(0) if os.isatty(0) else 'none'}, "
          f"uid = {os.getuid()}, groups = {os.getgroups()}",
          flush=True)

    # --- Phase 1: find drivers whose pygame.init() doesn't crash ---
    safe_drivers = []
    for driver in _KMS_DRIVER_ORDER:
        if _probe_driver(driver):
            safe_drivers.append(driver)

    if not safe_drivers:
        raise RuntimeError(
            f"No working console video driver found. "
            f"All driver probes failed: {_KMS_DRIVER_ORDER}. "
            f"Check /dev/dri/card*, /dev/fb0 and video/render groups."
        )

    # --- Phase 2: find a (driver, flags) combo whose set_mode doesn't crash ---
    # HWSURFACE is a no-op in SDL2/pygame2 but triggers Mali GPU driver SEGVs,
    # so we don't include it. Ordered from most to least desirable.
    mode_attempts = [
        ("fullscreen", pygame.FULLSCREEN | pygame.NOFRAME | pygame.DOUBLEBUF),
        ("windowed",   pygame.DOUBLEBUF),
        ("bare",       0),
    ]

    for driver in safe_drivers:
        for label, flags in mode_attempts:
            if not _probe_set_mode(driver, label, flags):
                continue

            # Probe passed — safe to do for real in our process
            os.environ['SDL_VIDEODRIVER'] = driver
            pygame.quit()
            pygame.init()

            try:
                info = pygame.display.Info()
                print(f"KMS: {driver} reports "
                      f"{info.current_w}x{info.current_h}", flush=True)
                modes = pygame.display.list_modes()
                if modes and modes != -1:
                    print(f"KMS: available modes: "
                          f"{modes[:5]}{'...' if len(modes) > 5 else ''}",
                          flush=True)
            except Exception:
                pass

            screen = pygame.display.set_mode(
                (DISPLAY_SIZE, DISPLAY_SIZE), flags
            )
            print(f"KMS: using driver '{driver}', mode '{label}'",
                  flush=True)
            return screen

    raise RuntimeError(
        f"No working display mode found. "
        f"Safe drivers: {safe_drivers} (from {_KMS_DRIVER_ORDER}). "
        f"All set_mode probes crashed or failed."
    )


def _init_normal_display(windowed):
    """Standard display init (X11/Wayland)."""
    flags = pygame.DOUBLEBUF
    if not windowed:
        flags |= pygame.FULLSCREEN | pygame.NOFRAME

    try:
        return pygame.display.set_mode(
            (DISPLAY_SIZE, DISPLAY_SIZE), flags | pygame.HWSURFACE
        )
    except pygame.error:
        return pygame.display.set_mode(
            (DISPLAY_SIZE, DISPLAY_SIZE), flags
        )


def show_frame_from_buffer(rgb_buffer):
    """Write an RGB byte buffer directly to the screen and flip.

    This is faster than creating a Pygame Surface + blit because it writes
    directly into the persistent surface's pixel buffer via surfarray,
    eliminating per-frame Surface allocation.
    """
    global _display_arr, _display_arr_t
    if _screen is None:
        raise RuntimeError("Display not initialized. Call init_display() first.")
    assert _frame_pg_surface is not None
    # Cache numpy view + transposed view; re-bind when the buffer changes
    # (clock and dial renderers use separate bytearrays)
    if _display_arr is None or _display_arr.base is not rgb_buffer:
        _display_arr = np.frombuffer(rgb_buffer, dtype=np.uint8).reshape(DISPLAY_SIZE, DISPLAY_SIZE, 3)
        _display_arr_t = _display_arr.transpose(1, 0, 2)
    pygame.surfarray.blit_array(_frame_pg_surface, _display_arr_t)
    _screen.blit(_frame_pg_surface, (0, 0))
    pygame.display.flip()


def shutdown_display():
    """Cleanly shut down Pygame display."""
    pygame.quit()
