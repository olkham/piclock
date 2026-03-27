"""Shared colour utilities for the clock rendering modules."""

import functools


@functools.lru_cache(maxsize=64)
def hex_to_rgb(hex_color):
    """Convert hex colour string to (r, g, b) floats in 0-1 range."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
