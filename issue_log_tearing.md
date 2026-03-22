# Pi Configuration Guide — Tear-Free Rendering

## Root Cause

The tearing is caused by **X11/Xorg compositing**, not the rendering pipeline itself.
The evidence:

- Rotating the screen moves the tearing boundary to the physical "top" → classic **scanout tearing**
- `/usr/lib/xorg/Xorg` at 100% CPU → **Xorg is the bottleneck**, compositing every frame to the display
- Window dragging shows less tearing → desktop compositor handles partial updates more efficiently than full-screen redraws
- `pipewire-pulse` at 10-15% → wasted CPU on unused audio daemon

**Why X11 tears:** Pygame renders into an X11 window → Xorg composites that window onto the framebuffer → there is no vsync synchronization between Xorg's compositing pass and the display's scanout. The display physically scans top-to-bottom at ~60Hz, so if the framebuffer is updated mid-scan, you see a horizontal tear line.

## The Fix: KMS/DRM Mode

SDL2 supports a **KMS/DRM backend** (`SDL_VIDEODRIVER=kmsdrm`) that bypasses X11 entirely. This gives:

- **Direct framebuffer access** — no Xorg overhead, no compositing
- **Hardware page flipping with vsync** — `drmModePageFlip` waits for vertical blank
- **Zero tearing** — the display only ever shows fully-rendered frames
- **~0% Xorg CPU** — it's not running at all

The `--kms` flag has been added to the app, and `install.sh --kms` generates the appropriate systemd service.

## Setup Steps

### 1. Re-install with KMS/DRM mode

```bash
sudo bash ~/piclock/scripts/install.sh --kms
```

This generates a service that runs with `--kms` and targets `multi-user.target` instead of `graphical.target`. It also adds the user to the `video` and `render` groups for DRM device access.

### 2. Boot to console (no desktop) — REQUIRED

The KMS/DRM backend needs exclusive DRM master access. lightdm (the display manager) holds DRM master when running, making `kmsdrm not available` even when the device exists. It must not be running.

```bash
sudo systemctl set-default multi-user.target
sudo reboot
```

The piclock service is configured for `WantedBy=multi-user.target` so it starts automatically after console boot. Do not run `sudo systemctl start lightdm` or `sudo systemctl set-default graphical.target` while in KMS mode.

### 3. Disable unused audio services (~10-15% CPU saved)

```bash
# Run as the pi user (not root):
systemctl --user disable pipewire-pulse.service pipewire.service wireplumber.service
systemctl --user stop pipewire-pulse.service pipewire.service wireplumber.service
```

### 4. Verify /boot/config.txt

Ensure the KMS driver overlay is enabled (default on modern Raspberry Pi OS):

```
dtoverlay=vc4-kms-v3d
```

For the 720×720 display, the existing HDMI settings should work as-is. If you need to force the mode:

```
hdmi_group=2
hdmi_mode=87
hdmi_cvt=720 720 60 1 0 0 0
```

### 5. Reboot and verify

```bash
sudo reboot
# After reboot, check the service:
sudo journalctl -u piclock -f
# Should show: "Display: 720x720 via KMSDRM (fullscreen)"
```

## Switching Back to X11 Mode

If you need the desktop back (e.g., for development):

```bash
sudo systemctl set-default graphical.target
sudo bash ~/piclock/scripts/install.sh   # without --kms
sudo reboot
```

## Summary of Modes

| Mode | Install command | Tearing | Desktop | Xorg CPU |
|------|----------------|---------|---------|----------|
| X11 (default) | `install.sh` | Yes (scanout) | Required | 60-100% |
| KMS/DRM | `install.sh --kms` | None (vsync'd) | Not needed | 0% |

---
