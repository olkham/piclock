"""Element-based face renderer using Cairo.

Renders faces defined as ordered element lists. Maintains the same
two-layer caching strategy (static + dynamic) and zero-allocation
buffer management as the original renderer.

Static elements (background, ticks, track arcs, labels, mask) are
cached and only redrawn when the face or bound data changes.
Dynamic elements (hands, progress arcs, bound text) are drawn every frame.
"""

import math
import os
import sys

import cairo
import numpy as np

from src.clock.color import hex_to_rgb
from src.clock.display import DISPLAY_SIZE
from src.clock.effects import draw_shadow, draw_glow

_SANS_FONT = "Arial" if sys.platform == "win32" else "sans-serif"
_SERIF_FONT = "Times New Roman" if sys.platform == "win32" else "serif"

# --- Dynamic element types (redrawn every frame) ---
_DYNAMIC_TYPES = {"hand"}
# Elements with bindings are always dynamic
_DYNAMIC_BINDINGS = {"angle", "progress", "text"}

# --- Persistent Cairo surfaces and buffers (same pattern as renderer.py) ---
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

# --- Mask + static cache ---
_mask_surface = None
_static_cache_surface = None
_static_cache_dirty = True
_last_face_id = None
_last_data_context_id = None


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


def _is_dynamic(element):
    """Check if an element must be drawn every frame."""
    if element.get("type") in _DYNAMIC_TYPES:
        return True
    bindings = element.get("bindings", {})
    return bool(bindings.keys() & _DYNAMIC_BINDINGS)


def invalidate_face_cache():
    """Force the static layer to be re-rendered on the next frame."""
    global _static_cache_dirty
    _static_cache_dirty = True


def _deg_to_rad(deg):
    """Convert degrees (0=top, clockwise) to Cairo radians."""
    return math.radians(deg - 90)


def _get_cap(style):
    """Map cap style name to Cairo line cap constant."""
    caps = {
        "butt": cairo.LINE_CAP_BUTT,
        "round": cairo.LINE_CAP_ROUND,
        "square": cairo.LINE_CAP_SQUARE,
    }
    return caps.get(style, cairo.LINE_CAP_ROUND)


def _compute_arc_geo(props):
    """Compute arc geometry from element properties."""
    size = DISPLAY_SIZE
    if props.get("arc_symmetric", False):
        center_deg = props.get("arc_center", 0)
        extent = props.get("arc_extent", 135)
        arc_start = center_deg - extent
        arc_end = center_deg + extent
    else:
        arc_start = props.get("arc_start", 135)
        arc_end = props.get("arc_end", 405)
    radius_pct = props.get("radius", 85)
    thickness_pct = props.get("thickness", 14)
    center = size / 2
    radius = radius_pct / 100 * center
    thickness = thickness_pct / 100 * radius
    start_rad = _deg_to_rad(arc_start)
    end_rad = _deg_to_rad(arc_end)
    arc_sweep = end_rad - start_rad
    cap = _get_cap(props.get("cap_style", "round"))
    return center, radius, thickness, start_rad, end_rad, arc_sweep, cap


# =========================================================================
# Per-element draw functions
# =========================================================================

# --- Background image cache ---
_bg_image_cache = {}


def _get_cached_bg_image(path):
    cached = _bg_image_cache.get(path)
    if cached is not None:
        return cached
    surface = cairo.ImageSurface.create_from_png(path)
    _bg_image_cache.clear()
    _bg_image_cache[path] = surface
    return surface


