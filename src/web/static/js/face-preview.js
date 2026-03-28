/**
 * Face preview — Canvas-based rendering that mirrors the Cairo face renderer.
 * Renders element-based faces in the web UI for real-time visual preview.
 *
 * Uses the same two-layer approach (static cache + dynamic per-frame).
 */

let _fpRAF = null;
let _fpStaticCache = null;
let _fpCachedJSON = '';
let _fpTimezone = null;
let _fpBgImageCache = {};
let _fpAgendaEvents = [];
let _fpAlarmData = [];

/* ── lifecycle ───────────────────────────────────────── */

function startFacePreview(canvasId, face, timezone) {
    if (_fpRAF) cancelAnimationFrame(_fpRAF);
    _fpStaticCache = null;
    _fpCachedJSON = '';
    _fpTimezone = timezone || null;

    const canvas = document.getElementById(canvasId);
    if (!canvas || !face) return;

    // DPR-aware sizing
    const dpr = window.devicePixelRatio || 1;
    const logicalSize = parseInt(canvas.style.width) || canvas.width / dpr || 360;
    if (canvas.width !== logicalSize * dpr) {
        canvas.width = logicalSize * dpr;
        canvas.height = logicalSize * dpr;
        canvas.style.width = logicalSize + 'px';
        canvas.style.height = logicalSize + 'px';
    }

    // Fetch live data for preview
    fetch('/api/agenda').then(r => r.json()).then(ev => {
        _fpAgendaEvents = ev || [];
        _fpStaticCache = null; _fpCachedJSON = '';
    }).catch(() => { _fpAgendaEvents = []; });
    fetch('/api/alarms').then(r => r.json()).then(a => {
        _fpAlarmData = a || [];
        _fpStaticCache = null; _fpCachedJSON = '';
    }).catch(() => { _fpAlarmData = []; });

    let lastSec = -1;
    function tick() {
        const now = _fpGetTime();
        const sec = now.getSeconds();
        // Redraw every second (or every frame if smooth hands exist)
        const hasSmooth = (face.elements || []).some(el =>
            el.type === 'hand' && el.properties && el.properties.smooth
        );
        if (hasSmooth || sec !== lastSec) {
            lastSec = sec;
            _fpRender(canvas, face, now);
        }
        _fpRAF = requestAnimationFrame(tick);
    }
    tick();
}

function stopFacePreview() {
    if (_fpRAF) { cancelAnimationFrame(_fpRAF); _fpRAF = null; }
}

function invalidateFacePreview() {
    _fpStaticCache = null;
    _fpCachedJSON = '';
}

/* ── time helpers ────────────────────────────────────── */

function _fpGetTime() {
    if (_fpTimezone) {
        try {
            const d = new Date();
            const parts = {};
            for (const part of ['hour', 'minute', 'second']) {
                const fmt = new Intl.DateTimeFormat('en-US', {
                    timeZone: _fpTimezone, [part]: 'numeric', hour12: false,
                });
                parts[part] = parseInt(fmt.format(d), 10);
            }
            const n = new Date(d);
            n.setHours(parts.hour, parts.minute, parts.second);
            return n;
        } catch (e) { /* fallthrough */ }
    }
    return new Date();
}

function _fpHex(hex) { return (hex && hex.startsWith('#')) ? hex : '#' + (hex || '000'); }

function _fpHexRGBA(hex, alpha) {
    hex = _fpHex(hex);
    const r = parseInt(hex.slice(1, 3), 16) || 0;
    const g = parseInt(hex.slice(3, 5), 16) || 0;
    const b = parseInt(hex.slice(5, 7), 16) || 0;
    return `rgba(${r},${g},${b},${alpha})`;
}

function _fpDeg2Rad(deg) { return (deg - 90) * Math.PI / 180; }

/* ── main render ─────────────────────────────────────── */

