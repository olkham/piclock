import math
import os
import sys
import cairo

try:
    from PIL import Image, ImageDraw, ImageFont
    _HAS_PILLOW = True
except ImportError:
    _HAS_PILLOW = False

_SERIF_FONT = "Times New Roman" if sys.platform == "win32" else "serif"
_SANS_FONT = "Arial" if sys.platform == "win32" else "sans-serif"


def _has_emoji(text):
    """Check if text contains characters outside basic Latin that Cairo can't render."""
    for ch in text:
        cp = ord(ch)
        if cp > 0x2600:
            return True
    return False


def _get_emoji_font(size):
    """Get a font that supports emoji rendering."""
    candidates = []
    if sys.platform == "win32":
        candidates = ["seguiemj.ttf", "C:\\Windows\\Fonts\\seguiemj.ttf"]
    else:
        candidates = [
            "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
            "/usr/share/fonts/noto/NotoColorEmoji.ttf",
            "/usr/share/fonts/google-noto-emoji/NotoColorEmoji.ttf",
            "/usr/share/fonts/truetype/ancient-scripts/Symbola_hint.ttf",
        ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, int(size))
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def draw_background(ctx, size, theme):
    """Draw the clock face background."""
    bg = theme.get("background", {})
    bg_type = bg.get("type", "solid")
    center = size / 2
    radius = size / 2

    if bg_type == "gradient":
        grad_type = bg.get("gradient_type", "radial")
        colors = bg.get("colors", ["#1a1a2e", "#16213e"])
        color_stops = bg.get("color_stops", [])

        if grad_type == "linear":
            angle_deg = bg.get("gradient_angle", 0)
            angle = math.radians(angle_deg - 90)
            dx = math.cos(angle) * radius
            dy = math.sin(angle) * radius
            pattern = cairo.LinearGradient(
                center - dx, center - dy,
                center + dx, center + dy,
            )
        else:
            cx = bg.get("gradient_center_x", 0.5) * size
            cy = bg.get("gradient_center_y", 0.5) * size
            gr = bg.get("gradient_radius", 1.0) * radius
            pattern = cairo.RadialGradient(cx, cy, 0, cx, cy, gr)

        if color_stops:
            for stop in color_stops:
                r, g, b = _hex_to_rgb(stop.get("color", "#000000"))
                pattern.add_color_stop_rgb(stop.get("position", 0), r, g, b)
        else:
            for i, color_hex in enumerate(colors):
                r, g, b = _hex_to_rgb(color_hex)
                pattern.add_color_stop_rgb(i / max(len(colors) - 1, 1), r, g, b)

        ctx.set_source(pattern)
    elif bg_type == "image":
        image_path = bg.get("image", "")
        if image_path and os.path.isfile(image_path):
            try:
                img = cairo.ImageSurface.create_from_png(image_path)
                img_w, img_h = img.get_width(), img.get_height()
                scale = max(size / img_w, size / img_h)
                ctx.save()
                ctx.scale(scale, scale)
                ctx.set_source_surface(img, 0, 0)
                ctx.paint()
                ctx.restore()
                return
            except Exception:
                pass
        color = bg.get("color", "#1a1a2e")
        r, g, b = _hex_to_rgb(color)
        ctx.set_source_rgb(r, g, b)
    else:
        color = bg.get("color", "#1a1a2e")
        r, g, b = _hex_to_rgb(color)
        ctx.set_source_rgb(r, g, b)

    ctx.rectangle(0, 0, size, size)
    ctx.fill()


def draw_markers(ctx, size, theme):
    """Draw hour and minute markers on the clock face."""
    markers = theme.get("markers", {})
    center = size / 2
    radius = size / 2

    # Minute markers
    if markers.get("show_minutes", True):
        minute_style = markers.get("minute_style", "line")
        if minute_style == "dot":
            _draw_minute_dots(ctx, center, radius, markers)
        else:
            _draw_minute_markers(ctx, center, radius, markers)

    # Hour markers
    style = markers.get("hour_style", "line")
    if style == "roman":
        _draw_roman_numerals(ctx, center, radius, markers)
    elif style == "arabic":
        _draw_arabic_numerals(ctx, center, radius, markers)
    elif style == "custom":
        _draw_custom_labels(ctx, center, radius, markers)
    elif style == "dot":
        _draw_dot_markers(ctx, center, radius, markers)
    elif style == "none":
        pass
    else:
        _draw_line_markers(ctx, center, radius, markers)