def _draw_background(ctx, size, props):
    """Draw a full-face background."""
    bg_type = props.get("style", "solid")
    center = size / 2
    radius = size / 2
    color_opacity = props.get("color_opacity", 100) / 100
    image_opacity = props.get("image_opacity", 100) / 100

    if bg_type == "gradient":
        grad_type = props.get("gradient_type", "radial")
        colors = props.get("colors", ["#1a1a2e", "#16213e"])
        color_stops = props.get("color_stops", [])

        if grad_type == "linear":
            angle_deg = props.get("gradient_angle", 0)
            angle = math.radians(angle_deg - 90)
            dx = math.cos(angle) * radius
            dy = math.sin(angle) * radius
            pattern = cairo.LinearGradient(
                center - dx, center - dy, center + dx, center + dy)
        else:
            cx = props.get("gradient_center_x", 0.5) * size
            cy = props.get("gradient_center_y", 0.5) * size
            gr = props.get("gradient_radius", 1.0) * radius
            pattern = cairo.RadialGradient(cx, cy, 0, cx, cy, gr)

        if color_stops:
            for stop in color_stops:
                r, g, b = hex_to_rgb(stop.get("color", "#000000"))
                pattern.add_color_stop_rgba(stop.get("position", 0), r, g, b, color_opacity)
        else:
            for i, color_hex in enumerate(colors):
                r, g, b = hex_to_rgb(color_hex)
                pattern.add_color_stop_rgba(i / max(len(colors) - 1, 1), r, g, b, color_opacity)

        ctx.set_source(pattern)
    elif bg_type == "image":
        color = props.get("color", "#1a1a2e")
        r, g, b = hex_to_rgb(color)
        ctx.set_source_rgb(r, g, b)
        ctx.rectangle(0, 0, size, size)
        ctx.fill()
        image_path = props.get("image", "")
        if image_path and os.path.isfile(image_path):
            try:
                img = _get_cached_bg_image(image_path)
                img_w, img_h = img.get_width(), img.get_height()
                scale = max(size / img_w, size / img_h)
                ctx.save()
                ctx.scale(scale, scale)
                ctx.set_source_surface(img, 0, 0)
                ctx.paint_with_alpha(image_opacity)
                ctx.restore()
            except Exception:
                pass
        return
    else:
        color = props.get("color", "#1a1a2e")
        r, g, b = hex_to_rgb(color)
        ctx.set_source_rgba(r, g, b, color_opacity)

    ctx.rectangle(0, 0, size, size)
    ctx.fill()


def _draw_circle(ctx, size, props, position):
    """Draw a circle or ring at a position."""
    center = size / 2
    radius = size / 2
    pos_x = center + (position[0] if position else 0) / 100 * radius
    pos_y = center + (position[1] if position else 0) / 100 * radius
    circle_r = props.get("radius", 6)
    color = props.get("color", "#ffffff")
    r, g, b = hex_to_rgb(color)
    opacity = props.get("opacity", 100) / 100
    filled = props.get("filled", True)

    if filled:
        ctx.set_source_rgba(r, g, b, opacity)
        ctx.arc(pos_x, pos_y, circle_r, 0, 2 * math.pi)
        ctx.fill()
    else:
        ctx.set_source_rgba(r, g, b, opacity)
        ctx.set_line_width(props.get("stroke_width", 2))
        ctx.arc(pos_x, pos_y, circle_r, 0, 2 * math.pi)
        ctx.stroke()


def _draw_arc_static(ctx, size, props):
    """Draw a static arc (track arc without progress binding)."""
    center, radius, thickness, start_rad, end_rad, arc_sweep, cap = _compute_arc_geo(props)
    opacity = props.get("opacity", 100) / 100
    track_style = props.get("track_style", "solid")

    ctx.set_line_width(thickness)
    ctx.set_line_cap(cap)

    if track_style == "zones":
        zones = props.get("track_zones", [])
        for zone in zones:
            z_from = zone.get("from", 0) / 100.0
            z_to = zone.get("to", 100) / 100.0
            z_color = zone.get("color", "#ffffff")
            zr, zg, zb = hex_to_rgb(z_color)
            seg_start = start_rad + arc_sweep * z_from
            seg_end = start_rad + arc_sweep * z_to
            ctx.set_source_rgba(zr, zg, zb, opacity)
            ctx.arc(center, center, radius, seg_start, seg_end)
            ctx.stroke()
    elif track_style == "gradient":
        start_color = props.get("track_gradient_start", "#22c55e")
        end_color = props.get("track_gradient_end", "#ef4444")
        sr, sg, sb = hex_to_rgb(start_color)
        er, eg, eb = hex_to_rgb(end_color)
        sx = center + radius * math.cos(start_rad)
        sy = center + radius * math.sin(start_rad)
        ex = center + radius * math.cos(end_rad)
        ey = center + radius * math.sin(end_rad)
        gradient = cairo.LinearGradient(sx, sy, ex, ey)
        gradient.add_color_stop_rgba(0, sr, sg, sb, opacity)
        gradient.add_color_stop_rgba(1, er, eg, eb, opacity)
        ctx.set_source(gradient)
        ctx.arc(center, center, radius, start_rad, end_rad)
        ctx.stroke()
    else:
        color = props.get("color", "#ffffff")
        cr, cg, cb = hex_to_rgb(color)
        ctx.set_source_rgba(cr, cg, cb, opacity)
        ctx.arc(center, center, radius, start_rad, end_rad)
        ctx.stroke()


