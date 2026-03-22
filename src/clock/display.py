import os
import sys
import platform

import numpy as np
import pygame

DISPLAY_SIZE = 720

_screen = None

# Persistent Pygame surface reused every frame (avoids per-frame surface creation)
_frame_pg_surface = None


def apply_sdl_hints(settings=None, use_kms=False):
    """Apply SDL environment hints. Must be called BEFORE pygame.init().

    When use_kms=True, forces the KMS/DRM video driver which bypasses X11
    entirely. This gives direct framebuffer access with hardware vsync and
    eliminates the Xorg compositing overhead that causes tearing.
    """
    if use_kms:
        os.environ['SDL_VIDEODRIVER'] = 'kmsdrm'
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


def init_display(windowed=False, settings=None, use_kms=False):
    """Initialize Pygame display. Fullscreen by default.

    Args:
        windowed: Run in a window instead of fullscreen.
        settings: Settings object for reading render preferences.
        use_kms: Force KMS/DRM mode (bypasses X11, requires console access).
    """
    global _screen, _frame_pg_surface

    apply_sdl_hints(settings, use_kms=use_kms)
    pygame.init()

    flags = pygame.DOUBLEBUF
    if not windowed:
        flags |= pygame.FULLSCREEN | pygame.NOFRAME

    # Try hardware surface (available in KMS/DRM mode for zero-copy page flips)
    try:
        _screen = pygame.display.set_mode(
            (DISPLAY_SIZE, DISPLAY_SIZE), flags | pygame.HWSURFACE
        )
    except pygame.error:
        _screen = pygame.display.set_mode(
            (DISPLAY_SIZE, DISPLAY_SIZE), flags
        )

    if windowed:
        pygame.display.set_caption("PiClock3")
    else:
        pygame.mouse.set_visible(False)

    # Create a persistent 24-bit surface matching the screen format
    _frame_pg_surface = pygame.Surface((DISPLAY_SIZE, DISPLAY_SIZE), 0, 24)

    driver = pygame.display.get_driver()
    print(f"Display: {DISPLAY_SIZE}x{DISPLAY_SIZE} via {driver}"
          f" ({'windowed' if windowed else 'fullscreen'})")

    return _screen


def show_frame_from_buffer(rgb_buffer):
    """Write an RGB byte buffer directly to the screen and flip.

    This is faster than creating a Pygame Surface + blit because it writes
    directly into the persistent surface's pixel buffer via surfarray,
    eliminating per-frame Surface allocation.
    """
    if _screen is None:
        raise RuntimeError("Display not initialized. Call init_display() first.")
    assert _frame_pg_surface is not None
    arr = np.frombuffer(rgb_buffer, dtype=np.uint8).reshape(DISPLAY_SIZE, DISPLAY_SIZE, 3)
    pygame.surfarray.blit_array(_frame_pg_surface, arr.transpose(1, 0, 2))
    _screen.blit(_frame_pg_surface, (0, 0))
    pygame.display.flip()


def shutdown_display():
    """Cleanly shut down Pygame display."""
    pygame.quit()
