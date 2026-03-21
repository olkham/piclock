## Plan: PiClock3 — Analogue Clock for Pi Zero

Build a beautiful analogue clock rendered with **PyCairo** (vector graphics, anti-aliased, gradients, shadows) displayed via **Pygame** on a **Waveshare 4" round HDMI display** (720×720). Python backend with **Flask** for web config UI and REST API. Theme system stored in **SQLite**. Cross-developed on Windows, deployed to Pi Zero.

---

### Tech Stack
- **PyCairo** — high-quality anti-aliased vector rendering (the best option for beautiful graphics on ARM)
- **Pygame** — cross-platform display output (window on Windows, framebuffer on Pi) + audio for alarms
- **Flask** — lightweight web server for config UI + REST API
- **SQLite** — theme/settings/alarm storage (thread-safe, zero-config)
- **Alpine.js + Tailwind CSS (CDN)** — lightweight web UI interactivity
- **systemd** — auto-start service on Pi

### Key Architecture Decisions
- **Dynamic FPS** — 1fps normally (Pi Zero CPU <5%), auto-scales to 30fps during alarm animations for smooth visuals
- **Flask in a background thread** — single-process architecture, shares config via SQLite
- **Cairo → numpy → Pygame** pipeline for display output
- **JSON-defined themes** with schema validation, stored in SQLite + default files
- **Fullscreen by default** on all platforms (including Windows), `--windowed` CLI flag for development

---

### Phase 1: Core Clock Engine *(foundation — everything depends on this)*

1. Set up Python project (`pyproject.toml`, `requirements.txt`, package structure)
2. Implement `src/clock/display.py` — Pygame display abstraction (720×720, fullscreen on all platforms by default, `--windowed` flag for development)
3. Implement `src/clock/renderer.py` — Cairo rendering pipeline: ImageSurface → draw → convert to Pygame surface via numpy, pass active alarms for indicator rendering
4. Implement `src/clock/face.py` — Background (solid / gradient / image), gradients support radial + linear with configurable angle + multi-stop colors, hour markers (lines/dots/roman/arabic/custom labels/none), minute markers (line or dot style), marker shadows, alarm indicator dots/triangles at alarm-time positions
5. Implement `src/clock/hands.py` — Tapered hour/minute hands with drop shadows + optional glow (per-hand glow color), thin second hand with configurable counterweight (toggle + radius), image-based hand support
6. Implement `src/clock/effects.py` — Shadow rendering, glow effects (used by hands)
7. Implement `src/clock/engine.py` — Main loop: get time → render → display, dynamic FPS (1fps normal, 30fps during alarm), alarm list tracking for face indicators, graceful shutdown
8. Implement `src/main.py` — Entry point with `--windowed` and `--port` CLI args

**Verify:** Clock window appears on Windows with smooth anti-aliased hands moving correctly.

### Phase 2: Theme System *(parallel with late Phase 1)*

1. Define theme JSON schema in `src/themes/schema.py` — background (solid/gradient/image, gradient_type, gradient_angle, color_stops), markers (hour_style incl. custom labels, hour_shadow, minute_style line/dot, minute_dot_radius, minute_shadow, font_size), hands (style/color/width/length/shadow/glow/glow_color per hand, second hand counterweight toggle + radius, second hand image), alarm_indicators (visible/color/size), center dot config
2. Implement `src/themes/manager.py` — Theme CRUD, load from JSON/SQLite, validate, set active
3. Create 3 default themes: **Classic** (dark bg, white hands, roman numerals), **Modern** (gradient bg, slim hands, line markers), **Minimal** (black bg, no markers, thin hands)
4. Wire themes into renderer — all drawing reads from active theme config
5. Implement `src/config/settings.py` — SQLite database for active theme, timezone, alarms, power settings

**Verify:** Switch themes → visual changes confirmed. Round-trip save/load works.

### Phase 3: Web Interface & API *(depends on Phase 1 + 2)*

1. Implement Flask app factory in `src/web/app.py`
2. Build REST API (`src/web/api.py`):
   - `GET/PUT /api/settings` — timezone, active theme
   - `GET/POST/PUT/DELETE /api/themes` — theme CRUD
   - `GET /api/themes/<name>/export` — download theme as JSON file
   - `POST /api/themes/import` — upload/import theme JSON
   - `GET/POST/PUT/DELETE /api/alarms` — alarm management (incl. animation_shape, animation_color, animation_speed per alarm)
   - `GET /api/sounds` — list available alarm sounds
   - `POST /api/sounds` — upload custom alarm sound (WAV, OGG, MP3)
   - `POST /api/uploads` — custom hand/background images
   - `GET /api/timezones?q=` — searchable timezone list with city names + GMT±HH:MM offsets
   - `GET /api/status` — current state
