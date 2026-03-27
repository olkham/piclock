import math
import cairo

from src.clock.color import hex_to_rgb


def draw_shadow(ctx, draw_fn, offset_x=3, offset_y=3, blur_alpha=0.3):
    """Draw a drop shadow by rendering the shape offset and semi-transparent.

    Args:
        ctx: Cairo context
        draw_fn: Callable that draws the shape (accepts a Cairo context)
        offset_x: Shadow x offset in pixels
        offset_y: Shadow y offset in pixels
        blur_alpha: Shadow opacity
    """
    ctx.save()
    ctx.translate(offset_x, offset_y)
    ctx.set_source_rgba(0, 0, 0, blur_alpha)
    draw_fn(ctx)
    ctx.restore()


def draw_glow(ctx, x, y, radius, color_hex, intensity=0.5):
    """Draw a soft glow effect at a point."""
    r, g, b = hex_to_rgb(color_hex)
    pattern = cairo.RadialGradient(x, y, 0, x, y, radius)
    pattern.add_color_stop_rgba(0, r, g, b, intensity)
    pattern.add_color_stop_rgba(1, r, g, b, 0)
    ctx.set_source(pattern)
    ctx.arc(x, y, radius, 0, 2 * math.pi)
    ctx.fill()

