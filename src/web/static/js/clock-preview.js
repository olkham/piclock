/**
 * Clock preview — Canvas-based rendering that mirrors the Cairo output.
 * Used in the web UI for real-time theme preview.
 * Optimised: static face is cached; only hands redraw each second.
 */

let _previewRAF = null;
let _staticCache = null;   // offscreen canvas for face+markers
let _cachedThemeJSON = '';  // serialised theme for cache invalidation
let _previewTimezone = null; // IANA timezone string (e.g. "America/New_York")
let _bgImageCache = {};    // cache loaded background images by URL
let _agendaEvents = [];    // cached agenda events for pie chart

function startClockPreview(canvasId, theme, timezone) {
    if (_previewRAF) cancelAnimationFrame(_previewRAF);
    _staticCache = null;
    _cachedThemeJSON = '';
    _previewTimezone = timezone || null;

    const canvas = document.getElementById(canvasId);
    if (!canvas || !theme) return;

    // Fetch agenda events for pie chart preview
    fetch('/api/agenda').then(r => r.json()).then(events => {
        _agendaEvents = events || [];
        _staticCache = null;
        _cachedThemeJSON = '';
    }).catch(() => { _agendaEvents = []; });

    let lastSec = -1;
    function tick() {
        const now = _getPreviewTime();
        if (now.getSeconds() !== lastSec) {
            lastSec = now.getSeconds();
            renderClock(canvas, theme, now);
        }
        _previewRAF = requestAnimationFrame(tick);
    }
    tick();
}

function _getPreviewTime() {
    if (_previewTimezone) {
        // Format time parts in the configured timezone
        const now = new Date();
        const parts = {};
        for (const part of ['hour', 'minute', 'second']) {
            const fmt = new Intl.DateTimeFormat('en-US', {
                timeZone: _previewTimezone,
                [part]: 'numeric',
                hour12: false,
            });
            parts[part] = parseInt(fmt.format(now), 10);
        }
        // Build a Date-like object that matches the configured timezone
        const d = new Date(now);
        d.setHours(parts.hour, parts.minute, parts.second);
        return d;
    }
    return new Date();
}

/* ── helpers ──────────────────────────────────────────── */

function hexToCSS(hex) {
    if (!hex) return '#000';
    return hex.startsWith('#') ? hex : '#' + hex;
}

/* ── main render ─────────────────────────────────────── */

function renderClock(canvas, theme, now) {
    const ctx = canvas.getContext('2d');
    const size = canvas.width;
    const center = size / 2;
    const radius = size / 2;

    // Rebuild static cache when theme changes
    const key = JSON.stringify(theme);
    if (key !== _cachedThemeJSON) {
        _cachedThemeJSON = key;
        _staticCache = buildStaticLayer(size, center, radius, theme);
    }

    ctx.clearRect(0, 0, size, size);

    // Draw cached background + markers
    ctx.drawImage(_staticCache, 0, 0);

    // Clip to circle for hands
    ctx.save();
    ctx.beginPath();
    ctx.arc(center, center, radius, 0, Math.PI * 2);
    ctx.clip();

    // Hands
    const time = { hour: now.getHours(), minute: now.getMinutes(), second: now.getSeconds(), ms: now.getMilliseconds() };
    drawHands(ctx, center, radius, time, theme);

    ctx.restore();
}

/* ── static layer (background + markers) ────────────── */

function buildStaticLayer(size, center, radius, theme) {
    const offscreen = document.createElement('canvas');
    offscreen.width = size;
    offscreen.height = size;
    const ctx = offscreen.getContext('2d');

    ctx.save();
    ctx.beginPath();
    ctx.arc(center, center, radius, 0, Math.PI * 2);
    ctx.clip();

    drawBackground(ctx, size, center, radius, theme);
    drawAgenda(ctx, center, radius, theme, _agendaEvents);
    drawMarkers(ctx, center, radius, theme);

    ctx.restore();

    // Circle border
    ctx.beginPath();
    ctx.arc(center, center, radius - 1, 0, Math.PI * 2);
    ctx.strokeStyle = '#333';
    ctx.lineWidth = 2;
    ctx.stroke();

    return offscreen;
}

/* ── background ──────────────────────────────────────── */