function _fpRender(canvas, face, now) {
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const size = canvas.width / dpr;

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const center = size / 2;
    const radius = size / 2;
    const elements = face.elements || [];

    // Build data context
    const h = now.getHours(), m = now.getMinutes(), s = now.getSeconds(), ms = now.getMilliseconds();
    const dataCtx = {
        'time.hour_angle': (h % 12 + m / 60) * 30 - 90,
        'time.minute_angle': (m + s / 60) * 6 - 90,
        'time.second_angle': (s + ms / 1000) * 6 - 90,
        'time.formatted_12h': (() => {
            const h12 = h % 12 || 12;
            return `${h12}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`;
        })(),
        'time.formatted_24h': `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`,
        'date.formatted': now.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        'date.full': now.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' }),
        'date.day_of_week': now.toLocaleDateString('en-US', { weekday: 'long' }),
        'dial.progress': 65,        // demo value for preview
        'dial.label': 'Progress',
        'dial.value': '65',
        'timer.progress': 40,
        'timer.remaining_formatted': '05:30',
        'timer.label': 'Timer',
        'alarm.list': _fpAlarmData,
        'agenda.events': _fpAgendaEvents,
    };

    // Rebuild static cache when face definition changes
    const key = JSON.stringify(face);
    if (key !== _fpCachedJSON) {
        _fpCachedJSON = key;
        _fpStaticCache = _fpBuildStatic(size, center, radius, elements, dataCtx);
    }

    ctx.clearRect(0, 0, size, size);
    ctx.drawImage(_fpStaticCache, 0, 0, size, size);

    // Draw dynamic elements (hands, bound arcs/text)
    ctx.save();
    ctx.beginPath();
    ctx.arc(center, center, radius, 0, Math.PI * 2);
    ctx.clip();

    for (const el of elements) {
        if (_fpIsDynamic(el) && !el._hidden) {
            _fpDrawElement(ctx, size, center, radius, el, dataCtx);
        }
    }
    ctx.restore();
}

/* ── static layer ────────────────────────────────────── */

function _fpBuildStatic(size, center, radius, elements, dataCtx) {
    const off = document.createElement('canvas');
    const dpr = window.devicePixelRatio || 1;
    off.width = size * dpr;
    off.height = size * dpr;
    const ctx = off.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    ctx.save();
    ctx.beginPath();
    ctx.arc(center, center, radius, 0, Math.PI * 2);
    ctx.clip();

    for (const el of elements) {
        if (!_fpIsDynamic(el) && !el._hidden) {
            _fpDrawElement(ctx, size, center, radius, el, dataCtx);
        }
    }
    ctx.restore();

    // Circle border
    ctx.beginPath();
    ctx.arc(center, center, radius - 1, 0, Math.PI * 2);
    ctx.strokeStyle = '#333';
    ctx.lineWidth = 2;
    ctx.stroke();

    return off;
}

function _fpIsDynamic(el) {
    if (el.type === 'hand') return true;
    const bindings = el.bindings || {};
    return !!(bindings.angle || bindings.progress || bindings.text);
}

/* ── element dispatcher ──────────────────────────────── */

function _fpDrawElement(ctx, size, center, radius, el, dataCtx) {
    const p = el.properties || {};
    switch (el.type) {
        case 'background':   _fpDrawBg(ctx, size, center, radius, p); break;
        case 'circle':       _fpDrawCircle(ctx, size, center, radius, el, p); break;
        case 'arc':          _fpDrawArc(ctx, size, center, radius, el, p, dataCtx); break;
        case 'hand':         _fpDrawHand(ctx, size, center, radius, el, p, dataCtx); break;
        case 'radial_lines': _fpDrawRadialLines(ctx, center, radius, p); break;
        case 'radial_dots':  _fpDrawRadialDots(ctx, center, radius, p); break;
        case 'radial_text':  _fpDrawRadialText(ctx, center, radius, p); break;
        case 'text':         _fpDrawText(ctx, size, center, radius, el, p, dataCtx); break;
        case 'alarm_indicators': _fpDrawAlarms(ctx, center, radius, el, p, dataCtx); break;
        case 'agenda':       _fpDrawAgenda(ctx, center, radius, el, p, dataCtx); break;
        case 'arc_ticks':    _fpDrawArcTicks(ctx, center, radius, p); break;
    }
}

