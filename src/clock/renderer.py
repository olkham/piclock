import math

import cairo
import numpy as np

from src.clock.display import DISPLAY_SIZE

# --- Cached static layer (background + markers + agenda + indicators + mask) ---
_static_cache_surface = None
_static_cache_dirty = True

# Pre-rendered circular mask: black corners, transparent circle (computed once)
_mask_surface = None

# Persistent Cairo frame surface backed by our own buffer (zero alloc per frame)
_frame_data = bytearray(DISPLAY_SIZE * DISPLAY_SIZE * 4)
_frame_surface = cairo.ImageSurface.create_for_data(
    _frame_data, cairo.FORMAT_ARGB32, DISPLAY_SIZE, DISPLAY_SIZE, DISPLAY_SIZE * 4
)
# Pre-allocated numpy view of the Cairo buffer — avoids per-frame frombuffer/reshape
_src_arr = np.frombuffer(_frame_data, dtype=np.uint8).reshape(
    DISPLAY_SIZE, DISPLAY_SIZE, 4
)

# Shared output buffer: numpy view writes directly into the bytearray that
# Pygame reads from — no intermediate copies or per-frame allocations.
_conv_buf = bytearray(DISPLAY_SIZE * DISPLAY_SIZE * 3)
_conv_arr = np.frombuffer(_conv_buf, dtype=np.uint8).reshape(
    DISPLAY_SIZE, DISPLAY_SIZE, 3
)

# Change detection via object identity (replaces per-frame MD5 hashing).
# IMPORTANT: This assumes theme/alarms/agenda_events objects are always
# *replaced* (not mutated in-place) when their content changes.
_last_theme_id = None
_last_alarms_id = None
_last_agenda_id = None


def _create_mask_surface():
    """Pre-render circular mask (black outside circle, transparent inside)."""
    size = DISPLAY_SIZE
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    ctx = cairo.Context(surface)
    center = size / 2
    ctx.set_source_rgb(0, 0, 0)
    ctx.rectangle(0, 0, size, size)
    ctx.arc(center, center, size / 2, 0, 2 * math.pi)
    ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    ctx.fill()
    ctx.set_fill_rule(cairo.FILL_RULE_WINDING)
    surface.flush()
    return surface


def _render_static_layer(theme, alarms, agenda_events):
    """Render the static clock layer (background, markers, indicators, mask)."""
    from src.clock.face import draw_background, draw_markers, draw_alarm_indicators, draw_agenda

    global _mask_surface
    if _mask_surface is None:
        _mask_surface = _create_mask_surface()

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, DISPLAY_SIZE, DISPLAY_SIZE)
    ctx = cairo.Context(surface)
    size = DISPLAY_SIZE

    draw_background(ctx, size, theme)

    if agenda_events:
        draw_agenda(ctx, size, theme, agenda_events)

    draw_markers(ctx, size, theme)

    if alarms:
        draw_alarm_indicators(ctx, size, theme, alarms)

    # Bake mask into static layer so it doesn't need per-frame EVEN_ODD fill
    ctx.set_source_surface(_mask_surface, 0, 0)
    ctx.paint()

    surface.flush()
    return surface


def invalidate_static_cache():
    """Force the static layer to be re-rendered on the next frame."""
    global _static_cache_dirty
    _static_cache_dirty = True


def render_frame(time_info, theme, overlay_fn=None, alarms=None, agenda_events=None, hand_angles=None):
    """Render a complete clock frame.

    Performance optimizations vs. naive approach:
    - Persistent Cairo surface (no 2 MB alloc per frame)
    - Pre-cached circular mask (no per-frame EVEN_ODD fill)
    - Object-identity change detection (no per-frame JSON + MD5)
    - Shared bytearray output buffer (no per-frame tobytes allocation)
    - RGB output (25 % less data than RGBA — alpha unnecessary after masking)
    """
    global _static_cache_surface, _static_cache_dirty, _mask_surface
    global _last_theme_id, _last_alarms_id, _last_agenda_id

    from src.clock.face import draw_clock_text, draw_current_event, draw_date_display
    from src.clock.hands import draw_hands

    size = DISPLAY_SIZE

    # Lightweight change detection via object identity
    t_id, a_id, ag_id = id(theme), id(alarms), id(agenda_events)
    if t_id != _last_theme_id or a_id != _last_alarms_id or ag_id != _last_agenda_id:
        _static_cache_dirty = True
        _last_theme_id = t_id
        _last_alarms_id = a_id
        _last_agenda_id = ag_id

    # Rebuild static layer only when inputs change
    if _static_cache_dirty or _static_cache_surface is None:
        _static_cache_surface = _render_static_layer(theme, alarms, agenda_events)
        _static_cache_dirty = False

    # Reuse persistent frame surface — SOURCE replaces all pixels (no clear needed)
    ctx = cairo.Context(_frame_surface)
    ctx.set_operator(cairo.OPERATOR_SOURCE)
    ctx.set_source_surface(_static_cache_surface, 0, 0)
    ctx.paint()
    ctx.set_operator(cairo.OPERATOR_OVER)

    # Dynamic elements only
    draw_hands(ctx, size, time_info, theme, hand_angles=hand_angles)
    draw_clock_text(ctx, size, time_info, theme)
    draw_date_display(ctx, size, time_info, theme)

    if agenda_events:
        draw_current_event(ctx, size, time_info, theme, agenda_events)

    if overlay_fn:
        overlay_fn(ctx, size)

    # No per-frame mask needed: the static cache already has the circular
    # mask baked in (black corners), and all dynamic elements (hands, text)
    # are drawn inside the circle by geometry — they can't reach corners.

    _frame_surface.flush()

    # Convert Cairo BGRA → Pygame RGB via shared buffer (zero allocation).
    # Three direct channel assignments avoid the temporary array that
    # slice reversal [:, :, 2::-1] creates on ARM — ~10% faster.
    _conv_arr[:, :, 0] = _src_arr[:, :, 2]
    _conv_arr[:, :, 1] = _src_arr[:, :, 1]
    _conv_arr[:, :, 2] = _src_arr[:, :, 0]
    # _conv_arr writes directly into _conv_buf — no copy needed
    return _conv_buf