function drawBackground(ctx, size, center, radius, theme) {
    const bg = theme.background || {};

    if (bg.type === 'image' && bg.image) {
        // Derive the web URL from the filesystem path
        const filename = bg.image.replace(/\\/g, '/').split('/').pop();
        const url = '/api/uploads/' + filename;

        if (_bgImageCache[url] && _bgImageCache[url].complete) {
            const img = _bgImageCache[url];
            const scale = Math.max(size / img.naturalWidth, size / img.naturalHeight);
            const dx = (size - img.naturalWidth * scale) / 2;
            const dy = (size - img.naturalHeight * scale) / 2;
            ctx.save();
            ctx.translate(dx, dy);
            ctx.scale(scale, scale);
            ctx.drawImage(img, 0, 0);
            ctx.restore();
            return;
        }

        // Start loading if not cached
        if (!_bgImageCache[url]) {
            const img = new window.Image();
            img.crossOrigin = 'anonymous';
            img.onload = () => {
                // Invalidate cache to force redraw with image
                _cachedThemeJSON = '';
            };
            img.src = url;
            _bgImageCache[url] = img;
        }

        // Fallback color while loading
        ctx.fillStyle = hexToCSS(bg.color || '#1a1a2e');
        ctx.fillRect(0, 0, size, size);
        return;
    }

    if (bg.type === 'gradient' && ((bg.colors && bg.colors.length >= 2) || (bg.color_stops && bg.color_stops.length >= 2))) {
        const gType = bg.gradient_type || 'radial';
        let grad;

        if (gType === 'linear') {
            const angle = ((bg.gradient_angle || 0) - 90) * Math.PI / 180;
            const dx = Math.cos(angle) * radius;
            const dy = Math.sin(angle) * radius;
            grad = ctx.createLinearGradient(center - dx, center - dy, center + dx, center + dy);
        } else {
            const cx = (bg.gradient_center_x != null ? bg.gradient_center_x : 0.5) * size;
            const cy = (bg.gradient_center_y != null ? bg.gradient_center_y : 0.5) * size;
            const gr = (bg.gradient_radius != null ? bg.gradient_radius : 1.0) * radius;
            grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, gr);
        }

        if (bg.color_stops && bg.color_stops.length > 0) {
            bg.color_stops.forEach(stop => {
                grad.addColorStop(stop.position || 0, hexToCSS(stop.color || '#000'));
            });
        } else {
            bg.colors.forEach((c, i) => {
                grad.addColorStop(i / (bg.colors.length - 1), hexToCSS(c));
            });
        }
        ctx.fillStyle = grad;
    } else {
        ctx.fillStyle = hexToCSS(bg.color || '#1a1a2e');
    }
    ctx.fillRect(0, 0, size, size);
}

/* ── markers ─────────────────────────────────────────── */

