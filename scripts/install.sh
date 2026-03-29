#!/usr/bin/env bash
# PiClock Installation Script
# Supports: Raspberry Pi OS, Debian, Ubuntu
# Usage:    sudo bash scripts/install.sh [--kms]
#
# Installs dependencies, creates a venv, and sets up a systemd service
# that runs PiClock directly from this project directory.
#
# Options:
#   --kms   Use KMS/DRM mode (bypass X11 for tear-free rendering).
#           The machine should boot to console (multi-user.target), not desktop.
#           Primarily useful on Raspberry Pi with a directly-connected display.
#   (default) Use X11 mode — requires desktop/graphical session.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Parse options
USE_KMS=false
for arg in "$@"; do
    case "$arg" in
        --kms) USE_KMS=true ;;
    esac
done

# Determine the real user (not root) when run via sudo
if [ -n "$SUDO_USER" ]; then
    SERVICE_USER="$SUDO_USER"
else
    SERVICE_USER="$USER"
fi
SERVICE_HOME=$(eval echo "~$SERVICE_USER")
SERVICE_UID=$(id -u "$SERVICE_USER")

# Detect distro
DISTRO="unknown"
if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRO="$ID"
fi

echo "=== PiClock Installer ==="
echo ""
echo "Project directory: $PROJECT_DIR"
echo "Service user:      $SERVICE_USER"
echo "Detected distro:   $DISTRO"
if [ "$USE_KMS" = true ]; then
    echo "Display mode:      KMS/DRM (bypass X11, tear-free)"
else
    echo "Display mode:      X11 (requires desktop session)"
fi
echo ""

# Check we're on Linux
if [ "$(uname)" != "Linux" ]; then
    echo "This installer is designed for Debian-based Linux (Raspberry Pi OS, Debian, Ubuntu)."
    echo "For development on other platforms, use: pip install -r requirements.txt"
    exit 1
fi

# Check for apt (Debian-based)
if ! command -v apt-get &>/dev/null; then
    echo "ERROR: apt-get not found. This installer requires a Debian-based distro"
    echo "(Raspberry Pi OS, Debian, or Ubuntu)."
    exit 1
fi

# Check for root (needed for apt and systemd)
if [ "$(id -u)" -ne 0 ]; then
    echo "Please run with sudo: sudo bash $0"
    exit 1
fi

# Detect Raspberry Pi vs other SBCs
IS_RPI=false
if grep -qi "raspberry pi" /proc/device-tree/model 2>/dev/null; then
    IS_RPI=true
    echo "Board:             Raspberry Pi"
else
    echo "Board:             Generic SBC / $(cat /proc/device-tree/model 2>/dev/null || echo 'unknown')"
fi
echo ""

# --- Step 1: System dependencies ---
echo "[1/5] Installing system dependencies..."
# Allow partial repo failures (e.g. stale backports on older Debian)
apt-get update || echo "  WARNING: apt-get update had errors — continuing anyway."

SYSTEM_DEPS=(
    python3
    python3-venv
    python3-pip
    libcairo2-dev
    pkg-config
    python3-dev
    libsdl2-dev
    libsdl2-image-dev
    libsdl2-mixer-dev
    libsdl2-ttf-dev
    git
)

if [ "$USE_KMS" = true ]; then
    # chvt is needed for VT switching in the systemd service
    SYSTEM_DEPS+=(kbd)
    if [ "$IS_RPI" = true ]; then
        # On Raspberry Pi, the system pygame is built against system SDL2 with KMS/DRM.
        # The pip wheel bundles its own SDL2 without kmsdrm on Pi, so we use the system one.
        SYSTEM_DEPS+=(python3-pygame)
    fi
fi

apt-get install -y "${SYSTEM_DEPS[@]}"
echo ""

# --- Step 2: Virtual environment ---
echo "[2/5] Setting up Python virtual environment..."

if [ "$USE_KMS" = true ] && [ "$IS_RPI" = true ]; then
    # --system-site-packages lets the venv see python3-pygame (which has KMS/DRM on Pi)
    sudo -u "$SERVICE_USER" python3 -m venv --system-site-packages "$PROJECT_DIR/venv"
else
    sudo -u "$SERVICE_USER" python3 -m venv "$PROJECT_DIR/venv"
fi