/* ── background ──────────────────────────────────────── */

function _fpDrawBg(ctx, size, center, radius, p) {
    const opacity = (p.color_opacity != null ? p.color_opacity : 100) / 100;

    if (p.style === 'image' && p.image) {
        ctx.save();
        ctx.globalAlpha = opacity;
        ctx.fillStyle = _fpHex(p.color || '#1a1a2e');
        ctx.fillRect(0, 0, size, size);
        ctx.restore();

        const filename = p.image.replace(/\\/g, '/').split('/').pop();
        const url = '/api/uploads/' + filename;
        if (_fpBgImageCache[url] && _fpBgImageCache[url].complete) {
            const img = _fpBgImageCache[url];
            const scale = Math.max(size / img.naturalWidth, size / img.naturalHeight);
            const dx = (size - img.naturalWidth * scale) / 2;
            const dy = (size - img.naturalHeight * scale) / 2;
            ctx.save();
            ctx.globalAlpha = (p.image_opacity != null ? p.image_opacity : 100) / 100;
            ctx.translate(dx, dy);
            ctx.scale(scale, scale);
            ctx.drawImage(img, 0, 0);
            ctx.restore();
        } else if (!_fpBgImageCache[url]) {
            const img = new Image();
            img.crossOrigin = 'anonymous';
            img.onload = () => invalidateFacePreview();
            img.src = url;
            _fpBgImageCache[url] = img;
        }
        return;
    }

    if (p.style === 'gradient') {
        const colors = p.colors || [p.color || '#1a1a2e', '#16213e'];
        if (colors.length < 2) {
            ctx.save(); ctx.globalAlpha = opacity;
            ctx.fillStyle = _fpHex(colors[0] || '#1a1a2e');
            ctx.fillRect(0, 0, size, size);
            ctx.restore();
            return;
        }
        let grad;
        if (p.gradient_type === 'linear') {
            const angle = ((p.gradient_angle || 0) - 90) * Math.PI / 180;
            const dx = Math.cos(angle) * radius;
            const dy = Math.sin(angle) * radius;
            grad = ctx.createLinearGradient(center - dx, center - dy, center + dx, center + dy);
        } else {
            const cx = (p.gradient_center_x != null ? p.gradient_center_x : 0.5) * size;
            const cy = (p.gradient_center_y != null ? p.gradient_center_y : 0.5) * size;
            const gr = (p.gradient_radius != null ? p.gradient_radius : 1.0) * radius;
            grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, gr);
        }
        if (p.color_stops && p.color_stops.length > 0) {
            for (const s of p.color_stops) grad.addColorStop(s.position || 0, _fpHex(s.color));
        } else {
            colors.forEach((c, i) => grad.addColorStop(i / (colors.length - 1), _fpHex(c)));
        }
        ctx.save(); ctx.globalAlpha = opacity;
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, size, size);
        ctx.restore();
        return;
    }

    // Solid
    ctx.save();
    ctx.globalAlpha = opacity;
    ctx.fillStyle = _fpHex(p.color || '#1a1a2e');
    ctx.fillRect(0, 0, size, size);
    ctx.restore();
}

/* ── circle ──────────────────────────────────────────── */

function _fpDrawCircle(ctx, size, center, radius, el, p) {
    const pos = el.position || [0, 0];
    const cx = center + (pos[0] / 100) * radius;
    const cy = center + (pos[1] / 100) * radius;
    const scale = radius / 360;
    const r = (p.radius || 6) * scale;
    const opacity = (p.opacity != null ? p.opacity : 100) / 100;

    ctx.save();
    ctx.globalAlpha = opacity;
    if (p.filled !== false) {
        ctx.fillStyle = _fpHex(p.color || '#fff');
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.fill();
    } else {
        ctx.strokeStyle = _fpHex(p.color || '#fff');
        ctx.lineWidth = (p.stroke_width || 2) * (radius / 360);
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.stroke();
    }
    ctx.restore();
}

