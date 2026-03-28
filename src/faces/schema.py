"""Face JSON schema, validation, and default face definitions."""

import copy

from src.faces.elements import (
    ELEMENT_TYPES, ELEMENT_DEFAULTS, ROMAN_LABELS, ARABIC_LABELS,
)

FACE_VERSION = 2


def _deep_merge(base, override):
    """Deep-merge override into a copy of base."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def merge_element_defaults(element):
    """Fill missing properties with defaults for the element's type."""
    etype = element.get("type", "")
    defaults = ELEMENT_DEFAULTS.get(etype, {})
    props = element.get("properties", {})
    merged_props = {**defaults, **props}
    result = dict(element)
    result["properties"] = merged_props
    return result


def merge_face_defaults(face):
    """Fill missing properties on all elements in a face with defaults."""
    result = dict(face)
    result.setdefault("name", "Untitled")
    result.setdefault("version", FACE_VERSION)
    result["elements"] = [merge_element_defaults(e) for e in face.get("elements", [])]
    return result


def validate_face(face):
    """Validate a face dict. Returns list of error strings (empty = valid)."""
    errors = []
    if not isinstance(face, dict):
        return ["Face must be a dict"]
    if "name" not in face or not face["name"]:
        errors.append("Face must have a 'name'")
    elements = face.get("elements")
    if not isinstance(elements, list):
        errors.append("Face must have an 'elements' list")
        return errors
    seen_ids = set()
    for i, el in enumerate(elements):
        if not isinstance(el, dict):
            errors.append(f"Element {i}: must be a dict")
            continue
        etype = el.get("type", "")
        if etype not in ELEMENT_TYPES:
            errors.append(f"Element {i}: unknown type '{etype}'")
        eid = el.get("id", "")
        if not eid:
            errors.append(f"Element {i}: missing 'id'")
        elif eid in seen_ids:
            errors.append(f"Element {i}: duplicate id '{eid}'")
        else:
            seen_ids.add(eid)
    return errors


# =============================================================================
# Default faces (equivalent to current Classic theme + Default Dial)
# =============================================================================

DEFAULT_CLOCK_FACE = {
    "name": "Classic Clock",
    "version": FACE_VERSION,
    "elements": [
        # Background
        {
            "id": "background",
            "type": "background",
            "properties": {
                "style": "gradient",
                "color": "#1a1a2e",
                "colors": ["#1a1a2e", "#16213e"],
                "gradient_type": "radial",
                "gradient_center_x": 0.5,
                "gradient_center_y": 0.5,
                "gradient_radius": 1.0,
                "color_stops": [],
                "image": "",
                "image_opacity": 100,
                "color_opacity": 100,
            },
        },
        # Agenda overlay
        {
            "id": "agenda",
            "type": "agenda",
            "properties": {
                "min_radius": 45,
                "max_radius": 65,
                "opacity": 30,
                "show_current_event": True,
                "font_size": 0,
                "offset_y": 0,
            },
            "bindings": {"events": {"source": "agenda.events"}},
        },
        # Minute tick marks
        {
            "id": "minute_ticks",
            "type": "radial_lines",
            "properties": {
                "count": 60,
                "skip_every": 5,
                "inner_radius": 93,
                "outer_radius": 95,
                "width": 1.5,
                "color": "#555555",
                "shadow": False,
            },
        },
        # Hour tick marks
        {
            "id": "hour_ticks",
            "type": "radial_lines",
            "properties": {
                "count": 12,
                "skip_every": 0,
                "inner_radius": 89,
                "outer_radius": 95,
                "width": 3,
                "color": "#e0e0e0",
                "shadow": False,
            },
        },
        # Hour labels (roman numerals)
        {
            "id": "hour_labels",
            "type": "radial_text",
            "properties": {
                "count": 12,
                "labels": list(ROMAN_LABELS),
                "style": "roman",
                "radius": 82,
                "color": "#e0e0e0",
                "font_size": 0,
                "font_family": "serif",
            },
        },
        # Alarm indicators
        {
            "id": "alarm_indicators",
            "type": "alarm_indicators",
            "properties": {
                "color": "#ffaa00",
                "size": 4,
                "radius": 70,
            },
            "bindings": {"items": {"source": "alarm.list"}},
        },
        # Hour hand
        {
            "id": "hour_hand",
            "type": "hand",
            "properties": {
                "style": "tapered",
                "color": "#ffffff",
                "width": 14,
                "start": -8,
                "end": 45,
                "shadow": True,
                "glow": False,
                "glow_color": "#ffffff",
                "image": "",
            },
            "bindings": {"angle": {"source": "time.hour_angle"}},
        },
        # Minute hand
        {
            "id": "minute_hand",
            "type": "hand",
            "properties": {
                "style": "tapered",
                "color": "#ffffff",
                "width": 10,
                "start": -10,
                "end": 65,
                "shadow": True,
                "glow": False,
                "glow_color": "#ffffff",
                "image": "",
            },
            "bindings": {"angle": {"source": "time.minute_angle"}},
        },
        # Second hand
        {
            "id": "second_hand",
            "type": "hand",
            "properties": {
                "style": "second",
                "color": "#ff4444",
                "width": 2,
                "start": -15,
                "end": 72,
                "shadow": True,
                "glow": False,
                "glow_color": "#ff4444",
                "counterweight": True,
                "counterweight_radius": 4,
                "smooth": True,
            },
            "bindings": {"angle": {"source": "time.second_angle"}},
        },
        # Center dot
        {
            "id": "center_dot",
            "type": "circle",
            "properties": {
                "radius": 6,
                "color": "#ffffff",
                "filled": True,
                "opacity": 100,
            },
            "position": [0, 0],
        },
        # Digital time
        {
            "id": "digital_time",
            "type": "text",
            "properties": {
                "color": "#cccccc",
                "font_size": 0,
                "align": "center",
                "suffix": "",
                "prefix": "",
                "font_family": "sans-serif",
            },
            "position": [0, 25],
            "bindings": {"text": {"source": "time.formatted_12h"}},
        },
        # Date display
        {
            "id": "date_display",
            "type": "text",
            "properties": {
                "color": "#cccccc",
                "font_size": 0,
                "align": "center",
                "suffix": "",
                "prefix": "",
                "font_family": "sans-serif",
            },
            "position": [0, 35],
            "bindings": {"text": {"source": "date.full"}},
        },
    ],
}


