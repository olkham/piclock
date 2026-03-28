"""Convert legacy theme JSON (v1 clock themes and dial themes) to face format.

This allows all existing themes to be used with the new element-based
renderer without modification. The original theme files are not modified.
"""

from src.faces.elements import ROMAN_LABELS, ARABIC_LABELS


def convert_clock_theme(theme):
    """Convert a legacy clock theme dict to a face dict.

    Maps all sections (background, markers, hands, center_dot, clock_text,
    date_display, alarm_indicators, agenda) to face elements.
    """
    name = theme.get("name", "Converted Theme")
    elements = []

    # --- Background ---
    bg = theme.get("background", {})
    elements.append({
        "id": "background",
        "type": "background",
        "properties": {
            "style": bg.get("type", "solid"),
            "color": bg.get("color", "#1a1a2e"),
            "colors": bg.get("colors", ["#1a1a2e", "#16213e"]),
            "gradient_type": bg.get("gradient_type", "radial"),
            "gradient_angle": bg.get("gradient_angle", 0),
            "gradient_center_x": bg.get("gradient_center_x", 0.5),
            "gradient_center_y": bg.get("gradient_center_y", 0.5),
            "gradient_radius": bg.get("gradient_radius", 1.0),
            "color_stops": bg.get("color_stops", []),
            "image": bg.get("image", ""),
            "image_opacity": bg.get("image_opacity", 100),
            "color_opacity": bg.get("color_opacity", 100),
        },
    })

    # --- Agenda overlay ---
    agenda_cfg = theme.get("agenda", {})
    if agenda_cfg.get("enabled", False):
        elements.append({
            "id": "agenda",
            "type": "agenda",
            "properties": {
                "min_radius": agenda_cfg.get("min_radius", 45),
                "max_radius": agenda_cfg.get("max_radius", 65),
                "opacity": agenda_cfg.get("opacity", 30),
                "show_current_event": agenda_cfg.get("show_current_event", True),
                "font_size": agenda_cfg.get("font_size", 0),
                "offset_y": agenda_cfg.get("offset_y", 0),
            },
            "bindings": {"events": {"source": "agenda.events"}},
        })

    # --- Markers ---
    markers = theme.get("markers", {})

    # Minute markers
    if markers.get("show_minutes", True):
        minute_style = markers.get("minute_style", "line")
        if minute_style == "dot":
            elements.append({
                "id": "minute_dots",
                "type": "radial_dots",
                "properties": {
                    "count": 60,
                    "skip_every": 5,
                    "radius": markers.get("minute_marker_radius", 95),
                    "dot_radius": markers.get("minute_dot_radius", 2),
                    "color": markers.get("minute_color", "#444444"),
                    "shadow": markers.get("minute_shadow", False),
                },
            })
        else:
            inner_pct = markers.get("minute_marker_inner_radius")
            if inner_pct is None:
                outer_pct = markers.get("minute_marker_radius", 95)
                length = markers.get("minute_length", 0.02)
                inner_pct = outer_pct - length * 100
            elements.append({
                "id": "minute_ticks",
                "type": "radial_lines",
                "properties": {
                    "count": 60,
                    "skip_every": 5,
                    "inner_radius": inner_pct,
                    "outer_radius": markers.get("minute_marker_radius", 95),
                    "width": markers.get("minute_width", 1.5),
                    "color": markers.get("minute_color", "#555555"),
                    "shadow": markers.get("minute_shadow", False),
                },
            })

    # Hour markers
    hour_style = markers.get("hour_style", "line")
    if hour_style == "dot":
        elements.append({
            "id": "hour_dots",
            "type": "radial_dots",
            "properties": {
                "count": 12,
                "skip_every": 0,
                "radius": markers.get("hour_marker_radius", 95),
                "dot_radius": markers.get("dot_radius", 5),
                "color": markers.get("hour_color", "#ffffff"),
                "shadow": markers.get("hour_shadow", False),
            },
        })
    elif hour_style == "line" or (hour_style == "none" and markers.get("hour_text_style", "none") == "none"):
        # Only emit line markers for explicit "line" style
        if hour_style == "line":
            inner_pct = markers.get("hour_marker_inner_radius")
            if inner_pct is None:
                outer_pct = markers.get("hour_marker_radius", 95)
                length = markers.get("hour_length", 0.06)
                inner_pct = outer_pct - length * 100
            elements.append({
                "id": "hour_ticks",
                "type": "radial_lines",
                "properties": {
                    "count": 12,
                    "skip_every": 0,
                    "inner_radius": inner_pct,
                    "outer_radius": markers.get("hour_marker_radius", 95),
                    "width": markers.get("hour_width", 3),
                    "color": markers.get("hour_color", "#ffffff"),
                    "shadow": markers.get("hour_shadow", False),
                },
            })

    # Hour text
    text_style = markers.get("hour_text_style", "none")
    # Backward compat: if hour_style is a text variant
    if text_style == "none" and hour_style in ("roman", "arabic", "custom"):
        text_style = hour_style

    if text_style in ("roman", "arabic", "custom"):
        if text_style == "roman":
            labels = list(ROMAN_LABELS)
            font_fam = "serif"
        elif text_style == "custom":
            labels = markers.get("hour_labels", list(ARABIC_LABELS))
            font_fam = "sans-serif"
        else:
            labels = list(ARABIC_LABELS)
            font_fam = "sans-serif"

        elements.append({
            "id": "hour_labels",
            "type": "radial_text",
            "properties": {
                "count": 12,
                "labels": labels,
                "style": text_style,
                "radius": markers.get("hour_radius", 82),
                "color": markers.get("hour_color", "#e0e0e0"),
                "font_size": markers.get("font_size", 0),
                "font_family": font_fam,
            },
        })

    # --- Alarm indicators ---
    indicator_cfg = theme.get("alarm_indicators", {})
    if indicator_cfg.get("visible", True):
        elements.append({
            "id": "alarm_indicators",
            "type": "alarm_indicators",
            "properties": {
                "color": indicator_cfg.get("color", "#ffaa00"),
                "size": indicator_cfg.get("size", 4),
                "radius": 70,
            },
            "bindings": {"items": {"source": "alarm.list"}},
        })

    # --- Hands ---
    hands = theme.get("hands", {})

    # Hour hand
    hour_cfg = hands.get("hour", {})
    h_start, h_end = _get_start_end(hour_cfg, -8, 45)
    elements.append({
        "id": "hour_hand",
        "type": "hand",
        "properties": {
            "style": hour_cfg.get("style", "tapered"),
            "color": hour_cfg.get("color", "#ffffff"),
            "width": hour_cfg.get("width", 14),
            "start": h_start,
            "end": h_end,
            "shadow": hour_cfg.get("shadow", True),
            "glow": hour_cfg.get("glow", False),
            "glow_color": hour_cfg.get("glow_color", "#ffffff"),
            "image": hour_cfg.get("image", ""),
        },
        "bindings": {"angle": {"source": "time.hour_angle"}},
    })

    # Minute hand
    min_cfg = hands.get("minute", {})
    m_start, m_end = _get_start_end(min_cfg, -10, 65)
    elements.append({
        "id": "minute_hand",
        "type": "hand",
        "properties": {
            "style": min_cfg.get("style", "tapered"),
            "color": min_cfg.get("color", "#ffffff"),
            "width": min_cfg.get("width", 10),
            "start": m_start,
            "end": m_end,
            "shadow": min_cfg.get("shadow", True),
            "glow": min_cfg.get("glow", False),
            "glow_color": min_cfg.get("glow_color", "#ffffff"),
            "image": min_cfg.get("image", ""),
        },
        "bindings": {"angle": {"source": "time.minute_angle"}},
    })

    # Second hand
    sec_cfg = hands.get("second", {})
    if sec_cfg.get("visible", True):
        s_start, s_end = _get_start_end(sec_cfg, -15, 72)
        elements.append({
            "id": "second_hand",
            "type": "hand",
            "properties": {
                "style": "second" if not sec_cfg.get("image") else "image",
                "color": sec_cfg.get("color", "#ff4444"),
                "width": 2,
                "start": s_start,
                "end": s_end,
                "shadow": sec_cfg.get("shadow", True),
                "glow": sec_cfg.get("glow", False),
                "glow_color": sec_cfg.get("glow_color", "#ff4444"),
                "image": sec_cfg.get("image", ""),
                "counterweight": sec_cfg.get("counterweight", True),
                "counterweight_radius": sec_cfg.get("counterweight_radius", 4),
                "smooth": sec_cfg.get("smooth", False),
            },
            "bindings": {"angle": {"source": "time.second_angle"}},
        })

    # --- Center dot ---
    dot = theme.get("center_dot", {})
    if dot.get("visible", True):
        elements.append({
            "id": "center_dot",
            "type": "circle",
            "properties": {
                "radius": dot.get("radius", 6),
                "color": dot.get("color", "#ffffff"),
                "filled": True,
                "opacity": 100,
            },
            "position": [0, 0],
        })

    # --- Clock text ---
    clock_text = theme.get("clock_text", {})
    if clock_text.get("visible", False):
        fmt = clock_text.get("format", "12h")
        source = "time.formatted_12h" if fmt == "12h" else "time.formatted_24h"
        elements.append({
            "id": "digital_time",
            "type": "text",
            "properties": {
                "color": clock_text.get("color", "#ffffff"),
                "font_size": clock_text.get("font_size", 0),
                "align": "center",
                "font_family": "sans-serif",
            },
            "position": [0, clock_text.get("offset_y", 25)],
            "bindings": {"text": {"source": source}},
        })

    # --- Date display ---
    date_cfg = theme.get("date_display", {})
    if date_cfg.get("visible", False):
        date_source = "date.full" if date_cfg.get("show_day_of_week", True) else "date.formatted"
        elements.append({
            "id": "date_display",
            "type": "text",
            "properties": {
                "color": date_cfg.get("color", "#ffffff"),
                "font_size": date_cfg.get("font_size", 0),
                "align": "center",
                "font_family": "sans-serif",
            },
            "position": [0, date_cfg.get("offset_y", 35)],
            "bindings": {"text": {"source": date_source}},
        })

    return {
        "name": name,
        "version": 2,
        "converted_from": "clock_theme",
        "elements": elements,
    }