3. Build web UI templates:
   - Dashboard (`index.html`) — timezone selector w/ searchable dropdown, status
   - Theme editor (`themes.html`) — full editor for all schema fields: background type/gradient/angle/stops/image, marker style/shadow/custom labels/font size, minute style/dot/shadow, hand style/color/shadow/glow/glow_color, counterweight config, alarm indicators config, center dot, live canvas preview, theme import/export buttons
   - Alarm manager (`alarms.html`) — alarm CRUD w/ animation shape/color/speed selectors, sound picker per alarm, sound upload
4. Implement `static/js/clock-preview.js` — Canvas-based live preview with cached static layer (offscreen canvas for face + markers), `requestAnimationFrame` for smooth 1fps updates, supports all theme features (linear gradients w/ angle, custom labels, minute dots, marker shadows, glow effects, configurable counterweight)
5. Start Flask in background thread from `main.py`
6. Timezone support via Python `zoneinfo` module

**Verify:** Access web UI from another device → change theme → clock updates within seconds. All API endpoints respond correctly.

### Phase 4: Alarms & Power Management *(depends on Phase 3)*

1. Implement `src/alarms/scheduler.py` — One-time and recurring alarms via threading, stored in SQLite; feeds alarm list to engine for face indicator rendering; passes per-alarm animation_shape/color/speed to visual overlay
2. Implement `src/alarms/audio.py` — Play sounds via `pygame.mixer`, support custom uploaded sounds (WAV/OGG/MP3)
3. Implement `src/alarms/visual.py` — On-screen overlay with 3 animation shapes (ring w/ inner ring, flash full-screen pulse, border_glow radial gradient), configurable color and speed (slow/normal/fast)
4. Implement `src/power/manager.py` — Display brightness control (sysfs on Pi), scheduled dimming/sleep, optional battery monitoring
5. Add alarm + power API endpoints and web UI pages
6. DB migration: alarms table gains `animation_shape`, `animation_color`, `animation_speed` columns (auto-migrated via ALTER TABLE)

**Verify:** Alarm triggers at correct time with audio + visual. Display dims on schedule.

### Phase 5: Deployment & Documentation *(depends on all above)*

1. Create `scripts/install.sh` — system deps, venv, pip install, systemd config, auto-start
2. Create `piclock.service` systemd unit (Restart=always, After=network.target)
3. Write `README.md` — hardware assembly, install guide, web UI usage, API docs, theme customization, troubleshooting

**Verify:** Fresh Pi Zero → `install.sh` → clock starts on boot, web UI accessible.

---

### Project Structure
```
piclock3/
├── src/
│   ├── main.py
│   ├── clock/        (engine, renderer, hands, face, display, effects)
│   ├── themes/       (manager, schema)
│   ├── web/          (app, api, views, templates/, static/)
│   ├── alarms/       (scheduler, audio, visual)
│   ├── power/        (manager)
│   └── config/       (settings)
├── data/
│   ├── themes/       (classic.json, modern.json, minimal.json)
│   ├── sounds/       (default alarm sounds)
│   └── uploads/      (user-uploaded images)
├── tests/
├── scripts/install.sh
├── piclock.service
├── requirements.txt
├── pyproject.toml
└── README.md
```

### Further Considerations

1. **Display assumes HDMI** — The Waveshare 4" round display connects via HDMI and uses built-in Pi display drivers. No special driver installation needed; just standard `config.txt` resolution/rotation settings.
2. **Image upload format** — Recommend PNG and JPG support, max 1MB for backgrounds. Second hand image support via theme `hands.second.image` field.
3. **Web preview fidelity** — The JavaScript Canvas preview won't be pixel-identical to Cairo output, but close enough for configuration purposes. Static layer is cached in an offscreen canvas; only hands redraw each second.
4. **Alarm animation performance** — Engine runs at 1fps normally. When an alarm triggers, FPS bumps to 30 for smooth overlay animation. Reverts to 1fps on alarm dismiss.
5. **Gradient rendering** — Both radial and linear gradients are supported. Linear gradients use a configurable angle. Multi-stop colors are supported (add/remove stops in theme editor).
6. **Theme portability** — Themes can be exported as JSON files and imported on other PiClock3 instances. The `merge_with_defaults()` system ensures old themes remain compatible when new fields are added.
7. **Sound management** — Custom alarm sounds can be uploaded via the web UI. Supported formats: WAV, OGG, MP3. Each alarm can have its own sound file.
