"""Element type definitions, defaults, and property schemas for face elements."""

# All element types and their default properties.
# Properties use % of radius unless otherwise noted.
# Positions are (x%, y%) from center where positive y = below center.

ELEMENT_TYPES = {
    "background",
    "circle",
    "arc",
    "hand",
    "radial_lines",
    "radial_dots",
    "radial_text",
    "text",
    "alarm_indicators",
    "agenda",
    "arc_ticks",
}

# Available data sources that elements can bind to
DATA_SOURCES = {
    # Clock time (angles in degrees, 0=top clockwise)
    "time.hour_angle",
    "time.minute_angle",
    "time.second_angle",
    # Formatted time strings
    "time.formatted_12h",
    "time.formatted_24h",
    # Date
    "date.formatted",
    "date.full",
    "date.day_of_week",
    # Dial mode
    "dial.progress",
    "dial.label",
    "dial.value",
    "dial.min",
    "dial.max",
    "dial.suffix",
    "dial.progress_color",
    # Timer mode
    "timer.progress",
    "timer.remaining_formatted",
    "timer.label",
    # Special (list-based, used by alarm_indicators and agenda)
    "alarm.list",
    "agenda.events",
}

# Bindable properties per element type
BINDABLE_PROPERTIES = {
    "hand": {"angle"},
    "arc": {"progress"},
    "text": {"text"},
    "alarm_indicators": {"items"},
    "agenda": {"events"},
}

# Default properties for each element type
ELEMENT_DEFAULTS = {
    "background": {
        "style": "solid",          # solid | gradient | image
        "color": "#1a1a2e",
        "colors": ["#1a1a2e", "#16213e"],
        "gradient_type": "radial",  # radial | linear
        "gradient_angle": 0,
        "gradient_center_x": 0.5,
        "gradient_center_y": 0.5,
        "gradient_radius": 1.0,
        "color_stops": [],
        "image": "",
        "image_opacity": 100,
        "color_opacity": 100,
    },
    "circle": {
        "radius": 6,              # % of face radius (or absolute if small)
        "color": "#ffffff",
        "filled": True,
        "stroke_width": 2,
        "opacity": 100,
    },
    "arc": {
        "arc_start": 135,         # degrees, 0=top clockwise
        "arc_end": 405,
        "arc_symmetric": False,
        "arc_center": 0,
        "arc_extent": 135,
        "radius": 85,             # % of half-display
        "thickness": 14,          # % of radius
        "color": "#ffffff",
        "opacity": 100,
        "cap_style": "round",     # round | butt | square
        "style": "solid",         # solid | dashed | gradient
        "dash_length": 8,
        "dash_gap": 4,
        "gradient_end_color": "#ff4444",
        # Track-specific (when not bound to progress)
        "track_style": "solid",   # solid | gradient | zones
        "track_gradient_start": "#22c55e",
        "track_gradient_end": "#ef4444",
        "track_zones": [],
    },
    "hand": {
        "style": "tapered",       # tapered | classic | second | needle | triangle | image
        "color": "#ffffff",
        "width": 10,
        "start": -10,             # % of radius (negative = behind center)
        "end": 65,                # % of radius (tip position)
        "shadow": True,
        "glow": False,
        "glow_color": "#ffffff",
        "image": "",
        "counterweight": False,
        "counterweight_radius": 4,
        "smooth": False,          # smooth sub-second motion (for second hand)
    },
    "radial_lines": {
        "count": 12,
        "skip_every": 0,          # skip every Nth (0 = no skip)
        "inner_radius": 89,       # % of radius
        "outer_radius": 95,       # % of radius
        "width": 3,
        "color": "#ffffff",
        "shadow": False,
    },
    "radial_dots": {
        "count": 12,
        "skip_every": 0,
        "radius": 95,             # % of face radius (position)
        "dot_radius": 5,          # size of each dot
        "color": "#ffffff",
        "shadow": False,
    },
    "radial_text": {
        "count": 12,
        "labels": ["12", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"],
        "style": "arabic",        # arabic | roman | custom
        "radius": 82,             # % of face radius
        "color": "#e0e0e0",
        "font_size": 0,           # 0 = auto
        "font_family": "sans-serif",
    },
    "text": {
        "color": "#ffffff",
        "font_size": 0,           # 0 = auto
        "align": "center",
        "static_text": "",        # used when no binding
        "suffix": "",
        "prefix": "",
        "font_family": "sans-serif",
    },
    "alarm_indicators": {
        "color": "#ffaa00",
        "size": 4,
        "radius": 70,             # % of face radius
    },
    "agenda": {
        "min_radius": 45,         # % of face radius
        "max_radius": 65,
        "opacity": 30,
        "show_current_event": True,
        "font_size": 0,
        "offset_y": 0,
    },
    "arc_ticks": {
        "arc_start": 135,
        "arc_end": 405,
        "arc_symmetric": False,
        "arc_center": 0,
        "arc_extent": 135,
        "major_count": 10,
        "major_inner_radius": 72,
        "major_outer_radius": 77,
        "major_width": 2,
        "major_color": "#ffffff",
        "minor_ticks": True,
        "minor_count": 4,         # per major interval
        "minor_inner_radius": 74,
        "minor_outer_radius": 77,
        "minor_width": 1,
        "minor_color": "#666666",
    },
}

# Roman numeral labels for convenience
ROMAN_LABELS = ["XII", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI"]
ARABIC_LABELS = ["12", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"]


def make_element(element_type, element_id=None, properties=None,
                 position=None, bindings=None):
    """Create a face element dict with defaults filled in.

    Args:
        element_type: One of ELEMENT_TYPES.
        element_id: Unique string identifier (auto-generated if None).
        properties: Dict of property overrides.
        position: (x%, y%) from center, or None for centered/full-face elements.
        bindings: Dict mapping property names to data source specs.

    Returns:
        Element dict ready for inclusion in a face.
    """
    if element_type not in ELEMENT_TYPES:
        raise ValueError(f"Unknown element type: {element_type}")

    defaults = ELEMENT_DEFAULTS.get(element_type, {})
    merged = {**defaults}
    if properties:
        merged.update(properties)

    element = {
        "id": element_id or f"{element_type}_{id(merged) % 10000:04d}",
        "type": element_type,
        "properties": merged,
    }
    if position is not None:
        element["position"] = list(position)
    if bindings:
        element["bindings"] = bindings
    return element