def _draw_arc_progress(ctx, size, props, progress, data_ctx=None):
    """Draw a progress arc (dynamic, bound to a progress data source)."""
    center, radius, thickness, start_rad, end_rad, arc_sweep, cap = _compute_arc_geo(props)

    norm_progress = max(0.0, min(1.0, float(progress) / 100.0))
    if norm_progress <= 0.001:
        return

    progress_end = start_rad + arc_sweep * norm_progress
    opacity = props.get("opacity", 100) / 100
    style = props.get("style", "solid")

    # Allow dynamic progress color override from data context
    color = props.get("color", "#00D68F")
    if data_ctx:
        override = data_ctx.resolve("dial.progress_color")
        if override:
            color = override
    pr, pg, pb = hex_to_rgb(color)

    ctx.set_line_width(thickness)
    ctx.set_line_cap(cap)

    if style == "dashed":
        dash_len = props.get("dash_length", 8)
        dash_gap = props.get("dash_gap", 4)
        ctx.set_dash([dash_len, dash_gap])

    if style == "gradient":
        grad_end = props.get("gradient_end_color", "#ff4444")
        er, eg, eb = hex_to_rgb(grad_end)
        sx = center + radius * math.cos(start_rad)
        sy = center + radius * math.sin(start_rad)
        ex = center + radius * math.cos(progress_end)
        ey = center + radius * math.sin(progress_end)
        gradient = cairo.LinearGradient(sx, sy, ex, ey)
        gradient.add_color_stop_rgba(0, pr, pg, pb, opacity)
        gradient.add_color_stop_rgba(1, er, eg, eb, opacity)
        ctx.set_source(gradient)
    else:
        ctx.set_source_rgba(pr, pg, pb, opacity)

    ctx.arc(center, center, radius, start_rad, progress_end)
    ctx.stroke()

    if style == "dashed":
        ctx.set_dash([])


def _draw_hand(ctx, size, props, angle_deg):
    """Draw a hand element at the given angle (degrees, 0=3 o'clock)."""
    center = size / 2
    radius = size / 2
    style = props.get("style", "tapered")
    color = props.get("color", "#ffffff")
    width = props.get("width", 10)
    start_pct = props.get("start", -10) / 100
    end_pct = props.get("end", 65) / 100
    shadow = props.get("shadow", True)
    glow_enabled = props.get("glow", False)
    glow_color = props.get("glow_color", "#ffffff")
    image_path = props.get("image", "")

    angle = math.radians(angle_deg)
    tip_r = radius * end_pct
    if start_pct < 0:
        tail_r = radius * abs(start_pct)
        tail_x = center - tail_r * math.cos(angle)
        tail_y = center - tail_r * math.sin(angle)
    else:
        start_r = radius * start_pct
        tail_x = center + start_r * math.cos(angle)
        tail_y = center + start_r * math.sin(angle)

    tip_x = center + tip_r * math.cos(angle)
    tip_y = center + tip_r * math.sin(angle)

    if image_path and os.path.isfile(image_path):
        _draw_image_hand(ctx, center, angle_deg, image_path, end_pct, radius)
        return

    if style == "second":
        _draw_second_hand_element(ctx, center, radius, angle, tip_x, tip_y,
                                  tail_x, tail_y, props)
        return

    # Dial-style hands
    if style in ("triangle", "needle", "line") and start_pct >= -0.1:
        _draw_dial_hand(ctx, size, props, angle, center)
        return

    # Standard clock hands (tapered / classic)
    if shadow:
        draw_shadow(ctx, lambda c: _stroke_clock_hand(
            c, center, tip_x, tip_y, tail_x, tail_y, width, style, angle))

    r, g, b = hex_to_rgb(color)
    ctx.set_source_rgb(r, g, b)
    _stroke_clock_hand(ctx, center, tip_x, tip_y, tail_x, tail_y, width, style, angle)

    if glow_enabled:
        draw_glow(ctx, tip_x, tip_y, radius * 0.06, glow_color, intensity=0.4)