/* ── arc ─────────────────────────────────────────────── */

function _fpDrawArc(ctx, size, center, radius, el, p, dataCtx) {
    const bindings = el.bindings || {};
    const arcR = (p.radius || 85) / 100 * (size / 2);
    const thickness = (p.thickness || 14) / 100 * arcR;
    const opacity = (p.opacity != null ? p.opacity : 100) / 100;

    let arcStart, arcEnd;
    if (p.arc_symmetric) {
        const ac = p.arc_center || 0;
        const ae = p.arc_extent || 135;
        arcStart = ac - ae;
        arcEnd = ac + ae;
    } else {
        arcStart = p.arc_start != null ? p.arc_start : 135;
        arcEnd = p.arc_end != null ? p.arc_end : 405;
    }

    const capMap = { round: 'round', butt: 'butt', square: 'square' };
    ctx.save();
    ctx.globalAlpha = opacity;
    ctx.lineWidth = thickness;
    ctx.lineCap = capMap[p.cap_style] || 'round';

    if (bindings.progress) {
        // Dynamic progress arc
        const progress = _fpResolveBinding(bindings.progress, dataCtx);
        const pct = Math.max(0, Math.min(100, parseFloat(progress) || 0));
        const startRad = _fpDeg2Rad(arcStart);
        const endRad = _fpDeg2Rad(arcEnd);
        const sweep = endRad - startRad;
        const progressEnd = startRad + sweep * (pct / 100);

        // Track
        ctx.strokeStyle = _fpHexRGBA(p.color || '#444', 0.25);
        ctx.beginPath();
        ctx.arc(center, center, arcR, startRad, endRad);
        ctx.stroke();

        // Progress
        ctx.strokeStyle = _fpHex(p.color || '#ffffff');
        ctx.beginPath();
        ctx.arc(center, center, arcR, startRad, progressEnd);
        ctx.stroke();
    } else {
        // Static arc
        const startRad = _fpDeg2Rad(arcStart);
        const endRad = _fpDeg2Rad(arcEnd);
        ctx.strokeStyle = _fpHex(p.color || '#ffffff');
        ctx.beginPath();
        ctx.arc(center, center, arcR, startRad, endRad);
        ctx.stroke();
    }
    ctx.restore();
}

/* ── hand ────────────────────────────────────────────── */

function _fpDrawHand(ctx, size, center, radius, el, p, dataCtx) {
    const bindings = el.bindings || {};
    let angleDeg = 0;
    if (bindings.angle) {
        const resolved = _fpResolveBinding(bindings.angle, dataCtx);
        angleDeg = parseFloat(resolved) || 0;
    }

    const scale = radius / 360;
    const startPct = (p.start != null ? p.start : -10) / 100;
    const endPct = (p.end != null ? p.end : 65) / 100;
    const w = (p.width || 10) * scale;
    const color = _fpHex(p.color || '#fff');
    const style = p.style || 'tapered';
    const angle = angleDeg * Math.PI / 180;

    const tipR = radius * endPct;
    const tipX = center + tipR * Math.cos(angle);
    const tipY = center + tipR * Math.sin(angle);

    let tailX, tailY;
    if (startPct < 0) {
        const tailR = radius * Math.abs(startPct);
        tailX = center - tailR * Math.cos(angle);
        tailY = center - tailR * Math.sin(angle);
    } else {
        const startR = radius * startPct;
        tailX = center + startR * Math.cos(angle);
        tailY = center + startR * Math.sin(angle);
    }

    // Shadow
    if (p.shadow !== false) {
        ctx.save();
        ctx.translate(2, 2);
        ctx.globalAlpha = 0.3;
        ctx.fillStyle = '#000';
        ctx.strokeStyle = '#000';
        _fpStrokeHand(ctx, tipX, tipY, tailX, tailY, w, style, angle);
        ctx.restore();
    }

    // Glow
    if (p.glow) {
        ctx.save();
        ctx.shadowColor = _fpHex(p.glow_color || p.color || '#fff');
        ctx.shadowBlur = 12 * scale;
        ctx.fillStyle = color;
        ctx.strokeStyle = color;
        _fpStrokeHand(ctx, tipX, tipY, tailX, tailY, w, style, angle);
        ctx.restore();
    }

    // Main hand
    ctx.fillStyle = color;
    ctx.strokeStyle = color;
    _fpStrokeHand(ctx, tipX, tipY, tailX, tailY, w, style, angle);

    // Counterweight (for second hand style)
    if (p.counterweight && (style === 'second' || style === 'line')) {
        const cwDist = radius * 0.10;
        const cwR = radius * ((p.counterweight_radius || 4) / 100);
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(center - cwDist * Math.cos(angle), center - cwDist * Math.sin(angle), cwR, 0, Math.PI * 2);
        ctx.fill();
    }
}