def convert_dial_theme(dial_theme):
    """Convert a legacy dial theme dict to a face dict.

    Maps background + dial section to face elements: background, track arc,
    ticks, progress arc, hand, center dot, label text, value text.
    """
    name = dial_theme.get("name", "Converted Dial")
    elements = []
    dial = dial_theme.get("dial", {})

    # --- Background ---
    bg = dial_theme.get("background", {})
    elements.append({
        "id": "background",
        "type": "background",
        "properties": {
            "style": bg.get("type", "solid"),
            "color": bg.get("color", "#0f172a"),
            "colors": bg.get("colors", ["#0f172a", "#1e293b"]),
            "gradient_type": bg.get("gradient_type", "radial"),
            "gradient_angle": bg.get("gradient_angle", 0),
            "gradient_center_x": bg.get("gradient_center_x", 0.5),
            "gradient_center_y": bg.get("gradient_center_y", 0.5),
            "gradient_radius": bg.get("gradient_radius", 1.0),
            "color_stops": bg.get("color_stops", []),
            "image": bg.get("image", ""),
            "image_opacity": bg.get("image_opacity", 100),
            "color_opacity": bg.get("color_opacity", 100),
        },
    })

    # Common arc config
    arc_props = {}
    if dial.get("arc_symmetric", False):
        arc_props["arc_symmetric"] = True
        arc_props["arc_center"] = dial.get("arc_center", 0)
        arc_props["arc_extent"] = dial.get("arc_extent", 135)
    else:
        arc_props["arc_start"] = dial.get("arc_start", 135)
        arc_props["arc_end"] = dial.get("arc_end", 405)

    # --- Track arc ---
    elements.append({
        "id": "track",
        "type": "arc",
        "properties": {
            **arc_props,
            "radius": dial.get("radius", 85),
            "thickness": dial.get("thickness", 14),
            "color": dial.get("track_color", "#ffffff"),
            "opacity": dial.get("track_opacity", 12),
            "cap_style": dial.get("cap_style", "round"),
            "style": "solid",
            "track_style": dial.get("track_style", "solid"),
            "track_gradient_start": dial.get("track_gradient_start", "#22c55e"),
            "track_gradient_end": dial.get("track_gradient_end", "#ef4444"),
            "track_zones": dial.get("track_zones", []),
        },
    })

    # --- Tick marks ---
    if dial.get("tick_marks", False):
        elements.append({
            "id": "ticks",
            "type": "arc_ticks",
            "properties": {
                **arc_props,
                "major_count": dial.get("major_tick_count", 10),
                "major_inner_radius": dial.get("major_tick_inner_radius", 72),
                "major_outer_radius": dial.get("major_tick_outer_radius", 77),
                "major_width": dial.get("major_tick_width", 2),
                "major_color": dial.get("major_tick_color", "#888888"),
                "minor_ticks": dial.get("minor_ticks", False),
                "minor_count": dial.get("minor_tick_count", 4),
                "minor_inner_radius": dial.get("minor_tick_inner_radius", 74),
                "minor_outer_radius": dial.get("minor_tick_outer_radius", 77),
                "minor_width": dial.get("minor_tick_width", 1),
                "minor_color": dial.get("minor_tick_color", "#555555"),
            },
        })

    # --- Progress arc ---
    if dial.get("show_progress", True):
        elements.append({
            "id": "progress",
            "type": "arc",
            "properties": {
                **arc_props,
                "radius": dial.get("radius", 85),
                "thickness": dial.get("thickness", 14),
                "color": dial.get("progress_color", "#00D68F"),
                "opacity": dial.get("progress_opacity", 100),
                "cap_style": dial.get("cap_style", "round"),
                "style": dial.get("style", "solid"),
                "dash_length": dial.get("dash_length", 8),
                "dash_gap": dial.get("dash_gap", 4),
                "gradient_end_color": dial.get("gradient_end_color", "#ff4444"),
            },
            "bindings": {"progress": {"source": "dial.progress"}},
        })

    # --- Label text ---
    if dial.get("show_text", True):
        elements.append({
            "id": "label",
            "type": "text",
            "properties": {
                "color": dial.get("label_color", "#888888"),
                "font_size": dial.get("label_font_size", 0),
                "align": "center",
                "font_family": "sans-serif",
            },
            "position": [0, -(dial.get("label_offset_y", 8))],
            "bindings": {"text": {"source": "dial.label"}},
        })

    # --- Value text ---
    if dial.get("show_value", False):
        elements.append({
            "id": "value",
            "type": "text",
            "properties": {
                "color": dial.get("value_color", "#ffffff"),
                "font_size": dial.get("value_font_size", 0),
                "align": "center",
                "suffix": dial.get("value_suffix", ""),
                "font_family": "sans-serif",
            },
            "position": [0, dial.get("value_offset_y", 12)],
            "bindings": {"text": {"source": "dial.value"}},
        })

    # --- Min/Max labels ---
    if dial.get("show_min_max", False):
        # These are positional text at arc endpoints — simplified as static text
        # For full fidelity, the renderer handles min/max specially
        pass

    # --- Hand ---
    if dial.get("show_hand", False):
        hand_binding = {
            "source": "dial.progress",
            "transform": "arc_angle",
        }
        hand_binding.update(arc_props)

        elements.append({
            "id": "dial_hand",
            "type": "hand",
            "properties": {
                "style": dial.get("hand_style", "triangle"),
                "color": dial.get("hand_color", "#ffffff"),
                "width": dial.get("hand_width", 4),
                "start": -(dial.get("hand_tail", 10)),
                "end": dial.get("hand_length", 80),
                "shadow": False,
            },
            "bindings": {"angle": hand_binding},
        })

        # Center dot
        if dial.get("hand_center_dot", True):
            elements.append({
                "id": "hand_center_dot",
                "type": "circle",
                "properties": {
                    "radius": dial.get("hand_center_dot_radius", 4),
                    "color": dial.get("hand_center_dot_color", "#333333"),
                    "filled": True,
                    "opacity": 100,
                },
                "position": [0, 0],
            })

    return {
        "name": name,
        "version": 2,
        "converted_from": "dial_theme",
        "elements": elements,
    }


def _get_start_end(cfg, default_start, default_end):
    """Get start/end from config, with fallback to legacy length/tail."""
    if "start" in cfg and "end" in cfg:
        return cfg["start"], cfg["end"]
    length = cfg.get("length", default_end / 100)
    tail = cfg.get("tail", abs(default_start) / 100)
    return -tail * 100, length * 100
