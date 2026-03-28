import glob
import math
import os
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


def _init_kms_display(windowed):
    """Try console-capable video drivers in order until one works."""
    flags = pygame.DOUBLEBUF
    if not windowed:
        flags |= pygame.FULLSCREEN | pygame.NOFRAME

    # Auto-detect the DRM card device for SDL2
    dri_cards = sorted(glob.glob('/dev/dri/card*'))
    if dri_cards:
        os.environ.setdefault('SDL_VIDEO_KMSDRM_DEVICE', dri_cards[0])
        print(f"KMS: DRM device: {dri_cards[0]}")

    # Log diagnostic info
    print(f"KMS: pygame {pygame.version.ver}, "
          f"SDL {'.'.join(str(x) for x in pygame.get_sdl_version())}")
    print(f"KMS: TTY = {os.ttyname(0) if os.isatty(0) else 'none'}, "
          f"uid = {os.getuid()}, groups = {os.getgroups()}")

    last_err = None
    for driver in _KMS_DRIVER_ORDER:
        os.environ['SDL_VIDEODRIVER'] = driver
        try:
            # Re-init pygame with the new driver
            pygame.quit()
            pygame.init()
            try:
                screen = pygame.display.set_mode(
                    (DISPLAY_SIZE, DISPLAY_SIZE), flags | pygame.HWSURFACE
                )
            except pygame.error:
                screen = pygame.display.set_mode(
                    (DISPLAY_SIZE, DISPLAY_SIZE), flags
                )
            print(f"KMS: using SDL driver '{driver}'")
            return screen
        except pygame.error as e:
            last_err = e
            print(f"KMS: driver '{driver}' failed ({e}), trying next...")
            continue

    raise RuntimeError(
        f"No working console video driver found. Tried: {_KMS_DRIVER_ORDER}. "
        f"Last error: {last_err}. "
        f"Check that /dev/dri/card* or /dev/fb0 exist and the user "
        f"has permission (video/render groups)."
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