function drawMarkers(ctx, center, radius, theme) {
    const markers = theme.markers || {};
    const scale = radius / 360;

    // Minute markers
    if (markers.show_minutes !== false) {
        const mStyle = markers.minute_style || 'line';
        const mColor = hexToCSS(markers.minute_color || '#444444');

        for (let i = 0; i < 60; i++) {
            if (i % 5 === 0) continue;
            const angle = (i * 6 - 90) * Math.PI / 180;

            if (mStyle === 'dot') {
                const dotR = (markers.minute_dot_radius || 2) * scale;
                const dist = radius * 0.92;
                if (markers.minute_shadow) {
                    ctx.fillStyle = 'rgba(0,0,0,0.3)';
                    ctx.beginPath();
                    ctx.arc(center + dist * Math.cos(angle) + 1, center + dist * Math.sin(angle) + 1, dotR, 0, Math.PI * 2);
                    ctx.fill();
                }
                ctx.fillStyle = mColor;
                ctx.beginPath();
                ctx.arc(center + dist * Math.cos(angle), center + dist * Math.sin(angle), dotR, 0, Math.PI * 2);
                ctx.fill();
            } else {
                const mLen = markers.minute_length || 0.02;
                const inner = radius * (1 - mLen);
                const outer = radius * 0.95;
                if (markers.minute_shadow) {
                    ctx.save();
                    ctx.translate(1, 1);
                    ctx.strokeStyle = 'rgba(0,0,0,0.3)';
                    ctx.lineWidth = markers.minute_width || 1.5;
                    ctx.lineCap = 'round';
                    ctx.beginPath();
                    ctx.moveTo(center + inner * Math.cos(angle), center + inner * Math.sin(angle));
                    ctx.lineTo(center + outer * Math.cos(angle), center + outer * Math.sin(angle));
                    ctx.stroke();
                    ctx.restore();
                }
                ctx.strokeStyle = mColor;
                ctx.lineWidth = markers.minute_width || 1.5;
                ctx.lineCap = 'round';
                ctx.beginPath();
                ctx.moveTo(center + inner * Math.cos(angle), center + inner * Math.sin(angle));
                ctx.lineTo(center + outer * Math.cos(angle), center + outer * Math.sin(angle));
                ctx.stroke();
            }
        }
    }

    // Hour markers
    const style = markers.hour_style || 'line';
    if (style === 'none') return;

    const hColor = hexToCSS(markers.hour_color || '#ffffff');
    const hasShadow = !!markers.hour_shadow;

    if (style === 'line') {
        const hLen = markers.hour_length || 0.06;
        for (let i = 0; i < 12; i++) {
            const angle = (i * 30 - 90) * Math.PI / 180;
            const inner = radius * (1 - hLen);
            const outer = radius * 0.95;
            if (hasShadow) {
                ctx.save(); ctx.translate(1, 1);
                ctx.strokeStyle = 'rgba(0,0,0,0.3)';
                ctx.lineWidth = markers.hour_width || 3;
                ctx.lineCap = 'round';
                ctx.beginPath();
                ctx.moveTo(center + inner * Math.cos(angle), center + inner * Math.sin(angle));
                ctx.lineTo(center + outer * Math.cos(angle), center + outer * Math.sin(angle));
                ctx.stroke();
                ctx.restore();
            }
            ctx.strokeStyle = hColor;
            ctx.lineWidth = markers.hour_width || 3;
            ctx.lineCap = 'round';
            ctx.beginPath();
            ctx.moveTo(center + inner * Math.cos(angle), center + inner * Math.sin(angle));
            ctx.lineTo(center + outer * Math.cos(angle), center + outer * Math.sin(angle));
            ctx.stroke();
        }
    } else if (style === 'dot') {
        const dotR = (markers.dot_radius || 5) * scale;
        for (let i = 0; i < 12; i++) {
            const angle = (i * 30 - 90) * Math.PI / 180;
            const dist = radius * 0.88;
            if (hasShadow) {
                ctx.fillStyle = 'rgba(0,0,0,0.3)';
                ctx.beginPath();
                ctx.arc(center + dist * Math.cos(angle) + 1, center + dist * Math.sin(angle) + 1, dotR, 0, Math.PI * 2);
                ctx.fill();
            }
            ctx.fillStyle = hColor;
            ctx.beginPath();
            ctx.arc(center + dist * Math.cos(angle), center + dist * Math.sin(angle), dotR, 0, Math.PI * 2);
            ctx.fill();
        }
    } else if (style === 'roman' || style === 'arabic' || style === 'custom') {
        let numerals;
        if (style === 'custom') {
            numerals = markers.hour_labels || ['XII','I','II','III','IV','V','VI','VII','VIII','IX','X','XI'];
        } else if (style === 'roman') {
            numerals = ['XII','I','II','III','IV','V','VI','VII','VIII','IX','X','XI'];
        } else {
            numerals = ['12','1','2','3','4','5','6','7','8','9','10','11'];
        }

        const fSize = (markers.font_size && markers.font_size > 0)
            ? markers.font_size * scale
            : radius * 0.1;
        const fontFamily = style === 'roman' ? 'serif' : 'sans-serif';
        ctx.font = `bold ${fSize}px ${fontFamily}`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';

        for (let i = 0; i < 12; i++) {
            const angle = (i * 30 - 90) * Math.PI / 180;
            const x = center + radius * 0.82 * Math.cos(angle);
            const y = center + radius * 0.82 * Math.sin(angle);
            if (hasShadow) {
                ctx.fillStyle = 'rgba(0,0,0,0.4)';
                ctx.fillText(numerals[i], x + 1, y + 1);
            }
            ctx.fillStyle = hColor;
            ctx.fillText(numerals[i], x, y);
        }
    }
}

/* ── agenda pie chart ────────────────────────────────── */