function _fpStrokeHand(ctx, tipX, tipY, tailX, tailY, width, style, angle) {
    if (style === 'tapered') {
        const perp = angle + Math.PI / 2;
        const bOff = width / 2;
        const tOff = width / 6;
        ctx.beginPath();
        ctx.moveTo(tailX + bOff * Math.cos(perp), tailY + bOff * Math.sin(perp));
        ctx.lineTo(tipX + tOff * Math.cos(perp), tipY + tOff * Math.sin(perp));
        ctx.lineTo(tipX - tOff * Math.cos(perp), tipY - tOff * Math.sin(perp));
        ctx.lineTo(tailX - bOff * Math.cos(perp), tailY - bOff * Math.sin(perp));
        ctx.closePath();
        ctx.fill();
    } else if (style === 'triangle') {
        const perp = angle + Math.PI / 2;
        const bOff = width / 2;
        ctx.beginPath();
        ctx.moveTo(tailX + bOff * Math.cos(perp), tailY + bOff * Math.sin(perp));
        ctx.lineTo(tipX, tipY);
        ctx.lineTo(tailX - bOff * Math.cos(perp), tailY - bOff * Math.sin(perp));
        ctx.closePath();
        ctx.fill();
    } else if (style === 'needle') {
        const perp = angle + Math.PI / 2;
        const midX = (tailX + tipX) / 2;
        const midY = (tailY + tipY) / 2;
        const bOff = width / 3;
        ctx.beginPath();
        ctx.moveTo(tailX, tailY);
        ctx.quadraticCurveTo(midX + bOff * Math.cos(perp), midY + bOff * Math.sin(perp), tipX, tipY);
        ctx.quadraticCurveTo(midX - bOff * Math.cos(perp), midY - bOff * Math.sin(perp), tailX, tailY);
        ctx.closePath();
        ctx.fill();
    } else if (style === 'second') {
        // Thin line for second hand
        ctx.lineWidth = Math.max(1.5, width * 0.15);
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(tailX, tailY);
        ctx.lineTo(tipX, tipY);
        ctx.stroke();
    } else {
        // classic / line
        ctx.lineWidth = width;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(tailX, tailY);
        ctx.lineTo(tipX, tipY);
        ctx.stroke();
    }
}

/* ── radial lines ────────────────────────────────────── */

