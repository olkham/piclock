"""Theme schema definition and validation."""
import copy

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
        "image_opacity": (int, float),  # 0-100, opacity for background image
        "color_opacity": (int, float),  # 0-100, opacity for background color/gradient
    },
    "markers": {
        "hour_style": str,       # "line", "dot", "none"
        "hour_text_style": str,  # "roman", "arabic", "custom", "none"
        "hour_labels": list,     # list of 12 strings for custom style
        "hour_color": str,
        "hour_width": (int, float),
        "hour_length": (int, float),
        "dot_radius": (int, float),
        "font_size": (int, float),
        "hour_radius": (int, float),  # % of radius for text/dot marker position
        "hour_marker_radius": (int, float),  # % of radius for outer edge of hour line/dot markers
        "hour_marker_inner_radius": (int, float),  # % of radius for inner edge of hour line markers
        "hour_shadow": bool,
        "show_minutes": bool,
        "minute_style": str,     # "line" or "dot"
        "minute_color": str,
        "minute_width": (int, float),
        "minute_length": (int, float),
        "minute_dot_radius": (int, float),
        "minute_marker_radius": (int, float),  # % of radius for outer edge of minute markers
        "minute_marker_inner_radius": (int, float),  # % of radius for inner edge of minute line markers
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
            "smooth": bool,
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
    "clock_text": {
        "visible": bool,
        "format": str,          # "12h", "24h"
        "color": str,
        "font_size": (int, float),   # 0 = auto
        "offset_y": (int, float),    # % of radius, positive = below center
    },
    "date_display": {
        "visible": bool,
        "color": str,
        "font_size": (int, float),   # 0 = auto
        "offset_y": (int, float),    # % of radius, positive = below center
        "show_day_of_week": bool,
    },
    "agenda": {
        "enabled": bool,
        "min_radius": (int, float),  # % of clock radius for inner edge
        "max_radius": (int, float),  # % of clock radius for outer edge
        "opacity": (int, float),     # 0-100, fill opacity
        "show_current_event": bool,  # show active event title on clock face
    },
    "dial": {
        "arc_start": (int, float),       # degrees, 0=top, clockwise
        "arc_end": (int, float),         # degrees, can exceed 360 for wrap
        "thickness": (int, float),       # % of radius
        "track_color": str,
        "track_opacity": (int, float),   # 0-100
        "progress_color": str,
        "progress_opacity": (int, float),
        "cap_style": str,               # "round", "butt", "square"
        "style": str,                   # "solid", "dashed", "gradient"
        "dash_length": (int, float),
        "dash_gap": (int, float),
        "gradient_end_color": str,
        "radius": (int, float),          # % of half-display
        "show_text": bool,
        "text_color": str,
        "text_font_size": (int, float),  # 0 = auto (11% of display)
        "text_offset_y": (int, float),   # % of radius
        "label_color": str,
        "label_font_size": (int, float), # 0 = auto (4.5% of display)
        "label_offset_y": (int, float),  # % of radius
        "show_progress": bool,           # hide progress arc (hand-only mode)
        "tick_marks": bool,
        "major_tick_count": int,
        "major_tick_inner_radius": (int, float),  # % of half-display
        "major_tick_outer_radius": (int, float),
        "major_tick_width": (int, float),
        "major_tick_color": str,
        "minor_ticks": bool,
        "minor_tick_count": int,             # per major interval
        "minor_tick_inner_radius": (int, float),
        "minor_tick_outer_radius": (int, float),
        "minor_tick_width": (int, float),
        "minor_tick_color": str,
        "show_hand": bool,
        "hand_color": str,
        "hand_width": (int, float),          # % of radius (base width)
        "hand_length": (int, float),         # % of half-display (tip)
        "hand_tail": (int, float),           # % of half-display (tail past centre)
        "hand_style": str,                   # "line", "triangle", "needle"
        "hand_center_dot": bool,
        "hand_center_dot_radius": (int, float),  # % of half-display
        "hand_center_dot_color": str,
        "show_value": bool,
        "value_color": str,
        "value_font_size": (int, float),     # 0 = auto (7% of display)
        "value_offset_y": (int, float),      # % of radius
        "value_suffix": str,                 # e.g. "°F", "%"
        "show_min_max": bool,
        "min_max_color": str,
        "min_max_font_size": (int, float),   # 0 = auto (3% of display)
        "track_style": str,                  # "solid", "gradient", "zones"
        "track_gradient_start": str,
        "track_gradient_end": str,
        "track_zones": list,                 # [{"from": 0, "to": 33, "color": "#hex"}, ...]
        "animate": bool,
        "animation_duration": (int, float),  # seconds
        "animation_curve": str,          # "ease_out", "ease_in_out", "linear"
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
        "image_opacity": 100,    # 0-100, opacity for background image
        "color_opacity": 100,    # 0-100, opacity for background color/gradient
    },
    "markers": {
        "hour_style": "none",
        "hour_text_style": "roman",
        "hour_labels": ["XII", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI"],
        "hour_color": "#e0e0e0",
        "hour_width": 3.0,
        "hour_length": 0.06,
        "dot_radius": 5.0,
        "font_size": 0,  # 0 = auto-calculate
        "hour_radius": 82,  # % of radius for text/dot marker position
        "hour_marker_radius": 95,  # % of radius for outer edge of hour line/dot markers
        "hour_marker_inner_radius": 89,  # % of radius for inner edge of hour line markers
        "hour_shadow": False,
        "show_minutes": True,
        "minute_style": "line",
        "minute_color": "#555555",
        "minute_width": 1.5,
        "minute_length": 0.02,
        "minute_dot_radius": 2.0,
        "minute_marker_radius": 95,  # % of radius for outer edge of minute markers
        "minute_marker_inner_radius": 93,  # % of radius for inner edge of minute line markers
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
            "smooth": False,
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
    "clock_text": {
        "visible": False,
        "format": "12h",
        "color": "#ffffff",
        "font_size": 0,
        "offset_y": 25,
    },
    "date_display": {
        "visible": False,
        "color": "#ffffff",
        "font_size": 0,
        "offset_y": -15,
        "show_day_of_week": True,
    },
    "agenda": {
        "enabled": False,
        "min_radius": 0,
        "max_radius": 80,
        "opacity": 35,
        "show_current_event": False,
    },
    "dial": {
        "arc_start": 135,
        "arc_end": 405,
        "arc_symmetric": False,
        "arc_center": 0,
        "arc_extent": 135,
        "thickness": 14,
        "track_color": "#ffffff",
        "track_opacity": 12,
        "progress_color": "#00D68F",
        "progress_opacity": 100,
        "cap_style": "round",
        "style": "solid",
        "dash_length": 8,
        "dash_gap": 4,
        "gradient_end_color": "#ff4444",
        "radius": 85,
        "show_text": True,
        "text_color": "#ffffff",
        "text_font_size": 0,
        "text_offset_y": -2,
        "label_color": "#888888",
        "label_font_size": 0,
        "label_offset_y": 8,
        "show_progress": True,
        "tick_marks": False,
        "major_tick_count": 10,
        "major_tick_inner_radius": 72,
        "major_tick_outer_radius": 78,
        "major_tick_width": 2,
        "major_tick_color": "#888888",
        "minor_ticks": False,
        "minor_tick_count": 4,
        "minor_tick_inner_radius": 73,
        "minor_tick_outer_radius": 77,
        "minor_tick_width": 1,
        "minor_tick_color": "#555555",
        "show_hand": False,
        "hand_color": "#ffffff",
        "hand_width": 3,
        "hand_length": 80,
        "hand_tail": 10,
        "hand_style": "triangle",
        "hand_center_dot": True,
        "hand_center_dot_radius": 4,
        "hand_center_dot_color": "#333333",
        "show_value": False,
        "value_color": "#ffffff",
        "value_font_size": 0,
        "value_offset_y": 12,
        "value_suffix": "",
        "show_min_max": False,
        "min_max_color": "#666666",
        "min_max_font_size": 0,
        "track_style": "solid",
        "track_gradient_start": "#22c55e",
        "track_gradient_end": "#ef4444",
        "track_zones": [
            {"from": 0, "to": 33, "color": "#22c55e"},
            {"from": 33, "to": 66, "color": "#f59e0b"},
            {"from": 66, "to": 100, "color": "#ef4444"},
        ],
        "animate": True,
        "animation_duration": 0.5,
        "animation_curve": "ease_out",
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


# Reuse the same validator for dial themes
validate_dial_theme = validate_theme


def merge_with_defaults(theme):
    """Deep merge a partial theme with DEFAULT_THEME, filling missing values."""
    return _deep_merge(DEFAULT_THEME, theme)


def merge_dial_theme_with_defaults(dial_theme):
    """Deep merge a partial dial theme with DEFAULT_DIAL_THEME."""
    return _deep_merge(DEFAULT_DIAL_THEME, dial_theme)


# ---------------------------------------------------------------------------
# Standalone dial theme — independent of clock themes
# ---------------------------------------------------------------------------

DEFAULT_DIAL_THEME = {
    "name": "Default Dial",
    "background": {
        "type": "solid",
        "color": "#0f172a",
        "colors": ["#0f172a", "#1e293b"],
        "gradient_type": "radial",
        "gradient_angle": 0,
        "gradient_center_x": 0.5,
        "gradient_center_y": 0.5,
        "gradient_radius": 1.0,
        "color_stops": [],
        "image": "",
        "image_opacity": 100,
        "color_opacity": 100,
    },
    "dial": copy.deepcopy(DEFAULT_THEME["dial"]),
}


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