function drawAgenda(ctx, center, radius, theme, events) {
    const cfg = theme.agenda || {};
    if (!cfg.enabled || !events || events.length === 0) return;

    const minR = (cfg.min_radius || 0) / 100 * radius;
    const maxR = (cfg.max_radius || 80) / 100 * radius;
    const opacity = (cfg.opacity != null ? cfg.opacity : 35) / 100;
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

        // Parse color and apply opacity
        const r = parseInt(color.slice(1, 3), 16);
        const g = parseInt(color.slice(3, 5), 16);
        const b = parseInt(color.slice(5, 7), 16);
        ctx.fillStyle = `rgba(${r},${g},${b},${opacity})`;

        ctx.beginPath();
        ctx.arc(center, center, maxR, startAngle, endAngle);
        ctx.arc(center, center, minR, endAngle, startAngle, true);
        ctx.closePath();
        ctx.fill();
    }
}

/* ── hands ───────────────────────────────────────────── */

function _getStartEnd(cfg, defStart, defEnd) {
    if (cfg.start != null && cfg.end != null) return [cfg.start / 100, cfg.end / 100];
    const length = cfg.length || (defEnd / 100);
    const tail = cfg.tail != null ? cfg.tail : (Math.abs(defStart) / 100);
    return [-tail, length];
}