function _fpDrawRadialLines(ctx, center, radius, p) {
    const count = p.count || 12;
    const skip = p.skip_every || 0;
    const inner = (p.inner_radius || 89) / 100 * radius;
    const outer = (p.outer_radius || 95) / 100 * radius;
    const w = (p.width || 3) * (radius / 360);
    const color = _fpHex(p.color || '#fff');

    ctx.strokeStyle = color;
    ctx.lineWidth = w;
    ctx.lineCap = 'round';

    for (let i = 0; i < count; i++) {
        if (skip > 0 && i % skip === 0) continue;
        const angle = _fpDeg2Rad(i * (360 / count));
        if (p.shadow) {
            ctx.save(); ctx.translate(1, 1);
            ctx.strokeStyle = 'rgba(0,0,0,0.3)';
            ctx.beginPath();
            ctx.moveTo(center + inner * Math.cos(angle), center + inner * Math.sin(angle));
            ctx.lineTo(center + outer * Math.cos(angle), center + outer * Math.sin(angle));
            ctx.stroke();
            ctx.restore();
            ctx.strokeStyle = color;
        }
        ctx.beginPath();
        ctx.moveTo(center + inner * Math.cos(angle), center + inner * Math.sin(angle));
        ctx.lineTo(center + outer * Math.cos(angle), center + outer * Math.sin(angle));
        ctx.stroke();
    }
}

/* ── radial dots ─────────────────────────────────────── */

