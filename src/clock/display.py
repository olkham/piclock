import os
import sys
import platform

import numpy as np
import pygame

DISPLAY_SIZE = 720

_screen = None

# Persistent Pygame surface reused every frame (avoids per-frame surface creation)
_frame_pg_surface = None


def apply_sdl_hints(settings=None):
    """Apply SDL environment hints from settings. Must be called BEFORE pygame.init()."""
    if settings is None:
        # Default: don't bypass compositor (enables compositor vsync)
        os.environ.setdefault('SDL_VIDEO_X11_NET_WM_BYPASS_COMPOSITOR', '0')
        return

    bypass = settings.get("render_bypass_compositor", False)
    os.environ['SDL_VIDEO_X11_NET_WM_BYPASS_COMPOSITOR'] = '1' if bypass else '0'


def init_display(windowed=False, settings=None):
    """Initialize Pygame display. Fullscreen by default."""
    global _screen, _frame_pg_surface

    apply_sdl_hints(settings)
    pygame.init()

    if windowed:
        _screen = pygame.display.set_mode(
            (DISPLAY_SIZE, DISPLAY_SIZE), pygame.DOUBLEBUF
        )
        pygame.display.set_caption("PiClock3")
    else:
        _screen = pygame.display.set_mode(
            (DISPLAY_SIZE, DISPLAY_SIZE),
            pygame.FULLSCREEN | pygame.NOFRAME | pygame.DOUBLEBUF,
        )
        pygame.mouse.set_visible(False)

    # Create a persistent 24-bit surface matching the screen format
    _frame_pg_surface = pygame.Surface((DISPLAY_SIZE, DISPLAY_SIZE), 0, 24)

    return _screen


def show_frame_from_buffer(rgb_buffer):
    """Write an RGB byte buffer directly to the screen and flip.

    This is faster than creating a Pygame Surface + blit because it writes
    directly into the persistent surface's pixel buffer via surfarray,
    eliminating per-frame Surface allocation.
    """
    if _screen is None:
        raise RuntimeError("Display not initialized. Call init_display() first.")
    # Load RGB bytes directly into the persistent surface via pixel array
    arr = np.frombuffer(rgb_buffer, dtype=np.uint8).reshape(DISPLAY_SIZE, DISPLAY_SIZE, 3)
    # surfarray expects (width, height, 3) — transpose from (H, W, 3) to (W, H, 3)
    pygame.surfarray.blit_array(_frame_pg_surface, arr.transpose(1, 0, 2))
    _screen.blit(_frame_pg_surface, (0, 0))
    pygame.display.flip()


def shutdown_display():
    """Cleanly shut down Pygame display."""
    pygame.quit()
