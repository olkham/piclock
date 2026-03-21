import cairo
import numpy as np
import pygame

from src.clock.display import DISPLAY_SIZE


def create_surface():
    """Create a Cairo ImageSurface for rendering."""
    return cairo.ImageSurface(cairo.FORMAT_ARGB32, DISPLAY_SIZE, DISPLAY_SIZE)


def cairo_surface_to_pygame(surface):
    """Convert a Cairo ImageSurface to a Pygame surface."""
    buf = surface.get_data()
    arr = np.frombuffer(buf, dtype=np.uint8).reshape(DISPLAY_SIZE, DISPLAY_SIZE, 4).copy()
    # Cairo uses BGRA, Pygame expects RGBA on little-endian
    arr[:, :, [0, 2]] = arr[:, :, [2, 0]]
    return pygame.image.frombuffer(arr.tobytes(), (DISPLAY_SIZE, DISPLAY_SIZE), "RGBA")


def render_frame(time_info, theme, overlay_fn=None, alarms=None):
    """Render a complete clock frame.

    Args:
        time_info: dict with keys 'hour', 'minute', 'second', 'microsecond'
        theme: dict with full theme configuration
        overlay_fn: optional callable(ctx, size) drawn on top of the clock
        alarms: optional list of alarm dicts for indicator rendering

    Returns:
        A Pygame surface with the rendered clock.
    """
    from src.clock.face import draw_background, draw_markers, draw_alarm_indicators
    from src.clock.hands import draw_hands
    from src.clock.effects import apply_circular_mask

    surface = create_surface()
    ctx = cairo.Context(surface)
    size = DISPLAY_SIZE

    # Draw background
    draw_background(ctx, size, theme)

    # Draw markers
    draw_markers(ctx, size, theme)

    # Draw alarm indicators
    if alarms:
        draw_alarm_indicators(ctx, size, theme, alarms)

    # Draw hands
    draw_hands(ctx, size, time_info, theme)

    # Draw overlay (e.g., alarm visual)
    if overlay_fn:
        overlay_fn(ctx, size)

    # Apply circular mask for round display
    apply_circular_mask(ctx, size)

    surface.flush()
    return cairo_surface_to_pygame(surface)
