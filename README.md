# PiClock3

A beautiful analogue clock face for Raspberry Pi Zero with a Waveshare 4" round HDMI display (720×720). Features smooth anti-aliased vector rendering, customizable themes, a web configuration interface, alarms, and power management.

## Hardware Requirements

- Raspberry Pi Zero (or any Pi model)
- Waveshare 4" Round HDMI Display (720×720)
- HDMI cable / adapter
- Power supply (5V for Pi)
- Optional: speaker/buzzer for alarm audio

## Quick Start

### Development (Windows/Mac/Linux)

```bash
# Clone the project
cd piclock3

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Run the clock
python -m src.main
```

The clock window will open at 720×720 pixels. The web interface will be available at `http://localhost:8080`.

### Raspberry Pi Installation

```bash
# Copy the project to your Pi, then:
sudo bash scripts/install.sh
```

This will:
1. Install system dependencies (Cairo, SDL2, Python)
2. Create a virtual environment with Python packages
3. Set up a systemd service for auto-start on boot
4. Start the clock immediately

## Web Interface

Access the web interface from any device on the same network:

```
http://<pi-ip-address>:8080
```

### Dashboard
- View current status (active theme, timezone)
- Quick theme switching
- Timezone selection
- Live clock preview

### Theme Editor
- Create, edit, and delete themes
- Customize background (solid color or gradient)
- Configure hour markers (lines, dots, roman numerals, arabic numerals, or none)
- Adjust hand styles (tapered or classic), colors, widths, and lengths
- Toggle second hand visibility
- Live Canvas preview of changes

### Alarm Manager
- Add one-time or recurring alarms
- Set alarm labels
- Choose repeat days
- Enable/disable individual alarms

## REST API

All endpoints accept and return JSON.

### Settings
- `GET /api/settings` — Get all settings
- `PUT /api/settings` — Update settings (JSON body: `{"timezone": "America/New_York"}`)

### Themes
- `GET /api/themes` — List all themes and active theme
- `GET /api/themes/<name>` — Get theme details
- `POST /api/themes` — Create a new theme
- `PUT /api/themes/<name>` — Update a theme
- `DELETE /api/themes/<name>` — Delete a theme
- `POST /api/themes/<name>/activate` — Set as active theme

### Alarms
- `GET /api/alarms` — List all alarms
- `POST /api/alarms` — Create alarm (`{"time": "07:00", "label": "Wake up", "days": "Mon,Tue,Wed,Thu,Fri"}`)
- `PUT /api/alarms/<id>` — Update alarm
- `DELETE /api/alarms/<id>` — Delete alarm

### Uploads
- `POST /api/uploads` — Upload an image file (PNG, JPG, SVG) for custom clock hands or backgrounds

### Other
- `GET /api/timezones` — List available timezones
- `GET /api/status` — Get current clock status

## Themes

Three built-in themes are included:

- **Classic** — Dark gradient background, roman numerals, white tapered hands, red second hand
- **Modern** — Deep blue gradient, line markers, blue-tinted slim hands
- **Minimal** — Pure black, no markers, thin white classic hands, no second hand

### Theme JSON Structure

```json
{
    "name": "My Theme",
    "background": {
        "type": "gradient",
        "color": "#1a1a2e",
        "colors": ["#1a1a2e", "#16213e"]
    },
    "markers": {
        "hour_style": "roman",
        "hour_color": "#e0e0e0",
        "show_minutes": true,
        "minute_color": "#555555"
    },
    "hands": {
        "hour": { "style": "tapered", "color": "#ffffff", "width": 14, "length": 0.45 },
        "minute": { "style": "tapered", "color": "#ffffff", "width": 10, "length": 0.65 },
        "second": { "visible": true, "color": "#ff4444", "length": 0.72 }
    },
    "center_dot": { "visible": true, "color": "#ffffff", "radius": 7 }
}
```

## Command Line Options

```
python -m src.main [options]

Options:
  --no-web          Disable the web interface
  --port PORT       Web interface port (default: 8080)
  --host HOST       Web interface host (default: 0.0.0.0)
  --theme NAME      Set initial theme
  --timezone TZ     Set timezone (e.g., America/New_York)
```

## Power Management

Configure via the web API:

```bash
# Set dim schedule (dim at 10pm, brighten at 7am)
curl -X PUT http://localhost:8080/api/settings \
  -H "Content-Type: application/json" \
  -d '{"dim_start": "22:00", "dim_end": "07:00", "dim_brightness": "30", "brightness": "100"}'
```

## Troubleshooting

### Clock doesn't start
- Check the service status: `sudo systemctl status piclock`
- View logs: `sudo journalctl -u piclock -f`
- Ensure HDMI display is connected and configured in `/boot/config.txt`

### Web interface not accessible
- Verify the Pi's IP: `hostname -I`
- Check firewall: `sudo ufw allow 8080`
- Ensure `--no-web` is not set

### Display appears stretched or off-center
- Edit `/boot/config.txt` to set the correct resolution:
  ```
  hdmi_group=2
  hdmi_mode=87
  hdmi_cvt=720 720 60
  ```

### No sound for alarms
- Check audio output: `aplay -l`
- Place `.wav`, `.ogg`, or `.mp3` files in `data/sounds/`

## Project Structure

```
piclock3/
├── src/
│   ├── main.py              — Entry point
│   ├── clock/               — Clock rendering engine
│   ├── themes/              — Theme management
│   ├── web/                 — Flask web app + API
│   ├── alarms/              — Alarm scheduler + audio
│   ├── power/               — Brightness + power management
│   └── config/              — Settings (SQLite)
├── data/                    — Themes, sounds, uploads
├── scripts/install.sh       — Pi installation script
└── piclock.service          — systemd unit file
```

## License

MIT
