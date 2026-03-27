/**
 * Shared dial canvas renderer used by both the Dial editor and Timer pages.
 *
 * drawDialPreview(ctx, dialConfig, bgConfig, progress, bgGradientStops, opts)
 *   ctx             - CanvasRenderingContext2D
 *   dialConfig      - The dial appearance object (arc, track, ticks, hand, text…)
 *   bgConfig        - The background config (type, color, gradient…)
 *   progress        - Current animated progress 0–100
 *   bgGradientStops - Array of { position, color } for bg gradient
 *   opts            - Optional overrides:
 *       progressColor  - override for progress arc color
 *       label          - text label to render
 *       value          - numeric value to render
 *       minValue       - min label
 *       maxValue       - max label
 *       size           - canvas logical size (default 360)
 */
function drawDialPreview(ctx, dialConfig, bgConfig, progress, bgGradientStops, opts) {
    const a = dialConfig;
    const bg = bgConfig;
    if (!a || !bg) return;
    opts = opts || {};
    const size = opts.size || 360;
    const center = size / 2;
    const dpr = window.devicePixelRatio || 1;
    const canvas = ctx.canvas;
    if (canvas.width !== size * dpr) {
        canvas.width = size * dpr;
        canvas.height = size * dpr;
        canvas.style.width = size + 'px';
        canvas.style.height = size + 'px';
        ctx.scale(dpr, dpr);
    }

    ctx.clearRect(0, 0, size, size);
    ctx.save();
    ctx.beginPath();
    ctx.arc(center, center, center, 0, Math.PI * 2);
    ctx.clip();

    // --- Background ---
    const bgType = bg.type || 'solid';
    const colorOpacity = (bg.color_opacity ?? 100) / 100;
    if (bgType === 'gradient' && bgGradientStops && bgGradientStops.length) {
        const gradType = bg.gradient_type || 'radial';
        let grad;
        if (gradType === 'radial') {
            const cx = (bg.gradient_center_x ?? 0.5) * size;
            const cy = (bg.gradient_center_y ?? 0.5) * size;
            const r = (bg.gradient_radius ?? 1.0) * center;
            grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
        } else {
            const angle = (bg.gradient_angle || 0) * Math.PI / 180;
            const dx = Math.cos(angle) * center;
            const dy = Math.sin(angle) * center;
            grad = ctx.createLinearGradient(center - dx, center - dy, center + dx, center + dy);
        }
        for (const s of bgGradientStops) grad.addColorStop(s.position, s.color);
        ctx.globalAlpha = colorOpacity;
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, size, size);
        ctx.globalAlpha = 1;
    } else {
        ctx.globalAlpha = colorOpacity;
        ctx.fillStyle = bg.color || '#0f172a';
        ctx.fillRect(0, 0, size, size);
        ctx.globalAlpha = 1;
    }

    const radius = a.radius / 100 * center;
    const thickness = a.thickness / 100 * radius;
    const half = center;

    const degToRad = (deg) => (deg - 90) * Math.PI / 180;
    let arcStart, arcEnd;
    if (a.arc_symmetric) {
        const ac = a.arc_center ?? 0;
        const ae = a.arc_extent ?? 135;
        arcStart = ac - ae;
        arcEnd = ac + ae;
    } else {
        arcStart = a.arc_start;
        arcEnd = a.arc_end;
    }
    const startRad = degToRad(arcStart);
    const endRad = degToRad(arcEnd);
    const sweep = endRad - startRad;

    const hexToRgba = (hex, alpha) => {
        const r = parseInt(hex.slice(1, 3), 16);
        const g = parseInt(hex.slice(3, 5), 16);
        const b = parseInt(hex.slice(5, 7), 16);
        return `rgba(${r},${g},${b},${alpha})`;
    };

    // --- Track ---
    ctx.lineWidth = thickness;
    ctx.lineCap = a.cap_style;

    if (a.track_style === 'zones' && a.track_zones && a.track_zones.length) {
        const trackAlpha = a.track_opacity / 100;
        for (const zone of a.track_zones) {
            const zStart = startRad + sweep * (zone.from / 100);
            const zEnd = startRad + sweep * (zone.to / 100);
            ctx.beginPath();
            ctx.arc(center, center, radius, zStart, zEnd);
            ctx.strokeStyle = hexToRgba(zone.color, trackAlpha);
            ctx.globalAlpha = 1;
            ctx.stroke();
        }
    } else if (a.track_style === 'gradient') {
        const sx = center + radius * Math.cos(startRad);
        const sy = center + radius * Math.sin(startRad);
        const ex = center + radius * Math.cos(endRad);
        const ey = center + radius * Math.sin(endRad);
        const grad = ctx.createLinearGradient(sx, sy, ex, ey);
        grad.addColorStop(0, a.track_gradient_start);
        grad.addColorStop(1, a.track_gradient_end);
        ctx.beginPath();
        ctx.arc(center, center, radius, startRad, endRad);
        ctx.strokeStyle = grad;
        ctx.globalAlpha = a.track_opacity / 100;
        ctx.stroke();
        ctx.globalAlpha = 1;
    } else {
        ctx.beginPath();
        ctx.arc(center, center, radius, startRad, endRad);
        ctx.strokeStyle = a.track_color;
        ctx.globalAlpha = a.track_opacity / 100;
        ctx.stroke();
        ctx.globalAlpha = 1;
    }

    // --- Progress arc ---
    const prog = Math.max(0, Math.min(100, progress));
    if (a.show_progress !== false && prog > 0) {
        const progEnd = startRad + sweep * (prog / 100);
        ctx.beginPath();
        ctx.arc(center, center, radius, startRad, progEnd);
        const pc = opts.progressColor || a.progress_color;
        if (a.style === 'gradient') {
            const gx1 = center + radius * Math.cos(startRad);
            const gy1 = center + radius * Math.sin(startRad);
            const gx2 = center + radius * Math.cos(progEnd);
            const gy2 = center + radius * Math.sin(progEnd);
            const grad = ctx.createLinearGradient(gx1, gy1, gx2, gy2);
            grad.addColorStop(0, pc);
            grad.addColorStop(1, a.gradient_end_color);
            ctx.strokeStyle = grad;
        } else {
            ctx.strokeStyle = pc;
        }
        ctx.globalAlpha = a.progress_opacity / 100;
        ctx.lineWidth = thickness;
        ctx.lineCap = a.cap_style;
        if (a.style === 'dashed') {
            ctx.setLineDash([a.dash_length, a.dash_gap]);
        } else {
            ctx.setLineDash([]);
        }
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.globalAlpha = 1;
    }

    // --- Tick marks ---
    if (a.tick_marks) {
        ctx.lineCap = 'butt';
        const majCount = a.major_tick_count || 10;
        if (majCount >= 2) {
            if (a.minor_ticks && a.minor_tick_count > 0) {
                const minInner = (a.minor_tick_inner_radius || 73) / 100 * half;
                const minOuter = (a.minor_tick_outer_radius || 77) / 100 * half;
                ctx.strokeStyle = a.minor_tick_color || '#555555';
                ctx.lineWidth = a.minor_tick_width || 1;
                const minPer = a.minor_tick_count;
                for (let i = 0; i < majCount; i++) {
                    for (let j = 1; j <= minPer; j++) {
                        const frac = (i + j / (minPer + 1)) / majCount;
                        const angle = startRad + sweep * frac;
                        ctx.beginPath();
                        ctx.moveTo(center + minInner * Math.cos(angle), center + minInner * Math.sin(angle));
                        ctx.lineTo(center + minOuter * Math.cos(angle), center + minOuter * Math.sin(angle));
                        ctx.stroke();
                    }
                }
            }
            const majInner = (a.major_tick_inner_radius || 72) / 100 * half;
            const majOuter = (a.major_tick_outer_radius || 78) / 100 * half;
            ctx.strokeStyle = a.major_tick_color || '#888888';
            ctx.lineWidth = a.major_tick_width || 2;
            for (let i = 0; i <= majCount; i++) {
                const angle = startRad + sweep * (i / majCount);
                ctx.beginPath();
                ctx.moveTo(center + majInner * Math.cos(angle), center + majInner * Math.sin(angle));
                ctx.lineTo(center + majOuter * Math.cos(angle), center + majOuter * Math.sin(angle));
                ctx.stroke();
            }
        }
    }

    // --- Hand ---
    const handAngle = startRad + sweep * (prog / 100);
    if (a.show_hand) {
        const tipR = (a.hand_length || 80) / 100 * half;
        const tailR = (a.hand_tail ?? 10) / 100 * half;
        const baseW = (a.hand_width || 3) / 100 * radius;
        const cosA = Math.cos(handAngle);
        const sinA = Math.sin(handAngle);
        const cosP = Math.cos(handAngle + Math.PI / 2);
        const sinP = Math.sin(handAngle + Math.PI / 2);
        const tipX = center + tipR * cosA;
        const tipY = center + tipR * sinA;
        const tailX = center - tailR * cosA;
        const tailY = center - tailR * sinA;

        ctx.fillStyle = a.hand_color || '#ffffff';
        ctx.strokeStyle = a.hand_color || '#ffffff';

        if (a.hand_style === 'line') {
            ctx.lineWidth = Math.max(baseW, 2);
            ctx.lineCap = 'round';
            ctx.beginPath();
            ctx.moveTo(tailX, tailY);
            ctx.lineTo(tipX, tipY);
            ctx.stroke();
        } else if (a.hand_style === 'needle') {
            const shaftW = Math.max(baseW * 0.3, 1);
            const diamondW = Math.max(baseW * 1.2, 2);
            const diamondLen = tipR * 0.06;
            ctx.lineWidth = shaftW;
            ctx.lineCap = 'butt';
            const dbx = center + (tipR - diamondLen) * cosA;
            const dby = center + (tipR - diamondLen) * sinA;
            ctx.beginPath();
            ctx.moveTo(tailX, tailY);
            ctx.lineTo(dbx, dby);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(tipX, tipY);
            ctx.lineTo(dbx + diamondW * cosP, dby + diamondW * sinP);
            ctx.lineTo(center + (tipR - diamondLen * 2) * cosA, center + (tipR - diamondLen * 2) * sinA);
            ctx.lineTo(dbx - diamondW * cosP, dby - diamondW * sinP);
            ctx.closePath();
            ctx.fill();
        } else {
            ctx.beginPath();
            ctx.moveTo(tipX, tipY);
            ctx.lineTo(tailX + baseW * cosP, tailY + baseW * sinP);
            ctx.lineTo(tailX - baseW * cosP, tailY - baseW * sinP);
            ctx.closePath();
            ctx.fill();
        }
    }

    // --- Label ---
    if (a.show_text && opts.label) {
        const labelSize = a.label_font_size || Math.round(size * 0.045);
        const labelY = center + a.label_offset_y / 100 * radius;
        ctx.fillStyle = a.label_color;
        ctx.font = `${labelSize}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(opts.label, center, labelY);
    }

    // --- Value text ---
    if (a.show_value && opts.value != null) {
        const valSize = a.value_font_size || Math.round(size * 0.07);
        const valY = center + (a.value_offset_y ?? 12) / 100 * radius;
        const valStr = opts.value + (a.value_suffix || '');
        ctx.fillStyle = a.value_color || '#ffffff';
        ctx.font = `bold ${valSize}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(valStr, center, valY);
    }

    // --- Min / Max labels ---
    if (a.show_min_max && opts.minValue != null && opts.maxValue != null) {
        const mmSize = a.min_max_font_size || Math.round(size * 0.03);
        const labelR = radius * 0.82;
        ctx.fillStyle = a.min_max_color || '#666666';
        ctx.font = `${mmSize}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        const minX = center + labelR * Math.cos(startRad);
        const minY = center + labelR * Math.sin(startRad);
        const maxX = center + labelR * Math.cos(endRad);
        const maxY = center + labelR * Math.sin(endRad);
        ctx.fillText(String(opts.minValue), minX, minY);
        ctx.fillText(String(opts.maxValue), maxX, maxY);
    }

    // --- Hand center dot ---
    if (a.show_hand && a.hand_center_dot) {
        const dotR = (a.hand_center_dot_radius || 4) / 100 * half;
        ctx.beginPath();
        ctx.arc(center, center, dotR, 0, Math.PI * 2);
        ctx.fillStyle = a.hand_center_dot_color || '#333333';
        ctx.fill();
        ctx.beginPath();
        ctx.arc(center, center, dotR, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(255,255,255,0.15)';
        ctx.lineWidth = 1;
        ctx.stroke();
    }

    ctx.restore();
}