function _fpDrawRadialDots(ctx, center, radius, p) {
    const count = p.count || 12;
    const skip = p.skip_every || 0;
    const posR = (p.radius || 95) / 100 * radius;
    const dotR = (p.dot_radius || 5) * (radius / 360);
    const color = _fpHex(p.color || '#fff');

    ctx.fillStyle = color;
    for (let i = 0; i < count; i++) {
        if (skip > 0 && i % skip === 0) continue;
        const angle = _fpDeg2Rad(i * (360 / count));
        if (p.shadow) {
            ctx.fillStyle = 'rgba(0,0,0,0.3)';
            ctx.beginPath();
            ctx.arc(center + posR * Math.cos(angle) + 1, center + posR * Math.sin(angle) + 1, dotR, 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = color;
        }
        ctx.beginPath();
        ctx.arc(center + posR * Math.cos(angle), center + posR * Math.sin(angle), dotR, 0, Math.PI * 2);
        ctx.fill();
    }
}

/* ── radial text ─────────────────────────────────────── */

function _fpDrawRadialText(ctx, center, radius, p) {
    const labels = p.labels || ['12','1','2','3','4','5','6','7','8','9','10','11'];
    const posR = (p.radius || 82) / 100 * radius;
    const color = _fpHex(p.color || '#e0e0e0');
    const scale = radius / 360;
    const fs = (p.font_size && p.font_size > 0) ? p.font_size * scale : radius * 0.1;
    const family = p.font_family === 'serif' ? 'serif' : 'sans-serif';

    ctx.font = `bold ${fs}px ${family}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = color;

    for (let i = 0; i < labels.length; i++) {
        const angle = _fpDeg2Rad(i * (360 / labels.length));
        const x = center + posR * Math.cos(angle);
        const y = center + posR * Math.sin(angle);
        ctx.fillText(labels[i], x, y);
    }
}

/* ── text (static or bound) ──────────────────────────── */

function _fpDrawText(ctx, size, center, radius, el, p, dataCtx) {
    const bindings = el.bindings || {};
    const pos = el.position || [0, 0];
    const x = center + (pos[0] / 100) * radius;
    const y = center + (pos[1] / 100) * radius;

    let text = p.static_text || '';
    if (bindings.text) {
        const resolved = _fpResolveSource(bindings.text.source, dataCtx);
        if (resolved != null) text = String(resolved);
    }
    text = (p.prefix || '') + text + (p.suffix || '');
    if (!text) return;

    const scale = radius / 360;
    const fs = (p.font_size && p.font_size > 0) ? p.font_size * scale : radius * 0.12;
    const family = p.font_family === 'serif' ? 'serif' : 'sans-serif';
    const color = _fpHex(p.color || '#fff');

    ctx.font = `bold ${fs}px ${family}`;
    ctx.textAlign = p.align || 'center';
    ctx.textBaseline = 'middle';

    // Shadow
    ctx.fillStyle = 'rgba(0,0,0,0.4)';
    ctx.fillText(text, x + 1, y + 1);
    ctx.fillStyle = color;
    ctx.fillText(text, x, y);
}

/* ── alarm indicators ────────────────────────────────── */

function _fpDrawAlarms(ctx, center, radius, el, p, dataCtx) {
    const alarms = _fpAlarmData || [];
    if (!alarms.length) return;
    const color = _fpHex(p.color || '#ffaa00');
    const dotSize = (p.size || 4) * (radius / 360);
    const posR = (p.radius || 70) / 100 * radius;

    for (const alarm of alarms) {
        const timeStr = alarm.time || '';
        if (!timeStr || alarm.enabled === false) continue;
        const parts = timeStr.split(':');
        if (parts.length < 2) continue;
        const hour = parseInt(parts[0], 10) % 12;
        const minute = parseInt(parts[1], 10);
        const angle = ((hour + minute / 60) * 30 - 90) * Math.PI / 180;

        const x = center + posR * Math.cos(angle);
        const y = center + posR * Math.sin(angle);

        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(x, y, dotSize, 0, Math.PI * 2);
        ctx.fill();

        // Triangle pointer
        const tipX = center + (posR + dotSize * 1.5) * Math.cos(angle);
        const tipY = center + (posR + dotSize * 1.5) * Math.sin(angle);
        const perp = angle + Math.PI / 2;
        const off = dotSize * 0.6;
        ctx.beginPath();
        ctx.moveTo(tipX, tipY);
        ctx.lineTo(x + off * Math.cos(perp), y + off * Math.sin(perp));
        ctx.lineTo(x - off * Math.cos(perp), y - off * Math.sin(perp));
        ctx.closePath();
        ctx.fill();
    }
}

/* ── agenda ──────────────────────────────────────────── */

function _fpDrawAgenda(ctx, center, radius, el, p, dataCtx) {
    const events = _fpAgendaEvents || [];
    if (!events.length) return;

    const minR = (p.min_radius || 45) / 100 * radius;
    const maxR = (p.max_radius || 65) / 100 * radius;
    const opacity = (p.opacity != null ? p.opacity : 30) / 100;
    if (maxR <= minR) return;

    for (const ev of events) {
        const startStr = ev.start_time || '';
        const endStr = ev.end_time || '';
        const color = ev.color || '#4488ff';
        if (!startStr || !endStr) continue;

        const sp = startStr.split(':');
        const ep = endStr.split(':');
        if (sp.length < 2 || ep.length < 2) continue;
        const sh = parseInt(sp[0], 10), sm = parseInt(sp[1], 10);
        const eh = parseInt(ep[0], 10), em = parseInt(ep[1], 10);

        let startMins = sh * 60 + sm;
        let endMins = eh * 60 + em;
        if (endMins <= startMins) endMins += 24 * 60;
        const durationHours = Math.min((endMins - startMins) / 60, 12);

        const startPos = (sh % 12) + sm / 60;
        const startAngle = (startPos * 30 - 90) * Math.PI / 180;
        const endAngle = startAngle + durationHours * 30 * Math.PI / 180;

        ctx.fillStyle = _fpHexRGBA(color, opacity);
        ctx.beginPath();
        ctx.arc(center, center, maxR, startAngle, endAngle);
        ctx.arc(center, center, minR, endAngle, startAngle, true);
        ctx.closePath();
        ctx.fill();
    }

    // Current event text
    if (p.show_current_event) {
        const now = _fpGetTime();
        const currentMins = now.getHours() * 60 + now.getMinutes();
        let active = null;
        for (const ev of events) {
            const ss = (ev.start_time || '').split(':');
            const es = (ev.end_time || '').split(':');
            if (ss.length < 2 || es.length < 2) continue;
            let startMins2 = parseInt(ss[0], 10) * 60 + parseInt(ss[1], 10);
            let endMins2 = parseInt(es[0], 10) * 60 + parseInt(es[1], 10);
            if (endMins2 <= startMins2) endMins2 += 24 * 60;
            if (startMins2 <= currentMins && currentMins < endMins2) { active = ev; break; }
        }
        if (active && active.title) {
            const scale = radius / 360;
            const fs = (p.font_size && p.font_size > 0) ? p.font_size * scale : radius * 0.07;
            const oY = (p.offset_y || 25) / 100 * radius;
            ctx.font = `${fs}px sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillStyle = 'rgba(0,0,0,0.4)';
            ctx.fillText('\uD83D\uDCC5 ' + active.title, center + 1, center + oY + 1);
            ctx.fillStyle = _fpHex(active.color || '#4488ff');
            ctx.fillText('\uD83D\uDCC5 ' + active.title, center, center + oY);
        }
    }
}