def _stroke_clock_hand(ctx, center, tip_x, tip_y, tail_x, tail_y, width, style, angle):
    """Stroke a clock hand shape (tapered or classic)."""
    if style == "tapered":
        perp = angle + math.pi / 2
        base_offset = width / 2
        tip_offset = width / 6
        ctx.new_path()
        ctx.move_to(tail_x + base_offset * math.cos(perp), tail_y + base_offset * math.sin(perp))
        ctx.line_to(tip_x + tip_offset * math.cos(perp), tip_y + tip_offset * math.sin(perp))
        ctx.line_to(tip_x - tip_offset * math.cos(perp), tip_y - tip_offset * math.sin(perp))
        ctx.line_to(tail_x - base_offset * math.cos(perp), tail_y - base_offset * math.sin(perp))
        ctx.close_path()
        ctx.fill()
    else:
        ctx.set_line_width(width)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.move_to(tail_x, tail_y)
        ctx.line_to(tip_x, tip_y)
        ctx.stroke()


def _draw_second_hand_element(ctx, center, radius, angle, tip_x, tip_y,
                              tail_x, tail_y, props):
    """Draw a second-hand style element (thin with optional counterweight)."""
    color = props.get("color", "#ff4444")
    shadow = props.get("shadow", True)
    glow_enabled = props.get("glow", False)
    glow_color = props.get("glow_color", "#ff4444")
    counterweight = props.get("counterweight", True)
    cw_radius = props.get("counterweight_radius", 4) / 100

    def _stroke(c):
        c.set_line_width(2.0)
        c.set_line_cap(cairo.LINE_CAP_ROUND)
        c.move_to(tail_x, tail_y)
        c.line_to(tip_x, tip_y)
        c.stroke()
        if counterweight:
            cw_dist = radius * cw_radius
            cw_x = center - cw_dist * 0.7 * math.cos(angle)
            cw_y = center - cw_dist * 0.7 * math.sin(angle)
            c.arc(cw_x, cw_y, radius * cw_radius, 0, 2 * math.pi)
            c.fill()

    if shadow:
        draw_shadow(ctx, _stroke)

    r, g, b = hex_to_rgb(color)
    ctx.set_source_rgb(r, g, b)
    _stroke(ctx)

    if glow_enabled:
        draw_glow(ctx, tip_x, tip_y, radius * 0.05, glow_color, intensity=0.35)


def _draw_dial_hand(ctx, size, props, angle, center):
    """Draw a dial-style hand (triangle, needle, line)."""
    half = size / 2
    tip_r = props.get("end", 80) / 100 * half
    tail_r = abs(props.get("start", -5)) / 100 * half
    width_val = props.get("width", 4)
    base_w = max(width_val, 2)
    style = props.get("style", "triangle")
    color = props.get("color", "#ffffff")
    hr, hg, hb = hex_to_rgb(color)

    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    cos_p = math.cos(angle + math.pi / 2)
    sin_p = math.sin(angle + math.pi / 2)

    tip_x = center + tip_r * cos_a
    tip_y = center + tip_r * sin_a
    tail_x = center - tail_r * cos_a
    tail_y = center - tail_r * sin_a

    ctx.set_source_rgb(hr, hg, hb)

    if style == "line":
        ctx.set_line_width(base_w)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.move_to(tail_x, tail_y)
        ctx.line_to(tip_x, tip_y)
        ctx.stroke()
    elif style == "needle":
        shaft_w = max(base_w * 0.3, 1)
        diamond_w = max(base_w * 1.2, 3)
        diamond_len = tip_r * 0.06
        ctx.set_line_width(shaft_w)
        ctx.set_line_cap(cairo.LINE_CAP_BUTT)
        diamond_base_x = center + (tip_r - diamond_len) * cos_a
        diamond_base_y = center + (tip_r - diamond_len) * sin_a
        ctx.move_to(tail_x, tail_y)
        ctx.line_to(diamond_base_x, diamond_base_y)
        ctx.stroke()
        ctx.move_to(tip_x, tip_y)
        ctx.line_to(diamond_base_x + diamond_w * cos_p, diamond_base_y + diamond_w * sin_p)
        ctx.line_to(center + (tip_r - diamond_len * 2) * cos_a,
                    center + (tip_r - diamond_len * 2) * sin_a)
        ctx.line_to(diamond_base_x - diamond_w * cos_p, diamond_base_y - diamond_w * sin_p)
        ctx.close_path()
        ctx.fill()
    else:  # triangle
        ctx.move_to(tip_x, tip_y)
        ctx.line_to(tail_x + base_w * cos_p, tail_y + base_w * sin_p)
        ctx.line_to(tail_x - base_w * cos_p, tail_y - base_w * sin_p)
        ctx.close_path()
        ctx.fill()