echo "  Upgrading pip..."
sudo -u "$SERVICE_USER" "$PROJECT_DIR/venv/bin/pip" install --upgrade pip
echo "  Installing Python packages..."
sudo -u "$SERVICE_USER" "$PROJECT_DIR/venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt"

if [ "$USE_KMS" = true ] && [ "$IS_RPI" = true ]; then
    # On Pi, requirements.txt installs pygame (pip wheel) which would shadow the system
    # python3-pygame that has KMS/DRM support. Remove it so the system package is used.
    echo "  Removing pip pygame (system package with KMS/DRM will be used instead)..."
    sudo -u "$SERVICE_USER" "$PROJECT_DIR/venv/bin/pip" uninstall pygame -y 2>/dev/null || true
elif [ "$USE_KMS" = true ]; then
    # The pip pygame wheel bundles its own SDL2 which lacks kmsdrm/fbdev drivers.
    # Rebuild pygame from source so it links against the system SDL2 (which has them).
    echo "  Rebuilding pygame from source (linking against system SDL2 with kmsdrm)..."
    sudo -u "$SERVICE_USER" "$PROJECT_DIR/venv/bin/pip" install pygame --no-binary pygame --force-reinstall
fi
echo ""

# --- Step 3: Data directories ---
echo "[3/5] Creating data directories..."
sudo -u "$SERVICE_USER" mkdir -p "$PROJECT_DIR/data/themes"
sudo -u "$SERVICE_USER" mkdir -p "$PROJECT_DIR/data/sounds"
sudo -u "$SERVICE_USER" mkdir -p "$PROJECT_DIR/data/uploads"
echo ""

# --- Step 4: Ensure project ownership ---
echo "[4/5] Setting file ownership..."
chown -R "$SERVICE_USER":"$SERVICE_USER" "$PROJECT_DIR"
echo ""

# --- Step 5: systemd service ---
echo "[5/5] Installing systemd service..."

# Allow the service user to reboot/poweroff/set-time without a password
SUDOERS_FILE="/etc/sudoers.d/piclock"
SYSTEMCTL_PATH=$(which systemctl)
TIMEDATECTL_PATH=$(which timedatectl 2>/dev/null || echo "/usr/bin/timedatectl")
{
    echo "${SERVICE_USER} ALL=(ALL) NOPASSWD: ${SYSTEMCTL_PATH} reboot, ${SYSTEMCTL_PATH} poweroff"
    echo "${SERVICE_USER} ALL=(ALL) NOPASSWD: ${TIMEDATECTL_PATH} set-ntp true, ${TIMEDATECTL_PATH} set-ntp false"
    echo "${SERVICE_USER} ALL=(ALL) NOPASSWD: ${TIMEDATECTL_PATH} set-time *"
} > "$SUDOERS_FILE"
chmod 0440 "$SUDOERS_FILE"

if [ "$USE_KMS" = true ]; then
    # KMS/DRM mode: runs from a virtual console, no X11 needed.
    # Grant device access via video+render groups (needed for /dev/dri/* and /dev/fb*).
    usermod -aG video "$SERVICE_USER" 2>/dev/null || true
    usermod -aG render "$SERVICE_USER" 2>/dev/null || true
    usermod -aG input "$SERVICE_USER" 2>/dev/null || true
    usermod -aG tty "$SERVICE_USER" 2>/dev/null || true

    # Disable getty on tty1 so PiClock can own the VT
    echo "  Freeing tty1 for PiClock..."
    systemctl stop getty@tty1.service 2>/dev/null || true
    systemctl disable getty@tty1.service 2>/dev/null || true

    # Diagnostics: check what display devices are available
    echo "  Display devices:"
    if ls /dev/dri/card* 2>/dev/null; then
        echo "    DRI/KMS devices found."
    else
        echo "    No /dev/dri/card* found — kmsdrm driver won't work."
    fi
    if [ -e /dev/fb0 ]; then
        echo "    Framebuffer /dev/fb0 found — fbdev driver available as fallback."
    else
        echo "    No /dev/fb0 found."
    fi
    echo ""

    cat > /etc/systemd/system/piclock.service << EOF
[Unit]
Description=PiClock Analogue Clock (KMS/DRM)
After=multi-user.target
Wants=multi-user.target
# Ensure getty is not holding tty1
Conflicts=getty@tty1.service

[Service]
Type=simple
User=${SERVICE_USER}
SupplementaryGroups=video render input tty
WorkingDirectory=${PROJECT_DIR}

