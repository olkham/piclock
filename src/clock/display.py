import os
import sys
import platform

import pygame

# Prevent SDL2 from bypassing the display compositor in fullscreen mode.
# Without this, fullscreen Pygame windows bypass the compositor's vsync,
# causing visible tearing (top ~5% of screen 1 frame behind the rest).
os.environ.setdefault('SDL_VIDEO_X11_NET_WM_BYPASS_COMPOSITOR', '0')


DISPLAY_SIZE = 720

_screen = None


def init_display(windowed=False):
    """Initialize Pygame display with double-buffering. Fullscreen by default."""
    global _screen
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

    return _screen


def show_frame(surface):
    """Blit a Pygame surface to the back buffer and flip."""
    if _screen is None:
        raise RuntimeError("Display not initialized. Call init_display() first.")
    _screen.blit(surface, (0, 0))
    pygame.display.flip()


def shutdown_display():
    """Cleanly shut down Pygame display."""
    pygame.quit()