DEFAULT_DIAL_FACE = {
    "name": "Default Dial",
    "version": FACE_VERSION,
    "elements": [
        # Background
        {
            "id": "background",
            "type": "background",
            "properties": {
                "style": "gradient",
                "color": "#0f172a",
                "colors": ["#0f172a", "#1e293b"],
                "gradient_type": "radial",
                "gradient_center_x": 0.5,
                "gradient_center_y": 0.5,
                "gradient_radius": 1.0,
                "color_stops": [],
                "image": "",
                "image_opacity": 100,
                "color_opacity": 100,
            },
        },
        # Track arc (the background ring)
        {
            "id": "track",
            "type": "arc",
            "properties": {
                "arc_symmetric": True,
                "arc_center": 0,
                "arc_extent": 130,
                "radius": 85,
                "thickness": 14,
                "color": "#ffffff",
                "opacity": 12,
                "cap_style": "round",
                "style": "solid",
                "track_style": "solid",
            },
        },
        # Tick marks along the arc
        {
            "id": "ticks",
            "type": "arc_ticks",
            "properties": {
                "arc_symmetric": True,
                "arc_center": 0,
                "arc_extent": 130,
                "major_count": 10,
                "major_inner_radius": 72,
                "major_outer_radius": 77,
                "major_width": 2,
                "major_color": "#ffffff",
                "minor_ticks": True,
                "minor_count": 4,
                "minor_inner_radius": 74,
                "minor_outer_radius": 77,
                "minor_width": 1,
                "minor_color": "#666666",
            },
        },
        # Progress arc
        {
            "id": "progress",
            "type": "arc",
            "properties": {
                "arc_symmetric": True,
                "arc_center": 0,
                "arc_extent": 130,
                "radius": 85,
                "thickness": 14,
                "color": "#00D68F",
                "opacity": 100,
                "cap_style": "round",
                "style": "solid",
            },
            "bindings": {"progress": {"source": "dial.progress"}},
        },
        # Dial hand
        {
            "id": "dial_hand",
            "type": "hand",
            "properties": {
                "style": "triangle",
                "color": "#ffffff",
                "width": 4,
                "start": -5,
                "end": 80,
                "shadow": False,
            },
            "bindings": {
                "angle": {
                    "source": "dial.progress",
                    "transform": "arc_angle",
                    "arc_symmetric": True,
                    "arc_center": 0,
                    "arc_extent": 130,
                },
            },
        },
        # Center dot for hand
        {
            "id": "hand_center_dot",
            "type": "circle",
            "properties": {
                "radius": 4,
                "color": "#ffffff",
                "filled": True,
                "opacity": 100,
            },
            "position": [0, 0],
        },
        # Label text
        {
            "id": "label",
            "type": "text",
            "properties": {
                "color": "#94a3b8",
                "font_size": 0,
                "align": "center",
                "font_family": "sans-serif",
            },
            "position": [0, -15],
            "bindings": {"text": {"source": "dial.label"}},
        },
        # Value text
        {
            "id": "value",
            "type": "text",
            "properties": {
                "color": "#ffffff",
                "font_size": 0,
                "align": "center",
                "suffix": "%",
                "font_family": "sans-serif",
            },
            "position": [0, 15],
            "bindings": {"text": {"source": "dial.value"}},
        },
    ],
}