def draw_alarm_indicators(ctx, size, theme, alarms):
    """Draw small indicators on the clock face for set alarms."""
    indicator_cfg = theme.get("alarm_indicators", {})
    if not indicator_cfg.get("visible", True) or not alarms:
        return

    center = size / 2
    radius = size / 2
    color = indicator_cfg.get("color", "#ffaa00")
    dot_size = indicator_cfg.get("size", 4.0)
    r, g, b = _hex_to_rgb(color)

    for alarm in alarms:
        time_str = alarm.get("time", "")
        if not time_str or not alarm.get("enabled", True):
            continue
        try:
            parts = time_str.split(":")
            hour = int(parts[0]) % 12
            minute = int(parts[1])
        except (ValueError, IndexError):
            continue

        angle = math.radians((hour + minute / 60) * 30 - 90)
        x = center + radius * 0.70 * math.cos(angle)
        y = center + radius * 0.70 * math.sin(angle)

        ctx.set_source_rgb(r, g, b)
        ctx.arc(x, y, dot_size, 0, 2 * math.pi)
        ctx.fill()

        # Small triangle pointer
        ctx.new_path()
        tip_x = center + radius * 0.74 * math.cos(angle)
        tip_y = center + radius * 0.74 * math.sin(angle)
        perp = angle + math.pi / 2
        base_off = dot_size * 0.6
        ctx.move_to(tip_x, tip_y)
        ctx.line_to(x + base_off * math.cos(perp), y + base_off * math.sin(perp))
        ctx.line_to(x - base_off * math.cos(perp), y - base_off * math.sin(perp))
        ctx.close_path()
        ctx.fill()


def _draw_minute_markers(ctx, center, radius, markers):
    color = markers.get("minute_color", "#444444")
    r, g, b = _hex_to_rgb(color)
    width = markers.get("minute_width", 1.5)
    length = markers.get("minute_length", 0.02)
    shadow = markers.get("minute_shadow", False)

    ctx.set_line_cap(cairo.LINE_CAP_ROUND)

    for i in range(60):
        if i % 5 == 0:
            continue
        angle = math.radians(i * 6 - 90)
        inner = radius * (1 - length)
        outer = radius * 0.95
        x1, y1 = center + inner * math.cos(angle), center + inner * math.sin(angle)
        x2, y2 = center + outer * math.cos(angle), center + outer * math.sin(angle)

        if shadow:
            ctx.set_source_rgba(0, 0, 0, 0.3)
            ctx.set_line_width(width)
            ctx.move_to(x1 + 1, y1 + 1)
            ctx.line_to(x2 + 1, y2 + 1)
            ctx.stroke()

        ctx.set_source_rgb(r, g, b)
        ctx.set_line_width(width)
        ctx.move_to(x1, y1)
        ctx.line_to(x2, y2)
        ctx.stroke()


def _draw_minute_dots(ctx, center, radius, markers):
    color = markers.get("minute_color", "#444444")
    r, g, b = _hex_to_rgb(color)
    dot_r = markers.get("minute_dot_radius", 2.0)
    shadow = markers.get("minute_shadow", False)

    for i in range(60):
        if i % 5 == 0:
            continue
        angle = math.radians(i * 6 - 90)
        x = center + radius * 0.93 * math.cos(angle)
        y = center + radius * 0.93 * math.sin(angle)

        if shadow:
            ctx.set_source_rgba(0, 0, 0, 0.3)
            ctx.arc(x + 1, y + 1, dot_r, 0, 2 * math.pi)
            ctx.fill()

        ctx.set_source_rgb(r, g, b)
        ctx.arc(x, y, dot_r, 0, 2 * math.pi)
        ctx.fill()


def _draw_line_markers(ctx, center, radius, markers):
    color = markers.get("hour_color", "#ffffff")
    r, g, b = _hex_to_rgb(color)
    width = markers.get("hour_width", 3.0)
    length = markers.get("hour_length", 0.06)
    shadow = markers.get("hour_shadow", False)

    ctx.set_line_cap(cairo.LINE_CAP_ROUND)

    for i in range(12):
        angle = math.radians(i * 30 - 90)
        inner = radius * (1 - length)
        outer = radius * 0.95
        x1, y1 = center + inner * math.cos(angle), center + inner * math.sin(angle)
        x2, y2 = center + outer * math.cos(angle), center + outer * math.sin(angle)

        if shadow:
            ctx.set_source_rgba(0, 0, 0, 0.3)
            ctx.set_line_width(width)
            ctx.move_to(x1 + 2, y1 + 2)
            ctx.line_to(x2 + 2, y2 + 2)
            ctx.stroke()

        ctx.set_source_rgb(r, g, b)
        ctx.set_line_width(width)
        ctx.move_to(x1, y1)
        ctx.line_to(x2, y2)
        ctx.stroke()