def _draw_image_hand(ctx, center, angle_deg, image_path, length_frac, radius):
    """Draw an image-based hand rotated to the given angle."""
    try:
        img = cairo.ImageSurface.create_from_png(image_path)
    except Exception:
        return
    img_w, img_h = img.get_width(), img.get_height()
    hand_len = radius * length_frac
    scale = hand_len / max(img_h, 1)

    ctx.save()
    ctx.translate(center, center)
    ctx.rotate(math.radians(angle_deg + 90))
    ctx.scale(scale, scale)
    ctx.set_source_surface(img, -img_w / 2, -img_h)
    ctx.paint()
    ctx.restore()


def _draw_radial_lines(ctx, size, props):
    """Draw radial line tick marks."""
    center = size / 2
    radius = size / 2
    count = props.get("count", 12)
    skip = props.get("skip_every", 0)
    inner_pct = props.get("inner_radius", 89) / 100
    outer_pct = props.get("outer_radius", 95) / 100
    width = props.get("width", 3)
    color = props.get("color", "#ffffff")
    do_shadow = props.get("shadow", False)

    r, g, b = hex_to_rgb(color)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)

    for i in range(count):
        if skip and i % skip == 0:
            continue
        angle = math.radians(i * (360 / count) - 90)
        inner = radius * inner_pct
        outer = radius * outer_pct
        x1, y1 = center + inner * math.cos(angle), center + inner * math.sin(angle)
        x2, y2 = center + outer * math.cos(angle), center + outer * math.sin(angle)

        if do_shadow:
            ctx.set_source_rgba(0, 0, 0, 0.3)
            ctx.set_line_width(width)
            ctx.move_to(x1 + 2, y1 + 2)
            ctx.line_to(x2 + 2, y2 + 2)
            ctx.stroke()

        ctx.set_source_rgb(r, g, b)
        ctx.set_line_width(width)
        ctx.move_to(x1, y1)
        ctx.line_to(x2, y2)
        ctx.stroke()


def _draw_radial_dots(ctx, size, props):
    """Draw radial dot markers."""
    center = size / 2
    radius = size / 2
    count = props.get("count", 12)
    skip = props.get("skip_every", 0)
    pos_pct = props.get("radius", 95) / 100
    dot_r = props.get("dot_radius", 5)
    color = props.get("color", "#ffffff")
    do_shadow = props.get("shadow", False)

    r, g, b = hex_to_rgb(color)

    for i in range(count):
        if skip and i % skip == 0:
            continue
        angle = math.radians(i * (360 / count) - 90)
        x = center + radius * pos_pct * math.cos(angle)
        y = center + radius * pos_pct * math.sin(angle)

        if do_shadow:
            ctx.set_source_rgba(0, 0, 0, 0.3)
            ctx.arc(x + 2, y + 2, dot_r, 0, 2 * math.pi)
            ctx.fill()

        ctx.set_source_rgb(r, g, b)
        ctx.arc(x, y, dot_r, 0, 2 * math.pi)
        ctx.fill()


