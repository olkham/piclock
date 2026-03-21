"""Theme schema definition and validation."""

THEME_SCHEMA = {
    "name": str,
    "background": {
        "type": str,       # "solid", "gradient", "image"
        "color": str,      # hex, used for solid / fallback
        "colors": list,    # list of hex strings for gradient
        "gradient_type": str,  # "radial" or "linear"
        "gradient_angle": (int, float),  # degrees for linear gradient
        "gradient_center_x": (int, float),  # 0-1, center X for radial (default 0.5)
        "gradient_center_y": (int, float),  # 0-1, center Y for radial (default 0.5)
        "gradient_radius": (int, float),    # 0-1, radius fraction for radial (default 1.0)
        "color_stops": list,   # list of {"color": hex, "position": 0-1} for fine control
        "image": str,      # path for image background
    },
    "markers": {
        "hour_style": str,       # "line", "dot", "roman", "arabic", "custom", "none"
        "hour_labels": list,     # list of 12 strings for custom style
        "hour_color": str,
        "hour_width": (int, float),
        "hour_length": (int, float),
        "dot_radius": (int, float),
        "font_size": (int, float),
        "hour_shadow": bool,
        "show_minutes": bool,
        "minute_style": str,     # "line" or "dot"
        "minute_color": str,
        "minute_width": (int, float),
        "minute_length": (int, float),
        "minute_dot_radius": (int, float),
        "minute_shadow": bool,
    },
    "hands": {
        "hour": {
            "style": str,       # "tapered", "classic"
            "color": str,
            "width": (int, float),
            "length": (int, float),      # legacy — use start/end instead
            "tail": (int, float),        # legacy — use start/end instead
            "start": (int, float),       # start % of radius (negative = behind center)
            "end": (int, float),         # end % of radius (tip position)
            "shadow": bool,
            "glow": bool,
            "glow_color": str,
            "image": str,       # optional path to image
        },
        "minute": {
            "style": str,
            "color": str,
            "width": (int, float),
            "length": (int, float),
            "tail": (int, float),
            "start": (int, float),
            "end": (int, float),
            "shadow": bool,
            "glow": bool,
            "glow_color": str,
            "image": str,
        },
        "second": {
            "visible": bool,
            "color": str,
            "length": (int, float),
            "tail": (int, float),
            "start": (int, float),
            "end": (int, float),
            "shadow": bool,
            "glow": bool,
            "glow_color": str,
            "style": str,       # "line", "image"
            "image": str,
            "counterweight": bool,
            "counterweight_radius": (int, float),
        },
    },
    "center_dot": {
        "visible": bool,
        "color": str,
        "radius": (int, float),
    },
    "alarm_indicators": {
        "visible": bool,
        "color": str,
        "size": (int, float),
    },
}


DEFAULT_THEME = {
    "name": "Classic",
    "background": {
        "type": "gradient",
        "color": "#1a1a2e",
        "colors": ["#1a1a2e", "#16213e"],
        "gradient_type": "radial",
        "gradient_angle": 0,
        "gradient_center_x": 0.5,
        "gradient_center_y": 0.5,
        "gradient_radius": 1.0,
        "color_stops": [],
        "image": "",
    },
    "markers": {
        "hour_style": "roman",
        "hour_labels": ["XII", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI"],
        "hour_color": "#e0e0e0",
        "hour_width": 3.0,
        "hour_length": 0.06,
        "dot_radius": 5.0,
        "font_size": 0,  # 0 = auto-calculate
        "hour_shadow": False,
        "show_minutes": True,
        "minute_style": "line",
        "minute_color": "#555555",
        "minute_width": 1.5,
        "minute_length": 0.02,
        "minute_dot_radius": 2.0,
        "minute_shadow": False,
    },
    "hands": {
        "hour": {
            "style": "tapered",
            "color": "#ffffff",
            "width": 14.0,
            "length": 0.45,
            "tail": 0.08,
            "shadow": True,
            "glow": False,
            "glow_color": "#ffffff",
            "image": "",
        },
        "minute": {
            "style": "tapered",
            "color": "#ffffff",
            "width": 10.0,
            "length": 0.65,
            "tail": 0.10,
            "shadow": True,
            "glow": False,
            "glow_color": "#ffffff",
            "image": "",
        },
        "second": {
            "visible": True,
            "color": "#ff4444",
            "length": 0.72,
            "tail": 0.15,
            "shadow": True,
            "glow": False,
            "glow_color": "#ff4444",
            "style": "line",
            "image": "",
            "counterweight": True,
            "counterweight_radius": 0.04,
        },
    },
    "center_dot": {
        "visible": True,
        "color": "#ffffff",
        "radius": 7,
    },
    "alarm_indicators": {
        "visible": True,
        "color": "#ffaa00",
        "size": 4.0,
    },
}


def validate_theme(theme):
    """Validate a theme dict has required fields. Returns list of errors."""
    errors = []
    if not isinstance(theme, dict):
        return ["Theme must be a dictionary"]
    if "name" not in theme:
        errors.append("Missing required field: name")
    if not isinstance(theme.get("name", ""), str):
        errors.append("'name' must be a string")
    return errors


def merge_with_defaults(theme):
    """Deep merge a partial theme with DEFAULT_THEME, filling missing values."""
    return _deep_merge(DEFAULT_THEME, theme)


def _deep_merge(base, override):
    """Recursively merge override into base, returning a new dict."""
    result = {}
    for key in base:
        if key in override:
            if isinstance(base[key], dict) and isinstance(override[key], dict):
                result[key] = _deep_merge(base[key], override[key])
            else:
                result[key] = override[key]
        else:
            result[key] = base[key]
    # Include keys in override not in base
    for key in override:
        if key not in base:
            result[key] = override[key]
    return result