# Switch to VT1 and give the process a real TTY (SDL2 kmsdrm needs this)
# + prefix runs as root (chvt needs CAP_SYS_TTY_CONFIG)
ExecStartPre=+/bin/chvt 1
TTYPath=/dev/tty1
StandardInput=tty-force
TTYReset=yes
TTYVHangup=yes

Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

ExecStart=${PROJECT_DIR}/venv/bin/python -m src.main --kms
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

else
    # X11 mode: requires a running desktop session.
    cat > /etc/systemd/system/piclock.service << EOF
[Unit]
Description=PiClock Analogue Clock
After=graphical.target
Wants=graphical.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${PROJECT_DIR}
Environment=DISPLAY=:0
Environment=XAUTHORITY=${SERVICE_HOME}/.Xauthority
Environment=XDG_RUNTIME_DIR=/run/user/${SERVICE_UID}
ExecStartPre=/bin/sleep 3
ExecStart=${PROJECT_DIR}/venv/bin/python -m src.main
Restart=always
RestartSec=5

[Install]
WantedBy=graphical.target
EOF
fi

systemctl daemon-reload
systemctl enable piclock.service

if [ "$USE_KMS" = true ]; then
    # Switch boot target to console — this is REQUIRED for KMS/DRM.
    # The display manager holds DRM master when running, which prevents
    # KMS/DRM from initialising even with the correct permissions.
    echo "  Switching boot target to multi-user (console)..."
    systemctl set-default multi-user.target
    # Stop display manager so the service start below succeeds immediately
    for dm in lightdm gdm3 gdm sddm; do
        systemctl stop "$dm" 2>/dev/null || true
    done
fi

systemctl start piclock.service

# --- Optional: replace Raspberry Pi boot splash ---
if [ "$IS_RPI" = true ] && [ -f "$PROJECT_DIR/data/boot/boot.png" ]; then
    SPLASH_DIR="/usr/share/plymouth/themes/pix"
    if [ -d "$SPLASH_DIR" ]; then
        echo ""
        echo "Replacing Raspberry Pi boot splash with PiClock image..."
        cp "$SPLASH_DIR/splash.png" "$SPLASH_DIR/splash.png.bak" 2>/dev/null || true
        cp "$PROJECT_DIR/data/boot/boot.png" "$SPLASH_DIR/splash.png"
        echo "  Boot splash replaced (original backed up to splash.png.bak)."
    fi
fi

# --- Optional: disable Radxa onboard heartbeat LED ---
if [ -e /sys/class/leds/board-led/trigger ] && grep -qi "radxa" /proc/device-tree/model 2>/dev/null; then
    echo ""
    read -r -p "Disable the onboard heartbeat LED? [y/N] " DISABLE_LED
    if [[ "$DISABLE_LED" =~ ^[Yy]$ ]]; then
        cat > /etc/systemd/system/disable-led.service << 'EOF'
[Unit]
Description=Disable board LED heartbeat

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'echo none > /sys/class/leds/board-led/trigger'

[Install]
WantedBy=multi-user.target
EOF
        systemctl daemon-reload
        systemctl enable --now disable-led.service
        echo "  Heartbeat LED disabled."
    fi
fi

echo ""
echo "=== Installation Complete ==="
echo "PiClock is now running and will start on boot."
echo "Web interface: http://$(hostname -I | awk '{print $1}'):8080"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status piclock    — Check status"
echo "  sudo systemctl restart piclock   — Restart"
echo "  sudo systemctl stop piclock      — Stop"
echo "  sudo journalctl -u piclock -f    — View logs"
echo ""
if [ "$USE_KMS" = true ]; then
    echo "Running in KMS/DRM mode (tear-free, no desktop required)."
    echo "Boot target set to multi-user (console) — desktop will not start on next boot."
    echo "To switch back to X11 mode: sudo bash $PROJECT_DIR/scripts/install.sh"
    echo ""
    echo "To disable unused audio services (saves ~10-15% CPU):"
    echo "  systemctl --user disable pipewire-pulse.service pipewire.service wireplumber.service"
else
    echo "Running in X11 mode."
    echo "To switch to tear-free KMS/DRM mode: sudo bash $PROJECT_DIR/scripts/install.sh --kms"
fi
echo ""
echo "To update later:  sudo bash $PROJECT_DIR/scripts/update.sh"
