"""Dial mode renderer — circular progress gauge for the PiClock display.

Renders a configurable arc-based progress dial with optional text,
tick marks, and smooth animation. Controlled via REST API; visual
defaults come from the active theme's ``dial`` section.
"""

import math
import sys
import time

import cairo
import numpy as np

from src.clock.display import DISPLAY_SIZE

_SANS_FONT = "Arial" if sys.platform == "win32" else "sans-serif"

# --- Persistent surfaces (same pattern as renderer.py) ---
_frame_data = bytearray(DISPLAY_SIZE * DISPLAY_SIZE * 4)
_frame_surface = cairo.ImageSurface.create_for_data(
    _frame_data, cairo.FORMAT_ARGB32, DISPLAY_SIZE, DISPLAY_SIZE, DISPLAY_SIZE * 4
)
_src_arr = np.frombuffer(_frame_data, dtype=np.uint8).reshape(
    DISPLAY_SIZE, DISPLAY_SIZE, 4
)
_conv_buf = bytearray(DISPLAY_SIZE * DISPLAY_SIZE * 3)
_conv_arr = np.frombuffer(_conv_buf, dtype=np.uint8).reshape(
    DISPLAY_SIZE, DISPLAY_SIZE, 3
)

_mask_surface = None


def _hex_to_rgb(hex_color):
    """Convert hex color string to (r, g, b) floats 0-1."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _create_mask_surface():
    """Pre-render circular mask (black corners, transparent circle)."""
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


def _deg_to_rad(deg):
    """Convert degrees (0=top, clockwise) to Cairo radians (0=right, counter-clockwise)."""
    # Cairo: 0 rad = 3 o'clock, positive = clockwise
    # Our convention: 0° = 12 o'clock, positive = clockwise
    return math.radians(deg - 90)


def _get_cap(style):
    """Map cap style name to Cairo line cap constant."""
    caps = {
        "butt": cairo.LINE_CAP_BUTT,
        "round": cairo.LINE_CAP_ROUND,
        "square": cairo.LINE_CAP_SQUARE,
    }
    return caps.get(style, cairo.LINE_CAP_ROUND)


def _ease_out(t):
    """Cubic ease-out: fast start, gentle settle."""
    return 1 - (1 - t) ** 3


def _ease_in_out(t):
    """Cubic ease-in-out."""
    if t < 0.5:
        return 4 * t * t * t
    return 1 - ((-2 * t + 2) ** 3) / 2


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def render_dial_frame(dial_theme, dial_state, display_progress):
    """Render a single dial frame.

    Args:
        dial_theme: Active dial theme dict (background + dial section).
        dial_state: Current dial state dict (progress, text, label, overrides).
        display_progress: The interpolated progress value (0-100) to render,
                         already accounting for animation.

    Returns:
        bytearray: RGB pixel buffer for display.
    """
    global _mask_surface
    if _mask_surface is None:
        _mask_surface = _create_mask_surface()

    from src.clock.face import draw_background

    size = DISPLAY_SIZE
    center = size / 2
    dial_cfg = dial_theme.get("dial", {})

    ctx = cairo.Context(_frame_surface)

    # --- Background (from dial theme's own background section) ---
    ctx.set_operator(cairo.OPERATOR_SOURCE)
    draw_background(ctx, size, dial_theme)
    ctx.set_operator(cairo.OPERATOR_OVER)

    # --- Arc geometry ---
    arc_start = dial_cfg.get("arc_start", 135)
    arc_end = dial_cfg.get("arc_end", 405)
    radius_pct = dial_cfg.get("radius", 85)
    thickness_pct = dial_cfg.get("thickness", 14)
    radius = radius_pct / 100 * (size / 2)
    thickness = thickness_pct / 100 * radius

    start_rad = _deg_to_rad(arc_start)
    end_rad = _deg_to_rad(arc_end)
    arc_sweep = end_rad - start_rad

    cap = _get_cap(dial_cfg.get("cap_style", "round"))

    # --- Track (unfilled background arc) ---
    track_style = dial_cfg.get("track_style", "solid")
    track_opacity = dial_cfg.get("track_opacity", 12) / 100

    ctx.set_line_width(thickness)
    ctx.set_line_cap(cap)

    if track_style == "zones":
        _draw_track_zones(ctx, center, radius, thickness, cap, dial_cfg, start_rad, arc_sweep, track_opacity)
    elif track_style == "gradient":
        _draw_track_gradient(ctx, center, radius, thickness, cap, dial_cfg, start_rad, end_rad, track_opacity)
    else:
        track_color = dial_cfg.get("track_color", "#ffffff")
        tr, tg, tb = _hex_to_rgb(track_color)
        ctx.set_source_rgba(tr, tg, tb, track_opacity)
        ctx.arc(center, center, radius, start_rad, end_rad)
        ctx.stroke()

    # --- Progress arc ---
    if dial_cfg.get("show_progress", True):
        _draw_progress_arc(ctx, center, radius, thickness, cap, dial_cfg, dial_state,
                           start_rad, arc_sweep, display_progress)

    # --- Tick marks ---
    if dial_cfg.get("tick_marks", False):
        _draw_ticks(ctx, center, size, dial_cfg, start_rad, arc_sweep)

    # --- Hand (shaft / triangle / needle) ---
    norm_progress = max(0.0, min(1.0, display_progress / 100.0))
    hand_angle = start_rad + arc_sweep * norm_progress
    if dial_cfg.get("show_hand", False):
        _draw_hand(ctx, center, size, dial_cfg, hand_angle)

    # --- Text ---
    if dial_cfg.get("show_text", True):
        _draw_dial_text(ctx, center, size, radius, dial_cfg, dial_state)

    # --- Value text ---
    if dial_cfg.get("show_value", False):
        _draw_value_text(ctx, center, size, radius, dial_cfg, dial_state, display_progress)

    # --- Min / Max labels ---
    if dial_cfg.get("show_min_max", False):
        _draw_min_max(ctx, center, size, radius, dial_cfg, dial_state, start_rad, end_rad)

    # --- Hand center dot (drawn last before mask for visual hierarchy) ---
    if dial_cfg.get("show_hand", False) and dial_cfg.get("hand_center_dot", True):
        _draw_hand_center_dot(ctx, center, size, dial_cfg)

    # --- Circular mask ---
    ctx.set_source_surface(_mask_surface, 0, 0)
    ctx.paint()

    _frame_surface.flush()

    # BGRA → RGB conversion (same optimized path as renderer.py)
    _conv_arr[:, :, 0] = _src_arr[:, :, 2]
    _conv_arr[:, :, 1] = _src_arr[:, :, 1]
    _conv_arr[:, :, 2] = _src_arr[:, :, 0]
    return _conv_buf


# ---------------------------------------------------------------------------
# Sub-drawing functions
# ---------------------------------------------------------------------------

def _draw_progress_arc(ctx, center, radius, thickness, cap, dial_cfg, dial_state,
                       start_rad, arc_sweep, display_progress):
    """Draw the filled progress arc."""
    norm_progress = max(0.0, min(1.0, display_progress / 100.0))
    if norm_progress <= 0.001:
        return

    progress_end = start_rad + arc_sweep * norm_progress
    progress_opacity = dial_cfg.get("progress_opacity", 100) / 100
    style = dial_cfg.get("style", "solid")

    progress_color = dial_state.get("progress_color") or dial_cfg.get("progress_color", "#00D68F")
    pr, pg, pb = _hex_to_rgb(progress_color)

    ctx.set_line_width(thickness)
    ctx.set_line_cap(cap)

    if style == "dashed":
        dash_len = dial_cfg.get("dash_length", 8)
        dash_gap = dial_cfg.get("dash_gap", 4)
        ctx.set_dash([dash_len, dash_gap])

    if style == "gradient":
        grad_end_color = dial_cfg.get("gradient_end_color", "#ff4444")
        er, eg, eb = _hex_to_rgb(grad_end_color)
        sx = center + radius * math.cos(start_rad)
        sy = center + radius * math.sin(start_rad)
        ex = center + radius * math.cos(progress_end)
        ey = center + radius * math.sin(progress_end)
        gradient = cairo.LinearGradient(sx, sy, ex, ey)
        gradient.add_color_stop_rgba(0, pr, pg, pb, progress_opacity)
        gradient.add_color_stop_rgba(1, er, eg, eb, progress_opacity)
        ctx.set_source(gradient)
    else:
        ctx.set_source_rgba(pr, pg, pb, progress_opacity)

    ctx.arc(center, center, radius, start_rad, progress_end)
    ctx.stroke()

    if style == "dashed":
        ctx.set_dash([])


def _draw_track_zones(ctx, center, radius, thickness, cap, dial_cfg, start_rad, arc_sweep, opacity):
    """Draw the track as coloured zone segments."""
    zones = dial_cfg.get("track_zones", [])
    if not zones:
        return
    for zone in zones:
        z_from = zone.get("from", 0) / 100.0
        z_to = zone.get("to", 100) / 100.0
        z_color = zone.get("color", "#ffffff")
        zr, zg, zb = _hex_to_rgb(z_color)
        seg_start = start_rad + arc_sweep * z_from
        seg_end = start_rad + arc_sweep * z_to
        ctx.set_line_width(thickness)
        ctx.set_line_cap(cap)
        ctx.set_source_rgba(zr, zg, zb, opacity)
        ctx.arc(center, center, radius, seg_start, seg_end)
        ctx.stroke()


def _draw_track_gradient(ctx, center, radius, thickness, cap, dial_cfg, start_rad, end_rad, opacity):
    """Draw the track with a smooth colour gradient."""
    start_color = dial_cfg.get("track_gradient_start", "#22c55e")
    end_color = dial_cfg.get("track_gradient_end", "#ef4444")
    sr, sg, sb = _hex_to_rgb(start_color)
    er, eg, eb = _hex_to_rgb(end_color)

    sx = center + radius * math.cos(start_rad)
    sy = center + radius * math.sin(start_rad)
    ex = center + radius * math.cos(end_rad)
    ey = center + radius * math.sin(end_rad)

    gradient = cairo.LinearGradient(sx, sy, ex, ey)
    gradient.add_color_stop_rgba(0, sr, sg, sb, opacity)
    gradient.add_color_stop_rgba(1, er, eg, eb, opacity)

    ctx.set_line_width(thickness)
    ctx.set_line_cap(cap)
    ctx.set_source(gradient)
    ctx.arc(center, center, radius, start_rad, end_rad)
    ctx.stroke()


def _draw_ticks(ctx, center, size, dial_cfg, start_rad, arc_sweep):
    """Draw major and optional minor tick marks using radius-based positioning."""
    half = size / 2
    major_count = dial_cfg.get("major_tick_count", 10)
    if major_count < 2:
        return

    # --- Major ticks ---
    maj_inner = dial_cfg.get("major_tick_inner_radius", 72) / 100 * half
    maj_outer = dial_cfg.get("major_tick_outer_radius", 78) / 100 * half
    maj_width = dial_cfg.get("major_tick_width", 2)
    maj_color = dial_cfg.get("major_tick_color", "#888888")
    mr, mg, mb = _hex_to_rgb(maj_color)

    ctx.set_line_cap(cairo.LINE_CAP_BUTT)

    # Draw minor ticks first (behind majors)
    if dial_cfg.get("minor_ticks", False):
        minor_per = dial_cfg.get("minor_tick_count", 4)
        if minor_per > 0:
            min_inner = dial_cfg.get("minor_tick_inner_radius", 73) / 100 * half
            min_outer = dial_cfg.get("minor_tick_outer_radius", 77) / 100 * half
            min_width = dial_cfg.get("minor_tick_width", 1)
            min_color = dial_cfg.get("minor_tick_color", "#555555")
            mnr, mng, mnb = _hex_to_rgb(min_color)

            ctx.set_source_rgb(mnr, mng, mnb)
            ctx.set_line_width(min_width)

            for i in range(major_count):
                for j in range(1, minor_per + 1):
                    frac = (i + j / (minor_per + 1)) / major_count
                    angle = start_rad + arc_sweep * frac
                    cos_a = math.cos(angle)
                    sin_a = math.sin(angle)
                    ctx.move_to(center + min_inner * cos_a, center + min_inner * sin_a)
                    ctx.line_to(center + min_outer * cos_a, center + min_outer * sin_a)
                    ctx.stroke()

    # Draw major ticks on top
    ctx.set_source_rgb(mr, mg, mb)
    ctx.set_line_width(maj_width)

    for i in range(major_count + 1):
        angle = start_rad + arc_sweep * i / major_count
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        ctx.move_to(center + maj_inner * cos_a, center + maj_inner * sin_a)
        ctx.line_to(center + maj_outer * cos_a, center + maj_outer * sin_a)
        ctx.stroke()


def _draw_hand(ctx, center, size, dial_cfg, angle):
    """Draw the dial hand (pointer) at the given angle."""
    half = size / 2
    tip_r = dial_cfg.get("hand_length", 80) / 100 * half
    tail_r = dial_cfg.get("hand_tail", 10) / 100 * half
    width_pct = dial_cfg.get("hand_width", 3)
    radius_for_width = dial_cfg.get("radius", 85) / 100 * half
    base_w = width_pct / 100 * radius_for_width
    style = dial_cfg.get("hand_style", "triangle")
    color = dial_cfg.get("hand_color", "#ffffff")
    hr, hg, hb = _hex_to_rgb(color)

    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    # Perpendicular for width
    cos_p = math.cos(angle + math.pi / 2)
    sin_p = math.sin(angle + math.pi / 2)

    tip_x = center + tip_r * cos_a
    tip_y = center + tip_r * sin_a
    tail_x = center - tail_r * cos_a
    tail_y = center - tail_r * sin_a

    ctx.set_source_rgb(hr, hg, hb)

    if style == "line":
        ctx.set_line_width(max(base_w, 2))
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.move_to(tail_x, tail_y)
        ctx.line_to(tip_x, tip_y)
        ctx.stroke()
    elif style == "needle":
        # Thin shaft with small diamond tip
        shaft_w = max(base_w * 0.3, 1)
        diamond_w = max(base_w * 1.2, 3)
        diamond_len = tip_r * 0.06

        # Shaft
        ctx.set_line_width(shaft_w)
        ctx.set_line_cap(cairo.LINE_CAP_BUTT)
        ctx.move_to(tail_x, tail_y)
        diamond_base_x = center + (tip_r - diamond_len) * cos_a
        diamond_base_y = center + (tip_r - diamond_len) * sin_a
        ctx.line_to(diamond_base_x, diamond_base_y)
        ctx.stroke()

        # Diamond tip
        ctx.move_to(tip_x, tip_y)
        ctx.line_to(diamond_base_x + diamond_w * cos_p, diamond_base_y + diamond_w * sin_p)
        ctx.line_to(center + (tip_r - diamond_len * 2) * cos_a,
                    center + (tip_r - diamond_len * 2) * sin_a)
        ctx.line_to(diamond_base_x - diamond_w * cos_p, diamond_base_y - diamond_w * sin_p)
        ctx.close_path()
        ctx.fill()
    else:
        # Triangle (default): tapered from base to sharp tip
        ctx.move_to(tip_x, tip_y)
        ctx.line_to(tail_x + base_w * cos_p, tail_y + base_w * sin_p)
        ctx.line_to(tail_x - base_w * cos_p, tail_y - base_w * sin_p)
        ctx.close_path()
        ctx.fill()


def _draw_hand_center_dot(ctx, center, size, dial_cfg):
    """Draw the center dot for the hand pivot."""
    half = size / 2
    dot_r = dial_cfg.get("hand_center_dot_radius", 4) / 100 * half
    dot_color = dial_cfg.get("hand_center_dot_color", "#333333")
    dr, dg, db = _hex_to_rgb(dot_color)

    ctx.arc(center, center, dot_r, 0, 2 * math.pi)
    ctx.set_source_rgb(dr, dg, db)
    ctx.fill()

    # Subtle border ring
    ctx.arc(center, center, dot_r, 0, 2 * math.pi)
    ctx.set_source_rgba(1, 1, 1, 0.15)
    ctx.set_line_width(1)
    ctx.stroke()


def _draw_value_text(ctx, center, size, radius, dial_cfg, dial_state, display_progress):
    """Draw the current numeric value with optional suffix."""
    # Use the raw progress value from dial state (not the 0-100 display_progress)
    raw_value = dial_state.get("progress", 0)
    suffix = dial_cfg.get("value_suffix", "")
    value_str = f"{raw_value}{suffix}"

    font_size = dial_cfg.get("value_font_size", 0)
    if font_size <= 0:
        font_size = size * 0.07

    offset_y = dial_cfg.get("value_offset_y", 12) / 100 * radius
    color = dial_cfg.get("value_color", "#ffffff")
    vr, vg, vb = _hex_to_rgb(color)

    ctx.select_font_face(_SANS_FONT, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(font_size)
    extents = ctx.text_extents(value_str)

    vx = center - extents.width / 2 - extents.x_bearing
    vy = center + offset_y + extents.height / 2

    ctx.set_source_rgba(0, 0, 0, 0.25)
    ctx.move_to(vx + 1, vy + 1)
    ctx.show_text(value_str)

    ctx.set_source_rgb(vr, vg, vb)
    ctx.move_to(vx, vy)
    ctx.show_text(value_str)


def _draw_min_max(ctx, center, size, radius, dial_cfg, dial_state, start_rad, end_rad):
    """Draw min/max value labels near the arc endpoints."""
    min_val = dial_state.get("min_value", 0)
    max_val = dial_state.get("max_value", 100)
    color = dial_cfg.get("min_max_color", "#666666")
    mr, mg, mb = _hex_to_rgb(color)

    font_size = dial_cfg.get("min_max_font_size", 0)
    if font_size <= 0:
        font_size = size * 0.03

    # Position labels just inside the arc
    half = size / 2
    label_r = dial_cfg.get("radius", 85) / 100 * half * 0.82

    ctx.select_font_face(_SANS_FONT, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(font_size)
    ctx.set_source_rgb(mr, mg, mb)

    for val, angle in [(min_val, start_rad), (max_val, end_rad)]:
        text = str(val)
        extents = ctx.text_extents(text)
        lx = center + label_r * math.cos(angle) - extents.width / 2 - extents.x_bearing
        ly = center + label_r * math.sin(angle) + extents.height / 2
        ctx.move_to(lx, ly)
        ctx.show_text(text)


def _draw_dial_text(ctx, center, size, radius, dial_cfg, dial_state):
    """Draw primary text and label in the center of the dial."""
    text = dial_state.get("text", "")
    label = dial_state.get("label", "")

    if not text and not label:
        return

    # Resolve colors (API override or theme default)
    text_color = dial_state.get("text_color") or dial_cfg.get("text_color", "#ffffff")
    label_color = dial_cfg.get("label_color", "#888888")

    text_offset_y = dial_cfg.get("text_offset_y", -2) / 100 * radius
    label_offset_y = dial_cfg.get("label_offset_y", 8) / 100 * radius

    # Primary text
    if text:
        text_font_size = dial_cfg.get("text_font_size", 0)
        if text_font_size <= 0:
            text_font_size = size * 0.11  # 11% of display = ~80px

        tr, tg, tb = _hex_to_rgb(text_color)
        ctx.select_font_face(_SANS_FONT, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        ctx.set_font_size(text_font_size)
        extents = ctx.text_extents(text)

        tx = center - extents.width / 2 - extents.x_bearing
        ty = center + text_offset_y + extents.height / 2

        # Shadow
        ctx.set_source_rgba(0, 0, 0, 0.3)
        ctx.move_to(tx + 2, ty + 2)
        ctx.show_text(text)

        # Text
        ctx.set_source_rgb(tr, tg, tb)
        ctx.move_to(tx, ty)
        ctx.show_text(text)

    # Label (smaller, below primary)
    if label:
        label_font_size = dial_cfg.get("label_font_size", 0)
        if label_font_size <= 0:
            label_font_size = size * 0.045  # 4.5% of display = ~32px

        lr, lg, lb = _hex_to_rgb(label_color)
        ctx.select_font_face(_SANS_FONT, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        ctx.set_font_size(label_font_size)
        extents = ctx.text_extents(label)

        lx = center - extents.width / 2 - extents.x_bearing
        ly = center + label_offset_y + extents.height / 2

        # Shadow
        ctx.set_source_rgba(0, 0, 0, 0.2)
        ctx.move_to(lx + 1, ly + 1)
        ctx.show_text(label)

        # Label
        ctx.set_source_rgb(lr, lg, lb)
        ctx.move_to(lx, ly)
        ctx.show_text(label)
