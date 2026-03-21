import math
import os

import cairo

from src.clock.effects import draw_shadow, draw_glow


def _get_start_end(cfg, default_start, default_end):
    """Get start/end % from config, with fallback to legacy length/tail."""
    if "start" in cfg and "end" in cfg:
        return cfg["start"] / 100, cfg["end"] / 100
    # Legacy fallback: convert length/tail to start/end fractions
    length = cfg.get("length", default_end / 100)
    tail = cfg.get("tail", abs(default_start) / 100)
    return -tail, length


def draw_hands(ctx, size, time_info, theme):
    """Draw all clock hands."""
    center = size / 2
    hands = theme.get("hands", {})

    hour = time_info["hour"] % 12
    minute = time_info["minute"]
    second = time_info["second"]
    microsecond = time_info.get("microsecond", 0)

    # Smooth angles
    hour_angle = (hour + minute / 60) * 30 - 90
    minute_angle = (minute + second / 60) * 6 - 90
    second_angle = (second + microsecond / 1_000_000) * 6 - 90

    # Hour hand
    hour_cfg = hands.get("hour", {})
    h_start, h_end = _get_start_end(hour_cfg, -8, 45)
    _draw_hand(
        ctx, center,
        angle_deg=hour_angle,
        start=h_start,
        end=h_end,
        width=hour_cfg.get("width", 12.0),
        color=hour_cfg.get("color", "#ffffff"),
        shadow=hour_cfg.get("shadow", True),
        glow=hour_cfg.get("glow", False),
        glow_color=hour_cfg.get("glow_color", "#ffffff"),
        style=hour_cfg.get("style", "tapered"),
        image_path=hour_cfg.get("image"),
        radius=size / 2,
    )

    # Minute hand
    min_cfg = hands.get("minute", {})
    m_start, m_end = _get_start_end(min_cfg, -10, 65)
    _draw_hand(
        ctx, center,
        angle_deg=minute_angle,
        start=m_start,
        end=m_end,
        width=min_cfg.get("width", 8.0),
        color=min_cfg.get("color", "#ffffff"),
        shadow=min_cfg.get("shadow", True),
        glow=min_cfg.get("glow", False),
        glow_color=min_cfg.get("glow_color", "#ffffff"),
        style=min_cfg.get("style", "tapered"),
        image_path=min_cfg.get("image"),
        radius=size / 2,
    )

    # Second hand
    sec_cfg = hands.get("second", {})
    if sec_cfg.get("visible", True):
        sec_image = sec_cfg.get("image", "")
        s_start, s_end = _get_start_end(sec_cfg, -15, 72)
        if sec_image and os.path.isfile(sec_image):
            _draw_image_hand(ctx, center, second_angle, sec_image,
                             s_end, size / 2)
        else:
            _draw_second_hand(
                ctx, center,
                angle_deg=second_angle,
                start=s_start,
                end=s_end,
                color=sec_cfg.get("color", "#ff4444"),
                shadow=sec_cfg.get("shadow", True),
                glow=sec_cfg.get("glow", False),
                glow_color=sec_cfg.get("glow_color", "#ff4444"),
                radius=size / 2,
                counterweight=sec_cfg.get("counterweight", True),
                counterweight_radius=sec_cfg.get("counterweight_radius", 0.04),
            )

    # Center dot
    dot = theme.get("center_dot", {})
    if dot.get("visible", True):
        r, g, b = _hex_to_rgb(dot.get("color", "#ffffff"))
        ctx.set_source_rgb(r, g, b)
        ctx.arc(center, center, dot.get("radius", 6), 0, 2 * math.pi)
        ctx.fill()