def _draw_dot_markers(ctx, center, radius, markers):
    color = markers.get("hour_color", "#ffffff")
    r, g, b = _hex_to_rgb(color)
    dot_radius = markers.get("dot_radius", 5.0)
    shadow = markers.get("hour_shadow", False)

    for i in range(12):
        angle = math.radians(i * 30 - 90)
        x = center + radius * 0.88 * math.cos(angle)
        y = center + radius * 0.88 * math.sin(angle)

        if shadow:
            ctx.set_source_rgba(0, 0, 0, 0.3)
            ctx.arc(x + 2, y + 2, dot_radius, 0, 2 * math.pi)
            ctx.fill()

        ctx.set_source_rgb(r, g, b)
        ctx.arc(x, y, dot_radius, 0, 2 * math.pi)
        ctx.fill()


def _draw_roman_numerals(ctx, center, radius, markers):
    numerals = ["XII", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI"]
    _draw_text_markers(ctx, center, radius, markers, numerals, _SERIF_FONT, 0.1)


def _draw_arabic_numerals(ctx, center, radius, markers):
    numerals = ["12", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"]
    _draw_text_markers(ctx, center, radius, markers, numerals, _SANS_FONT, 0.12)


def _draw_custom_labels(ctx, center, radius, markers):
    labels = markers.get("hour_labels", ["12", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"])
    if len(labels) != 12:
        labels = (labels + [""] * 12)[:12]
    _draw_text_markers(ctx, center, radius, markers, labels, _SANS_FONT, 0.1)


def _draw_text_markers(ctx, center, radius, markers, labels, font_family, default_size_ratio):
    color = markers.get("hour_color", "#ffffff")
    r, g, b = _hex_to_rgb(color)
    font_size = markers.get("font_size", 0) or radius * default_size_ratio
    shadow = markers.get("hour_shadow", False)

    # Check if any label contains emoji — use Pillow for rendering if so
    use_pillow = _HAS_PILLOW and any(_has_emoji(lbl) for lbl in labels if lbl)

    if use_pillow:
        _draw_text_markers_pillow(ctx, center, radius, labels, font_size, r, g, b, shadow)
    else:
        _draw_text_markers_cairo(ctx, center, radius, labels, font_family, font_size, r, g, b, shadow)


def _draw_text_markers_cairo(ctx, center, radius, labels, font_family, font_size, r, g, b, shadow):
    """Render text markers using Cairo's toy text API (fast, no emoji)."""
    ctx.select_font_face(font_family, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(font_size)

    for i, label in enumerate(labels):
        if not label:
            continue
        angle = math.radians(i * 30 - 90)
        x = center + radius * 0.82 * math.cos(angle)
        y = center + radius * 0.82 * math.sin(angle)
        extents = ctx.text_extents(label)

        if shadow:
            ctx.set_source_rgba(0, 0, 0, 0.3)
            ctx.move_to(x - extents.width / 2 + 2, y + extents.height / 2 + 2)
            ctx.show_text(label)

        ctx.set_source_rgb(r, g, b)
        ctx.move_to(x - extents.width / 2, y + extents.height / 2)
        ctx.show_text(label)


def _draw_text_markers_pillow(ctx, center, radius, labels, font_size, r, g, b, shadow):
    """Render text markers using Pillow (supports emoji/unicode)."""
    font = _get_emoji_font(font_size)
    color_rgba = (int(r * 255), int(g * 255), int(b * 255), 255)

    for i, label in enumerate(labels):
        if not label:
            continue
        angle = math.radians(i * 30 - 90)
        x = center + radius * 0.82 * math.cos(angle)
        y = center + radius * 0.82 * math.sin(angle)

        # Measure text
        dummy = Image.new("RGBA", (1, 1))
        draw = ImageDraw.Draw(dummy)
        bbox = draw.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pad = 4
        img_w, img_h = tw + pad * 2, th + pad * 2

        # Draw shadow
        if shadow:
            shadow_img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
            sd = ImageDraw.Draw(shadow_img)
            sd.text((pad - bbox[0] + 2, pad - bbox[1] + 2), label, fill=(0, 0, 0, 76), font=font)
            _composite_pillow_to_cairo(ctx, shadow_img, x - img_w / 2, y - img_h / 2)

        # Draw text
        text_img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
        td = ImageDraw.Draw(text_img)
        td.text((pad - bbox[0], pad - bbox[1]), label, fill=color_rgba, font=font)
        _composite_pillow_to_cairo(ctx, text_img, x - img_w / 2, y - img_h / 2)


def _composite_pillow_to_cairo(ctx, pil_img, x, y):
    """Paint a Pillow RGBA image onto a Cairo context at (x, y)."""
    # Convert Pillow RGBA to Cairo ARGB32 byte order (BGRa on little-endian)
    raw = pil_img.tobytes("raw", "BGRa")
    w, h = pil_img.size
    surface = cairo.ImageSurface.create_for_data(
        bytearray(raw), cairo.FORMAT_ARGB32, w, h, w * 4
    )
    ctx.save()
    ctx.set_source_surface(surface, x, y)
    ctx.paint()
    ctx.restore()


def draw_clock_text(ctx, size, time_info, theme):
    """Draw the digital time text on the clock face."""
    cfg = theme.get("clock_text", {})
    if not cfg.get("visible", False):
        return

    center = size / 2
    radius = size / 2

    hour = time_info["hour"]
    minute = time_info["minute"]
    fmt = cfg.get("format", "12h")
    if fmt == "12h":
        suffix = "AM" if hour < 12 else "PM"
        display_hour = hour % 12 or 12
        text = f"{display_hour}:{minute:02d} {suffix}"
    else:
        text = f"{hour:02d}:{minute:02d}"

    color = cfg.get("color", "#ffffff")
    r, g, b = _hex_to_rgb(color)
    font_size = cfg.get("font_size", 0)
    if font_size <= 0:
        font_size = radius * 0.12
    offset_y = cfg.get("offset_y", 25) / 100 * radius

    ctx.select_font_face(_SANS_FONT, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(font_size)
    extents = ctx.text_extents(text)
    x = center - extents.width / 2
    y = center + offset_y + extents.height / 2

    ctx.set_source_rgba(0, 0, 0, 0.4)
    ctx.move_to(x + 1, y + 1)
    ctx.show_text(text)

    ctx.set_source_rgb(r, g, b)
    ctx.move_to(x, y)
    ctx.show_text(text)


def draw_agenda(ctx, size, theme, agenda_events):
    """Draw agenda events as pie/donut chart slices on the clock face."""
    agenda_cfg = theme.get("agenda", {})
    if not agenda_cfg.get("enabled", False) or not agenda_events:
        return

    center = size / 2
    radius = size / 2
    min_r = agenda_cfg.get("min_radius", 0) / 100 * radius
    max_r = agenda_cfg.get("max_radius", 80) / 100 * radius
    opacity = agenda_cfg.get("opacity", 35) / 100

    if max_r <= min_r:
        return

    for ev in agenda_events:
        start_str = ev.get("start_time", "")
        end_str = ev.get("end_time", "")
        color = ev.get("color", "#4488ff")
        if not start_str or not end_str:
            continue

        try:
            sh, sm = int(start_str.split(":")[0]), int(start_str.split(":")[1])
            eh, em = int(end_str.split(":")[0]), int(end_str.split(":")[1])
        except (ValueError, IndexError):
            continue

        # Calculate duration in hours to handle crossing 12-hour boundary
        start_mins = sh * 60 + sm
        end_mins = eh * 60 + em
        if end_mins <= start_mins:
            end_mins += 24 * 60  # crosses midnight
        duration_hours = min((end_mins - start_mins) / 60, 12)  # cap at full circle

        # Map to 12-hour clock position
        start_pos = (sh % 12) + sm / 60
        start_angle = math.radians(start_pos * 30 - 90)
        end_angle = start_angle + math.radians(duration_hours * 30)

        r, g, b = _hex_to_rgb(color)
        ctx.set_source_rgba(r, g, b, opacity)

        # Draw annular sector: outer arc → inner arc (reverse) → close
        ctx.new_path()
        ctx.arc(center, center, max_r, start_angle, end_angle)
        ctx.arc_negative(center, center, min_r, end_angle, start_angle)
        ctx.close_path()
        ctx.fill()


def _hex_to_rgb(hex_color):
    """Convert hex color string to (r, g, b) floats 0-1."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))