function drawHands(ctx, center, radius, time, theme) {
    const hands = theme.hands || {};
    const hour = time.hour % 12;
    const minute = time.minute;
    const second = time.second;
    const ms = time.ms || 0;

    const hourAngle = (hour + minute / 60) * 30 - 90;
    const minuteAngle = (minute + second / 60) * 6 - 90;
    const secondAngle = (second + ms / 1000) * 6 - 90;

    // Hour hand
    const hCfg = hands.hour || {};
    const [hStart, hEnd] = _getStartEnd(hCfg, -8, 45);
    drawHand(ctx, center, radius, hourAngle, hEnd, hCfg.width || 14,
             hexToCSS(hCfg.color || '#ffffff'), hStart, hCfg.style || 'tapered',
             hCfg.shadow !== false, hCfg.glow, hexToCSS(hCfg.glow_color || hCfg.color || '#ffffff'));

    // Minute hand
    const mCfg = hands.minute || {};
    const [mStart, mEnd] = _getStartEnd(mCfg, -10, 65);
    drawHand(ctx, center, radius, minuteAngle, mEnd, mCfg.width || 10,
             hexToCSS(mCfg.color || '#ffffff'), mStart, mCfg.style || 'tapered',
             mCfg.shadow !== false, mCfg.glow, hexToCSS(mCfg.glow_color || mCfg.color || '#ffffff'));

    // Second hand
    const sCfg = hands.second || {};
    if (sCfg.visible !== false) {
        const showCW = sCfg.counterweight !== false;
        const cwR = sCfg.counterweight_radius || 0.04;
        const [sStart, sEnd] = _getStartEnd(sCfg, -15, 72);
        drawSecondHand(ctx, center, radius, secondAngle, sEnd,
                       hexToCSS(sCfg.color || '#ff4444'), sStart,
                       sCfg.shadow !== false, sCfg.glow, hexToCSS(sCfg.glow_color || sCfg.color || '#ff4444'),
                       showCW, cwR);
    }

    // Center dot
    const dot = theme.center_dot || {};
    if (dot.visible !== false) {
        const dotR = (dot.radius || 7) * (radius / 360);
        ctx.fillStyle = hexToCSS(dot.color || '#ffffff');
        ctx.beginPath();
        ctx.arc(center, center, dotR, 0, Math.PI * 2);
        ctx.fill();
    }

    // Clock text
    const ct = theme.clock_text || {};
    if (ct.visible) {
        const h = time.hour;
        const m = time.minute;
        let text;
        if (ct.format === '24h') {
            text = String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');
        } else {
            const suffix = h < 12 ? ' AM' : ' PM';
            text = (h % 12 || 12) + ':' + String(m).padStart(2, '0') + suffix;
        }
        const scale = radius / 360;
        const fs = (ct.font_size && ct.font_size > 0) ? ct.font_size * scale : radius * 0.12;
        const offsetY = (ct.offset_y != null ? ct.offset_y : 25) / 100 * radius;
        ctx.font = `bold ${fs}px sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillStyle = 'rgba(0,0,0,0.4)';
        ctx.fillText(text, center + 1, center + offsetY + 1);
        ctx.fillStyle = hexToCSS(ct.color || '#ffffff');
        ctx.fillText(text, center, center + offsetY);
    }
}

function drawHand(ctx, center, radius, angleDeg, end, width, color, start, style, shadow, glow, glowColor) {
    const angle = angleDeg * Math.PI / 180;
    const tipR = radius * end;
    const scale = radius / 360;

    const tipX = center + tipR * Math.cos(angle);
    const tipY = center + tipR * Math.sin(angle);
    let tailX, tailY;
    if (start < 0) {
        const tailR = radius * Math.abs(start);
        tailX = center - tailR * Math.cos(angle);
        tailY = center - tailR * Math.sin(angle);
    } else {
        const startR = radius * start;
        tailX = center + startR * Math.cos(angle);
        tailY = center + startR * Math.sin(angle);
    }

    const w = width * scale;

    if (shadow) {
        ctx.save();
        ctx.translate(2, 2);
        ctx.globalAlpha = 0.3;
        ctx.fillStyle = '#000';
        ctx.strokeStyle = '#000';
        strokeHand(ctx, tipX, tipY, tailX, tailY, w, style, angle);
        ctx.restore();
    }

    if (glow) {
        ctx.save();
        ctx.shadowColor = glowColor || color;
        ctx.shadowBlur = 12 * scale;
        ctx.fillStyle = color;
        ctx.strokeStyle = color;
        strokeHand(ctx, tipX, tipY, tailX, tailY, w, style, angle);
        ctx.restore();
    }

    ctx.fillStyle = color;
    ctx.strokeStyle = color;
    strokeHand(ctx, tipX, tipY, tailX, tailY, w, style, angle);
}

function strokeHand(ctx, tipX, tipY, tailX, tailY, width, style, angle) {
    if (style === 'tapered') {
        const perp = angle + Math.PI / 2;
        const baseOff = width / 2;
        const tipOff = width / 6;
        ctx.beginPath();
        ctx.moveTo(tailX + baseOff * Math.cos(perp), tailY + baseOff * Math.sin(perp));
        ctx.lineTo(tipX + tipOff * Math.cos(perp), tipY + tipOff * Math.sin(perp));
        ctx.lineTo(tipX - tipOff * Math.cos(perp), tipY - tipOff * Math.sin(perp));
        ctx.lineTo(tailX - baseOff * Math.cos(perp), tailY - baseOff * Math.sin(perp));
        ctx.closePath();
        ctx.fill();
    } else {
        ctx.lineWidth = width;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(tailX, tailY);
        ctx.lineTo(tipX, tipY);
        ctx.stroke();
    }
}

function drawSecondHand(ctx, center, radius, angleDeg, end, color, start, shadow, glow, glowColor, showCW, cwRadius) {
    const angle = angleDeg * Math.PI / 180;
    const tipR = radius * end;
    const scale = radius / 360;

    const tipX = center + tipR * Math.cos(angle);
    const tipY = center + tipR * Math.sin(angle);
    let tailX, tailY;
    if (start < 0) {
        const tailR = radius * Math.abs(start);
        tailX = center - tailR * Math.cos(angle);
        tailY = center - tailR * Math.sin(angle);
    } else {
        const startR = radius * start;
        tailX = center + startR * Math.cos(angle);
        tailY = center + startR * Math.sin(angle);
    }

    if (shadow) {
        ctx.save();
        ctx.translate(2, 2);
        ctx.globalAlpha = 0.3;
        ctx.strokeStyle = '#000';
        ctx.fillStyle = '#000';
        ctx.lineWidth = 1.5 * scale;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(tailX, tailY);
        ctx.lineTo(tipX, tipY);
        ctx.stroke();
        ctx.restore();
    }

    if (glow) {
        ctx.save();
        ctx.shadowColor = glowColor || color;
        ctx.shadowBlur = 10 * scale;
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5 * scale;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(tailX, tailY);
        ctx.lineTo(tipX, tipY);
        ctx.stroke();
        ctx.restore();
    }

    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = 1.5 * scale;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(tailX, tailY);
    ctx.lineTo(tipX, tipY);
    ctx.stroke();

    // Counterweight
    if (showCW) {
        const cwDist = radius * 0.10;
        const cwR = radius * (cwRadius || 0.04);
        ctx.beginPath();
        ctx.arc(center - cwDist * Math.cos(angle), center - cwDist * Math.sin(angle), cwR, 0, Math.PI * 2);
        ctx.fill();
    }
}