def _draw_radial_text(ctx, size, props):
    """Draw text labels around the face (hour numbers, etc.)."""
    center = size / 2
    radius = size / 2
    count = props.get("count", 12)
    labels = props.get("labels", [])
    style = props.get("style", "arabic")
    radius_pct = props.get("radius", 82) / 100
    color = props.get("color", "#e0e0e0")
    font_size = props.get("font_size", 0)
    font_family = props.get("font_family", "sans-serif")

    if font_family == "serif":
        font_family = _SERIF_FONT
    elif font_family == "sans-serif":
        font_family = _SANS_FONT

    if not labels or len(labels) < count:
        if style == "roman":
            from src.faces.elements import ROMAN_LABELS
            labels = ROMAN_LABELS
        else:
            from src.faces.elements import ARABIC_LABELS
            labels = ARABIC_LABELS

    r, g, b = hex_to_rgb(color)
    if font_size <= 0:
        font_size = radius * 0.1

    ctx.select_font_face(font_family, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(font_size)

    for i in range(min(count, len(labels))):
        label = labels[i]
        if not label:
            continue
        angle = math.radians(i * (360 / count) - 90)
        x = center + radius * radius_pct * math.cos(angle)
        y = center + radius * radius_pct * math.sin(angle)
        extents = ctx.text_extents(label)

        ctx.set_source_rgb(r, g, b)
        ctx.move_to(x - extents.width / 2, y + extents.height / 2)
        ctx.show_text(label)


def _draw_text(ctx, size, props, position, text_value):
    """Draw a text element at a position."""
    center = size / 2
    radius = size / 2

    if text_value is None:
        text_value = props.get("static_text", "")
    if not text_value:
        return

    prefix = props.get("prefix", "")
    suffix = props.get("suffix", "")
    display = f"{prefix}{text_value}{suffix}"

    color = props.get("color", "#ffffff")
    r, g, b = hex_to_rgb(color)
    font_size = props.get("font_size", 0)
    font_family = props.get("font_family", "sans-serif")

    if font_family == "serif":
        font_family = _SERIF_FONT
    elif font_family == "sans-serif":
        font_family = _SANS_FONT

    pos_x = center + (position[0] if position else 0) / 100 * radius
    pos_y = center + (position[1] if position else 0) / 100 * radius

    if font_size <= 0:
        font_size = radius * 0.12

    ctx.select_font_face(font_family, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(font_size)
    extents = ctx.text_extents(display)

    align = props.get("align", "center")
    if align == "center":
        tx = pos_x - extents.width / 2 - extents.x_bearing
    elif align == "right":
        tx = pos_x - extents.width - extents.x_bearing
    else:
        tx = pos_x
    ty = pos_y + extents.height / 2

    # Shadow
    ctx.set_source_rgba(0, 0, 0, 0.4)
    ctx.move_to(tx + 1, ty + 1)
    ctx.show_text(display)

    ctx.set_source_rgb(r, g, b)
    ctx.move_to(tx, ty)
    ctx.show_text(display)


def _draw_alarm_indicators(ctx, size, props, alarms):
    """Draw alarm indicator dots on the face."""
    if not alarms:
        return
    center = size / 2
    radius = size / 2
    color = props.get("color", "#ffaa00")
    dot_size = props.get("size", 4)
    pos_pct = props.get("radius", 70) / 100
    r, g, b = hex_to_rgb(color)

    for alarm in alarms:
        time_str = alarm.get("time", "")
        if not time_str or not alarm.get("enabled", True):
            continue
        try:
            parts = time_str.split(":")
            hour = int(parts[0]) % 12
            minute = int(parts[1])
        except (ValueError, IndexError):
            continue

        angle = math.radians((hour + minute / 60) * 30 - 90)
        x = center + radius * pos_pct * math.cos(angle)
        y = center + radius * pos_pct * math.sin(angle)

        ctx.set_source_rgb(r, g, b)
        ctx.arc(x, y, dot_size, 0, 2 * math.pi)
        ctx.fill()

        # Triangle pointer
        ctx.new_path()
        tip_x = center + radius * (pos_pct + 0.04) * math.cos(angle)
        tip_y = center + radius * (pos_pct + 0.04) * math.sin(angle)
        perp = angle + math.pi / 2
        base_off = dot_size * 0.6
        ctx.move_to(tip_x, tip_y)
        ctx.line_to(x + base_off * math.cos(perp), y + base_off * math.sin(perp))
        ctx.line_to(x - base_off * math.cos(perp), y - base_off * math.sin(perp))
        ctx.close_path()
        ctx.fill()


def _draw_agenda(ctx, size, props, events):
    """Draw agenda events as pie/donut chart slices."""
    if not events:
        return
    center = size / 2
    radius = size / 2
    min_r = props.get("min_radius", 45) / 100 * radius
    max_r = props.get("max_radius", 65) / 100 * radius
    opacity = props.get("opacity", 30) / 100

    if max_r <= min_r:
        return

    for ev in events:
        start_str = ev.get("start_time", "")
        end_str = ev.get("end_time", "")
        color = ev.get("color", "#4488ff")
        if not start_str or not end_str:
            continue
        try:
            sh, sm = int(start_str.split(":")[0]), int(start_str.split(":")[1])
            eh, em = int(end_str.split(":")[0]), int(end_str.split(":")[1])
        except (ValueError, IndexError):
            continue

        start_mins = sh * 60 + sm
        end_mins = eh * 60 + em
        if end_mins <= start_mins:
            end_mins += 24 * 60
        duration_hours = min((end_mins - start_mins) / 60, 12)

        start_pos = (sh % 12) + sm / 60
        start_angle = math.radians(start_pos * 30 - 90)
        end_angle = start_angle + math.radians(duration_hours * 30)

        r, g, b = hex_to_rgb(color)
        ctx.set_source_rgba(r, g, b, opacity)
        ctx.new_path()
        ctx.arc(center, center, max_r, start_angle, end_angle)
        ctx.arc_negative(center, center, min_r, end_angle, start_angle)
        ctx.close_path()
        ctx.fill()


def _draw_arc_ticks(ctx, size, props):
    """Draw tick marks along an arc (for dial-style displays)."""
    if props.get("arc_symmetric", False):
        center_deg = props.get("arc_center", 0)
        extent = props.get("arc_extent", 135)
        arc_start = center_deg - extent
        arc_end = center_deg + extent
    else:
        arc_start = props.get("arc_start", 135)
        arc_end = props.get("arc_end", 405)

    start_rad = _deg_to_rad(arc_start)
    end_rad = _deg_to_rad(arc_end)
    arc_sweep = end_rad - start_rad

    center = size / 2
    half = size / 2
    major_count = props.get("major_count", 10)
    if major_count < 2:
        return

    # Minor ticks first (behind majors) — batched
    if props.get("minor_ticks", False):
        minor_per = props.get("minor_count", 4)
        if minor_per > 0:
            min_inner = props.get("minor_inner_radius", 74) / 100 * half
            min_outer = props.get("minor_outer_radius", 77) / 100 * half
            min_width = props.get("minor_width", 1)
            min_color = props.get("minor_color", "#666666")
            mnr, mng, mnb = hex_to_rgb(min_color)

            ctx.set_source_rgb(mnr, mng, mnb)
            ctx.set_line_width(min_width)
            ctx.set_line_cap(cairo.LINE_CAP_BUTT)

            for i in range(major_count):
                for j in range(1, minor_per + 1):
                    frac = (i + j / (minor_per + 1)) / major_count
                    angle = start_rad + arc_sweep * frac
                    cos_a = math.cos(angle)
                    sin_a = math.sin(angle)
                    ctx.move_to(center + min_inner * cos_a, center + min_inner * sin_a)
                    ctx.line_to(center + min_outer * cos_a, center + min_outer * sin_a)
            ctx.stroke()

    # Major ticks — batched
    maj_inner = props.get("major_inner_radius", 72) / 100 * half
    maj_outer = props.get("major_outer_radius", 77) / 100 * half
    maj_width = props.get("major_width", 2)
    maj_color = props.get("major_color", "#ffffff")
    mr, mg, mb = hex_to_rgb(maj_color)

    ctx.set_source_rgb(mr, mg, mb)
    ctx.set_line_width(maj_width)
    ctx.set_line_cap(cairo.LINE_CAP_BUTT)

    for i in range(major_count + 1):
        angle = start_rad + arc_sweep * i / major_count
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        ctx.move_to(center + maj_inner * cos_a, center + maj_inner * sin_a)
        ctx.line_to(center + maj_outer * cos_a, center + maj_outer * sin_a)
    ctx.stroke()


# =========================================================================
# Main render function
# =========================================================================

def _render_static_layer(face, data_ctx):
    """Render static elements + mask into a cached surface."""
    global _mask_surface
    if _mask_surface is None:
        _mask_surface = _create_mask_surface()

    size = DISPLAY_SIZE
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    ctx = cairo.Context(surface)

    for element in face.get("elements", []):
        if _is_dynamic(element):
            continue
        _draw_element(ctx, size, element, data_ctx)

    # Bake mask
    ctx.set_source_surface(_mask_surface, 0, 0)
    ctx.paint()

    surface.flush()
    return surface


def _draw_element(ctx, size, element, data_ctx, force_dynamic=False):
    """Dispatch drawing of a single element."""
    etype = element.get("type", "")
    props = element.get("properties", {})
    position = element.get("position")
    bindings = element.get("bindings", {})

    if etype == "background":
        _draw_background(ctx, size, props)

    elif etype == "circle":
        _draw_circle(ctx, size, props, position)

    elif etype == "arc":
        if "progress" in bindings:
            # Dynamic: draw progress arc
            progress_binding = bindings["progress"]
            progress = data_ctx.resolve_binding(progress_binding)
            _draw_arc_progress(ctx, size, props, progress, data_ctx)
        else:
            # Static: draw track arc
            _draw_arc_static(ctx, size, props)

    elif etype == "hand":
        angle_binding = bindings.get("angle", {})
        angle = data_ctx.resolve_binding(angle_binding) if angle_binding else 0
        _draw_hand(ctx, size, props, angle)

    elif etype == "radial_lines":
        _draw_radial_lines(ctx, size, props)

    elif etype == "radial_dots":
        _draw_radial_dots(ctx, size, props)

    elif etype == "radial_text":
        _draw_radial_text(ctx, size, props)

    elif etype == "text":
        text_value = None
        if "text" in bindings:
            text_binding = bindings["text"]
            text_value = data_ctx.resolve_binding(text_binding)
            if text_value is not None:
                text_value = str(text_value)
        _draw_text(ctx, size, props, position, text_value)

    elif etype == "alarm_indicators":
        items = None
        if "items" in bindings:
            items = data_ctx.resolve_binding(bindings["items"])
        _draw_alarm_indicators(ctx, size, props, items or [])

    elif etype == "agenda":
        events = None
        if "events" in bindings:
            events = data_ctx.resolve_binding(bindings["events"])
        _draw_agenda(ctx, size, props, events or [])

    elif etype == "arc_ticks":
        _draw_arc_ticks(ctx, size, props)


def render_face_frame(face, data_ctx, overlay_fn=None):
    """Render a complete face frame.

    Args:
        face: Face dict with 'elements' list.
        data_ctx: DataContext with current live values.
        overlay_fn: Optional overlay function (alarm flash, etc.)

    Returns:
        bytearray: RGB pixel buffer for display.
    """
    global _static_cache_surface, _static_cache_dirty
    global _last_face_id, _last_data_context_id

    size = DISPLAY_SIZE

    # Identity-based change detection
    f_id = id(face)
    # For data that affects static elements (alarms, agenda), check identity
    static_data_id = (id(data_ctx.alarms), id(data_ctx.agenda_events))
    if f_id != _last_face_id or static_data_id != _last_data_context_id:
        _static_cache_dirty = True
        _last_face_id = f_id
        _last_data_context_id = static_data_id

    # Rebuild static layer only when inputs change
    if _static_cache_dirty or _static_cache_surface is None:
        _static_cache_surface = _render_static_layer(face, data_ctx)
        _static_cache_dirty = False

    # Start from cached static layer
    ctx = cairo.Context(_frame_surface)
    ctx.set_operator(cairo.OPERATOR_SOURCE)
    ctx.set_source_surface(_static_cache_surface, 0, 0)
    ctx.paint()
    ctx.set_operator(cairo.OPERATOR_OVER)

    # Draw dynamic elements only
    for element in face.get("elements", []):
        if _is_dynamic(element):
            _draw_element(ctx, size, element, data_ctx)

    if overlay_fn:
        overlay_fn(ctx, size)

    _frame_surface.flush()

    # BGRA → RGB conversion
    _conv_arr[:, :, 0] = _src_arr[:, :, 2]
    _conv_arr[:, :, 1] = _src_arr[:, :, 1]
    _conv_arr[:, :, 2] = _src_arr[:, :, 0]
    return _conv_buf