/* ── arc ticks ───────────────────────────────────────── */

function _fpDrawArcTicks(ctx, center, radius, p) {
    let arcStart, arcEnd;
    if (p.arc_symmetric) {
        const ac = p.arc_center || 0;
        const ae = p.arc_extent || 135;
        arcStart = ac - ae;
        arcEnd = ac + ae;
    } else {
        arcStart = p.arc_start != null ? p.arc_start : 135;
        arcEnd = p.arc_end != null ? p.arc_end : 405;
    }

    const majorCount = p.major_count || 10;
    const majorInner = (p.major_inner_radius || 72) / 100 * radius;
    const majorOuter = (p.major_outer_radius || 77) / 100 * radius;

    ctx.lineCap = 'round';

    // Major ticks
    for (let i = 0; i <= majorCount; i++) {
        const frac = i / majorCount;
        const deg = arcStart + (arcEnd - arcStart) * frac;
        const angle = _fpDeg2Rad(deg);

        ctx.strokeStyle = _fpHex(p.major_color || '#fff');
        ctx.lineWidth = (p.major_width || 2) * (radius / 360);
        ctx.beginPath();
        ctx.moveTo(center + majorInner * Math.cos(angle), center + majorInner * Math.sin(angle));
        ctx.lineTo(center + majorOuter * Math.cos(angle), center + majorOuter * Math.sin(angle));
        ctx.stroke();
    }

    // Minor ticks
    if (p.minor_ticks) {
        const minorCount = p.minor_count || 4;
        const minorInner = (p.minor_inner_radius || 74) / 100 * radius;
        const minorOuter = (p.minor_outer_radius || 77) / 100 * radius;

        for (let i = 0; i < majorCount; i++) {
            for (let j = 1; j <= minorCount; j++) {
                const frac = (i + j / (minorCount + 1)) / majorCount;
                const deg = arcStart + (arcEnd - arcStart) * frac;
                const angle = _fpDeg2Rad(deg);

                ctx.strokeStyle = _fpHex(p.minor_color || '#666');
                ctx.lineWidth = (p.minor_width || 1) * (radius / 360);
                ctx.beginPath();
                ctx.moveTo(center + minorInner * Math.cos(angle), center + minorInner * Math.sin(angle));
                ctx.lineTo(center + minorOuter * Math.cos(angle), center + minorOuter * Math.sin(angle));
                ctx.stroke();
            }
        }
    }
}

/* ── binding resolution ──────────────────────────────── */

function _fpResolveSource(source, dataCtx) {
    return dataCtx[source] != null ? dataCtx[source] : null;
}

function _fpResolveBinding(binding, dataCtx) {
    const source = binding.source || '';
    let value = _fpResolveSource(source, dataCtx);
    if (binding.transform === 'arc_angle') {
        let arcStart, arcEnd;
        if (binding.arc_symmetric) {
            const ac = binding.arc_center || 0;
            const ae = binding.arc_extent || 135;
            arcStart = ac - ae;
            arcEnd = ac + ae;
        } else {
            arcStart = binding.arc_start != null ? binding.arc_start : 135;
            arcEnd = binding.arc_end != null ? binding.arc_end : 405;
        }
        const pct = Math.max(0, Math.min(100, parseFloat(value) || 0));
        return arcStart + (arcEnd - arcStart) * (pct / 100);
    }
    return value;
}