def _draw_hand(ctx, center, angle_deg, start, end, width, color,
               shadow, glow, glow_color, style, image_path, radius):
    """Draw a single clock hand (hour or minute)."""
    if image_path and os.path.isfile(image_path):
        _draw_image_hand(ctx, center, angle_deg, image_path, end, radius)
        return

    angle = math.radians(angle_deg)
    tip_r = radius * end
    tail_r = radius * abs(start) if start < 0 else 0
    start_r = radius * start if start >= 0 else 0

    tip_x = center + tip_r * math.cos(angle)
    tip_y = center + tip_r * math.sin(angle)
    if start < 0:
        tail_x = center - tail_r * math.cos(angle)
        tail_y = center - tail_r * math.sin(angle)
    else:
        tail_x = center + start_r * math.cos(angle)
        tail_y = center + start_r * math.sin(angle)

    if shadow:
        draw_shadow(ctx, lambda c: _stroke_hand(c, center, tip_x, tip_y, tail_x, tail_y, width, style, angle))

    r, g, b = _hex_to_rgb(color)
    ctx.set_source_rgb(r, g, b)
    _stroke_hand(ctx, center, tip_x, tip_y, tail_x, tail_y, width, style, angle)

    if glow:
        draw_glow(ctx, tip_x, tip_y, radius * 0.06, glow_color, intensity=0.4)


def _stroke_hand(ctx, center, tip_x, tip_y, tail_x, tail_y, width, style, angle):
    """Stroke a hand shape."""
    if style == "tapered":
        # Tapered hand: wider at base, narrower at tip
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
        # Classic rectangular hand
        ctx.set_line_width(width)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.move_to(tail_x, tail_y)
        ctx.line_to(tip_x, tip_y)
        ctx.stroke()


def _draw_second_hand(ctx, center, angle_deg, start, end, color, shadow,
                      glow, glow_color, radius, counterweight, counterweight_radius):
    """Draw the second hand with optional counterweight."""
    angle = math.radians(angle_deg)
    tip_r = radius * end
    tail_r = radius * abs(start) if start < 0 else 0
    start_r = radius * start if start >= 0 else 0

    tip_x = center + tip_r * math.cos(angle)
    tip_y = center + tip_r * math.sin(angle)
    if start < 0:
        tail_x = center - tail_r * math.cos(angle)
        tail_y = center - tail_r * math.sin(angle)
    else:
        tail_x = center + start_r * math.cos(angle)
        tail_y = center + start_r * math.sin(angle)

    if shadow:
        draw_shadow(ctx, lambda c: _stroke_second(
            c, tail_x, tail_y, tip_x, tip_y, center, angle, radius,
            counterweight, counterweight_radius))

    r, g, b = _hex_to_rgb(color)
    ctx.set_source_rgb(r, g, b)
    _stroke_second(ctx, tail_x, tail_y, tip_x, tip_y, center, angle, radius,
                   counterweight, counterweight_radius)

    if glow:
        draw_glow(ctx, tip_x, tip_y, radius * 0.05, glow_color, intensity=0.35)


def _stroke_second(ctx, tail_x, tail_y, tip_x, tip_y, center, angle, radius,
                   counterweight=True, counterweight_radius=0.04):
    """Stroke the second hand shape."""
    # Thin main line
    ctx.set_line_width(2.0)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.move_to(tail_x, tail_y)
    ctx.line_to(tip_x, tip_y)
    ctx.stroke()

    # Counterweight circle
    if counterweight:
        cw_r = radius * counterweight_radius
        cw_dist = radius * 0.10
        cw_x = center - cw_dist * math.cos(angle)
        cw_y = center - cw_dist * math.sin(angle)
        ctx.arc(cw_x, cw_y, cw_r, 0, 2 * math.pi)
        ctx.fill()


def _draw_image_hand(ctx, center, angle_deg, image_path, length, radius):
    """Draw a hand from an image file, rotated to the correct angle."""
    try:
        img_surface = cairo.ImageSurface.create_from_png(image_path)
    except Exception:
        return  # Silently fall back if image can't be loaded

    img_w = img_surface.get_width()
    img_h = img_surface.get_height()

    # Scale image to fit the hand length
    target_h = radius * length * 2
    scale = target_h / img_h

    ctx.save()
    ctx.translate(center, center)
    ctx.rotate(math.radians(angle_deg + 90))  # +90 because images point up
    ctx.scale(scale, scale)
    ctx.set_source_surface(img_surface, -img_w / 2, -img_h)
    ctx.paint()
    ctx.restore()


def _hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))
