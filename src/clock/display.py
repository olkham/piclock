import sys
import platform

import pygame


DISPLAY_SIZE = 720

_screen = None


def init_display(windowed=False):
    """Initialize Pygame display. Fullscreen by default, windowed if requested."""
    global _screen
    pygame.init()

    if windowed:
        _screen = pygame.display.set_mode((DISPLAY_SIZE, DISPLAY_SIZE))
        pygame.display.set_caption("PiClock3")
    else:
        _screen = pygame.display.set_mode(
            (DISPLAY_SIZE, DISPLAY_SIZE), pygame.FULLSCREEN | pygame.NOFRAME
        )
        pygame.mouse.set_visible(False)

    return _screen


def show_frame(surface):
    """Blit a Pygame surface to the screen and flip."""
    if _screen is None:
        raise RuntimeError("Display not initialized. Call init_display() first.")
    _screen.blit(surface, (0, 0))
    pygame.display.flip()


def shutdown_display():
    """Cleanly shut down Pygame display."""
    pygame.quit()
