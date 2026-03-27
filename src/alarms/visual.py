"""Visual alarm overlay on the clock face — customizable animations."""

import math
import sys
import time

import cairo
from src.clock.color import hex_to_rgb
_FONT = "Arial" if sys.platform == "win32" else "sans-serif"

# Speed multipliers
_SPEED = {"slow": 2.0, "normal": 4.0, "fast": 8.0}


class AlarmOverlay:
    """Draws a customizable visual indicator when an alarm is active."""

    def __init__(self, label="Alarm", shape="ring", color="#ff3333",
                 speed="normal", position="bottom"):
        self._label = label
        self._shape = shape
        self._color = color
        self._speed = _SPEED.get(speed, 4.0)
        self._position = position  # "top", "center", "bottom"
        self._start_time = time.time()
        # Pre-cached surfaces for expensive effects
        self._glow_surface = None
        self._glow_cache_key = None
        self._label_surface = None
        self._label_cache_key = None

    def draw(self, ctx, size):
        """Draw the alarm overlay on a Cairo context."""
        center = size / 2
        radius = size / 2
        elapsed = time.time() - self._start_time
        pulse = (math.sin(elapsed * self._speed) + 1) / 2  # 0..1

        r, g, b = hex_to_rgb(self._color)

        if self._shape == "flash":
            self._draw_flash(ctx, size, center, radius, pulse, r, g, b)
        elif self._shape == "border_glow":
            self._draw_border_glow(ctx, size, center, radius, pulse, r, g, b)
        else:
            self._draw_ring(ctx, center, radius, pulse, r, g, b)

        # Cached label + bell icon overlay
        self._draw_label(ctx, size, center, radius)

    def _draw_label(self, ctx, size, center, radius):
        """Draw the label text + bell icon, cached to a surface."""
        cache_key = (size, self._label, self._position)
        if self._label_surface is None or self._label_cache_key != cache_key:
            self._label_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
            lctx = cairo.Context(self._label_surface)
            font_size = radius * 0.08
            lctx.set_source_rgba(1.0, 1.0, 1.0, 0.9)
            lctx.select_font_face(_FONT, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            lctx.set_font_size(font_size)
            extents = lctx.text_extents(self._label)
            total_w = font_size * 0.9 + extents.width
            text_x = center - total_w / 2 + font_size * 0.9
            # Position based on setting
            if self._position == "top":
                text_y = center - radius * 0.35
            elif self._position == "center":
                text_y = center
            else:  # "bottom" (default)
                text_y = center + radius * 0.35
            _draw_bell_icon(lctx, text_x - font_size * 0.6, text_y - font_size * 0.5, font_size * 0.7)
            lctx.set_source_rgba(1.0, 1.0, 1.0, 0.9)
            lctx.move_to(text_x, text_y)
            lctx.show_text(self._label)
            self._label_surface.flush()
            self._label_cache_key = cache_key

        ctx.set_source_surface(self._label_surface, 0, 0)
        ctx.paint()

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

    def _draw_border_glow(self, ctx, size, center, radius, pulse, r, g, b):
        """Optimized border glow: pre-render gradient to cached surface, composite with varying alpha."""
        cache_key = (size, self._color)
        if self._glow_surface is None or self._glow_cache_key != cache_key:
            # Render the glow gradient at full intensity once
            self._glow_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
            gctx = cairo.Context(self._glow_surface)
            glow_width = 50  # fixed max glow width
            pattern = cairo.RadialGradient(
                center, center, radius - glow_width,
                center, center, radius,
            )
            pattern.add_color_stop_rgba(0, r, g, b, 0)
            pattern.add_color_stop_rgba(1, r, g, b, 1.0)
            gctx.set_source(pattern)
            gctx.arc(center, center, radius, 0, 2 * math.pi)
            gctx.fill()
            self._glow_surface.flush()
            self._glow_cache_key = cache_key

        # Composite cached glow with pulse-driven alpha (no gradient computation per frame)
        alpha = 0.3 + pulse * 0.5
        ctx.set_source_surface(self._glow_surface, 0, 0)
        ctx.paint_with_alpha(alpha)


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
