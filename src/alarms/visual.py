"""Visual alarm overlay on the clock face — customizable animations."""

import math
import sys
import time

import cairo

_FONT = "Arial" if sys.platform == "win32" else "sans-serif"

# Speed multipliers
_SPEED = {"slow": 2.0, "normal": 4.0, "fast": 8.0}


class AlarmOverlay:
    """Draws a customizable visual indicator when an alarm is active."""

    def __init__(self, label="Alarm", shape="ring", color="#ff3333",
                 speed="normal"):
        self._label = label
        self._shape = shape
        self._color = color
        self._speed = _SPEED.get(speed, 4.0)
        self._start_time = time.time()

    def draw(self, ctx, size):
        """Draw the alarm overlay on a Cairo context."""
        center = size / 2
        radius = size / 2
        elapsed = time.time() - self._start_time
        pulse = (math.sin(elapsed * self._speed) + 1) / 2  # 0..1

        r, g, b = _hex_to_rgb(self._color)

        if self._shape == "flash":
            self._draw_flash(ctx, size, center, radius, pulse, r, g, b)
        elif self._shape == "border_glow":
            self._draw_border_glow(ctx, center, radius, pulse, r, g, b)
        else:
            self._draw_ring(ctx, center, radius, pulse, r, g, b)

        # Label text with alarm bell icon
        label_text = self._label
        ctx.set_source_rgba(1.0, 1.0, 1.0, 0.9)
        ctx.select_font_face(_FONT, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        font_size = radius * 0.08
        ctx.set_font_size(font_size)
        extents = ctx.text_extents(label_text)
        total_w = font_size * 0.9 + extents.width
        text_x = center - total_w / 2 + font_size * 0.9
        text_y = center + radius * 0.35

        # Draw bell icon to the left of the label
        _draw_bell_icon(ctx, text_x - font_size * 0.6, text_y - font_size * 0.5, font_size * 0.7)

        ctx.set_source_rgba(1.0, 1.0, 1.0, 0.9)
        ctx.move_to(text_x, text_y)
        ctx.show_text(label_text)

    def _draw_ring(self, ctx, center, radius, pulse, r, g, b):
        alpha = 0.2 + pulse * 0.5
        ctx.set_source_rgba(r, g, b, alpha)
        ctx.set_line_width(6 + pulse * 8)
        ctx.arc(center, center, radius * 0.92, 0, 2 * math.pi)
        ctx.stroke()

        # Inner ring
        ctx.set_source_rgba(r, g, b, alpha * 0.4)
        ctx.set_line_width(3 + pulse * 4)
        ctx.arc(center, center, radius * 0.84, 0, 2 * math.pi)
        ctx.stroke()

    def _draw_flash(self, ctx, size, center, radius, pulse, r, g, b):
        alpha = pulse * 0.25
        ctx.set_source_rgba(r, g, b, alpha)
        ctx.arc(center, center, radius, 0, 2 * math.pi)
        ctx.fill()

    def _draw_border_glow(self, ctx, center, radius, pulse, r, g, b):
        glow_width = 20 + pulse * 30
        pattern = cairo.RadialGradient(
            center, center, radius - glow_width,
            center, center, radius,
        )
        alpha = 0.3 + pulse * 0.5
        pattern.add_color_stop_rgba(0, r, g, b, 0)
        pattern.add_color_stop_rgba(1, r, g, b, alpha)
        ctx.set_source(pattern)
        ctx.arc(center, center, radius, 0, 2 * math.pi)
        ctx.fill()


def _hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))


def _draw_bell_icon(ctx, cx, cy, size):
    """Draw a simple bell/alarm icon using Cairo paths."""
    ctx.save()
    ctx.set_source_rgba(1.0, 1.0, 1.0, 0.9)
    s = size / 2

    # Bell body (rounded trapezoid shape)
    ctx.move_to(cx - s * 0.7, cy + s * 0.5)
    ctx.curve_to(cx - s * 0.7, cy - s * 0.3,
                 cx - s * 0.4, cy - s * 0.9,
                 cx, cy - s * 0.9)
    ctx.curve_to(cx + s * 0.4, cy - s * 0.9,
                 cx + s * 0.7, cy - s * 0.3,
                 cx + s * 0.7, cy + s * 0.5)
    ctx.close_path()
    ctx.fill()

    # Bell rim (horizontal bar at bottom)
    ctx.set_line_width(s * 0.15)
    ctx.move_to(cx - s * 0.85, cy + s * 0.5)
    ctx.line_to(cx + s * 0.85, cy + s * 0.5)
    ctx.stroke()

    # Clapper (small circle at bottom)
    ctx.arc(cx, cy + s * 0.75, s * 0.15, 0, 2 * math.pi)
    ctx.fill()

    # Handle (small arc on top)
    ctx.set_line_width(s * 0.12)
    ctx.arc(cx, cy - s * 0.9, s * 0.2, math.pi, 0)
    ctx.stroke()

    ctx.restore()
