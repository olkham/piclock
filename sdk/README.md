# PiClock3 Python SDK

Programmatic control of your PiClock3 device from any Python script.

## Install

```bash
pip install ./sdk
# Or for development:
pip install -e ./sdk
```

## Quick Start

```python
from piclock import PiClock

clock = PiClock("192.168.1.50")  # your Pi's IP

# Change timezone
clock.set_timezone("America/New_York")

# Set background image
clock.set_background_image("photo.png")

# Create an alarm
clock.create_alarm("07:30", label="Wake up", days="Mon,Tue,Wed,Thu,Fri")

# Adjust brightness
clock.set_power(brightness=80, dim_brightness=20, dim_start="22:00", dim_end="07:00")
```

## Examples

See `sdk/examples/` for complete scripts:

- **clock_map.py** — Set your clock to show a map tile and timezone for any city

```bash
pip install ./sdk[examples]
python sdk/examples/clock_map.py "New York City" --host 192.168.1.50
python sdk/examples/clock_map.py "Tokyo" --host piclock.local
```
