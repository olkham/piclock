import hashlib
import json

import cairo
import numpy as np
import pygame

from src.clock.display import DISPLAY_SIZE

# Cached static layer (background + markers + agenda + alarm indicators + mask)
_static_cache_surface = None
_static_cache_key = None


# Pre-allocated buffer for Cairo→Pygame conversion (avoids per-frame allocation)
_conv_arr = np.empty((DISPLAY_SIZE, DISPLAY_SIZE, 4), dtype=np.uint8)


def create_surface():
    """Create a Cairo ImageSurface for rendering."""
    return cairo.ImageSurface(cairo.FORMAT_ARGB32, DISPLAY_SIZE, DISPLAY_SIZE)


def cairo_surface_to_pygame(surface):
    """Convert a Cairo ImageSurface to a Pygame surface (reduced allocation)."""
    buf = surface.get_data()
    src = np.frombuffer(buf, dtype=np.uint8).reshape(DISPLAY_SIZE, DISPLAY_SIZE, 4)
    # Cairo BGRA → Pygame RGBA: swap R and B channels using pre-allocated buffer
    _conv_arr[:, :, 0] = src[:, :, 2]  # R
    _conv_arr[:, :, 1] = src[:, :, 1]  # G
    _conv_arr[:, :, 2] = src[:, :, 0]  # B
    _conv_arr[:, :, 3] = src[:, :, 3]  # A
    return pygame.image.frombuffer(_conv_arr.tobytes(), (DISPLAY_SIZE, DISPLAY_SIZE), "RGBA")


def _compute_static_key(theme, alarms, agenda_events):
    """Compute a hash key for the static layer inputs."""
    data = json.dumps({
        "theme": theme,
        "alarms": [(a.get("id"), a.get("time"), a.get("enabled")) for a in (alarms or [])],
        "agenda": [(e.get("id"), e.get("start_time"), e.get("end_time"), e.get("color")) for e in (agenda_events or [])],
    }, sort_keys=True, default=str)
    return hashlib.md5(data.encode()).hexdigest()


def _render_static_layer(theme, alarms, agenda_events):
    """Render the static clock layer (background, markers, indicators, mask)."""
    from src.clock.face import draw_background, draw_markers, draw_alarm_indicators, draw_agenda
    from src.clock.effects import apply_circular_mask

    surface = create_surface()
    ctx = cairo.Context(surface)
    size = DISPLAY_SIZE

    draw_background(ctx, size, theme)

    if agenda_events:
        draw_agenda(ctx, size, theme, agenda_events)

    draw_markers(ctx, size, theme)

    if alarms:
        draw_alarm_indicators(ctx, size, theme, alarms)

    apply_circular_mask(ctx, size)

    surface.flush()
    return surface


def invalidate_static_cache():
    """Force the static layer to be re-rendered on the next frame."""
    global _static_cache_surface, _static_cache_key
    _static_cache_surface = None
    _static_cache_key = None


def render_frame(time_info, theme, overlay_fn=None, alarms=None, agenda_events=None, hand_angles=None):
    """Render a complete clock frame.

    Uses a cached static layer for background/markers/indicators and only
    re-renders the dynamic parts (hands, text, overlays) each frame.

    Args:
        time_info: dict with keys 'hour', 'minute', 'second', 'microsecond'
        theme: dict with full theme configuration
        overlay_fn: optional callable(ctx, size) drawn on top of the clock
        alarms: optional list of alarm dicts for indicator rendering
        agenda_events: optional list of agenda event dicts for pie chart
        hand_angles: optional dict with 'hour', 'minute', 'second' angle overrides (degrees)

    Returns:
        A Pygame surface with the rendered clock.
    """
    global _static_cache_surface, _static_cache_key

    from src.clock.face import draw_clock_text, draw_current_event, draw_date_display
    from src.clock.hands import draw_hands
    from src.clock.effects import apply_circular_mask

    size = DISPLAY_SIZE

    # Get or rebuild the cached static layer
    cache_key = _compute_static_key(theme, alarms, agenda_events)
    if _static_cache_surface is None or _static_cache_key != cache_key:
        _static_cache_surface = _render_static_layer(theme, alarms, agenda_events)
        _static_cache_key = cache_key

    # Create frame surface and paint the cached static layer onto it
    surface = create_surface()
    ctx = cairo.Context(surface)
    ctx.set_source_surface(_static_cache_surface, 0, 0)
    ctx.paint()

    # Draw dynamic elements (hands, text, overlay)
    draw_hands(ctx, size, time_info, theme, hand_angles=hand_angles)

    draw_clock_text(ctx, size, time_info, theme)

    draw_date_display(ctx, size, time_info, theme)

    if agenda_events:
        draw_current_event(ctx, size, time_info, theme, agenda_events)

    if overlay_fn:
        overlay_fn(ctx, size)

    # Apply circular mask to dynamic elements
    apply_circular_mask(ctx, size)

    surface.flush()
    return cairo_surface_to_pygame(surface)
