This project is a simple analogue clock face that will run on a pi zero with a circular display.
The clock face is designed to be minimalist and easy to read, with clear hour and minute markers. The clock will also include a second hand for added functionality.

Requirements:
- Raspberry Pi Zero or similar
- Circular display (e.g., Waveshare 4" round HDMI 720×720 — no special drivers required)
- Automatically start the clock face on boot (fullscreen by default, `--windowed` flag for development)
- Web interface to set the time and customize the clock face (e.g., change colors, add/remove second hand)
- API for external applications to interact with the clock (e.g., set alarms, change time)
- Support for multiple time zones selectable through the web interface / API (searchable dropdown with GMT offsets)
- Power management features to ensure the clock runs efficiently and can operate on battery power if needed
- Modular design to allow for easy updates and additions of new features in the future

Features:
- Clear and minimalist design for easy readability
- Customizable clock face through a web interface with live canvas preview
- API for external applications to interact with the clock
- Multiple styles (themes) can be created, saved, exported, and imported
  - Different color schemes
  - Different hand styles (tapered, classic) with per-hand shadow and glow toggles
    - Glow color configurable per hand (hour, minute, second)
  - Different marker styles (lines, dots, roman numerals, arabic numerals, custom labels, none)
    - Custom hour labels: 12 user-defined strings
    - Minute markers: line or dot style with configurable radius
    - Marker shadow toggles for both hour and minute markers
    - Configurable size, width, length, and color for all marker types
  - Second hand features
    - Configurable counterweight (toggle + radius)
    - Image support for second hand (upload custom image)
  - Configurable clock face background
    - Solid color
    - Gradient: radial or linear with configurable angle and multi-stop color support
    - Image: upload a PNG/JPG background
  - Alarm indicators on clock face (dots/triangles at alarm-time positions, toggle + color + size)
  - Center dot configuration (toggle, color, radius)
  - Theme export (download JSON) and import (upload JSON file)
- Alarm system
  - Per-alarm animation style: ring, flash, border_glow
  - Per-alarm animation color and speed (slow, normal, fast)
  - Custom alarm sound upload (WAV, OGG, MP3) and picker per alarm
  - Dynamic FPS: 1 fps normally, 30 fps during alarm animation
  - Repeat days or one-time alarms
  - Per-alarm sound enable/disable (silent alarms)
  - Configurable animation duration per alarm
  - Snooze and dismiss from web interface
- Agenda mode
  - Pie/donut chart overlay showing day's events on the clock face
  - Events with title, start/end time, color, and recurring days
  - Configurable inner and outer radius (0-100%) for full pie or donut chart
  - Configurable opacity for event slices
  - CRUD management via web UI and API
- Timezone selector
  - Searchable dropdown showing city names with GMT±HH:MM offsets
  - Filters via `/api/timezones?q=` search query

Tech Stack:
- Python 3.11 — PyCairo vector rendering, Pygame display, Flask web server, SQLite storage
- Single-process: Cairo → NumPy → Pygame surface pipeline, Flask runs in daemon thread
- AlpineJS + Tailwind CSS for web UI, canvas-based live clock preview (cached static layer + requestAnimationFrame)

Build Guide:
Uses Python with Flask for the web interface and API. PyCairo for vector rendering, Pygame for display output. Cross-development on Windows, deploy to Raspberry Pi Zero.

Other files:
- Build an installation script to set up the necessary dependencies and configure the clock to start on boot
- Create a README file with instructions on how to set up and use the clock, as well as any additional features or customization options available through the web interface and API. Include troubleshooting tips and contact information for support.
