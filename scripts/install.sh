#!/usr/bin/env bash
# PiClock3 Installation Script
# Run on Raspberry Pi: sudo bash scripts/install.sh
# Installs dependencies, creates a venv, and sets up a systemd service
# that runs PiClock3 directly from this project directory.
#
# Options:
#   --kms   Use KMS/DRM mode (bypass X11 for tear-free rendering).
#           The Pi should boot to console (multi-user.target), not desktop.
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

echo "=== PiClock3 Installer ==="
echo ""
echo "Project directory: $PROJECT_DIR"
echo "Service user:      $SERVICE_USER"
if [ "$USE_KMS" = true ]; then
    echo "Display mode:      KMS/DRM (bypass X11, tear-free)"
else
    echo "Display mode:      X11 (requires desktop session)"
fi
echo ""

# Check we're on a Pi (or at least Linux)
if [ "$(uname)" != "Linux" ]; then
    echo "This installer is designed for Raspberry Pi / Linux."
    echo "For development on other platforms, use: pip install -r requirements.txt"
    exit 1
fi

# Check for root (needed for apt and systemd)
if [ "$(id -u)" -ne 0 ]; then
    echo "Please run with sudo: sudo bash $0"
    exit 1
fi

# --- Step 1: System dependencies ---
echo "[1/5] Installing system dependencies..."
apt-get update
apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    libcairo2-dev \
    pkg-config \
    python3-dev \
    libsdl2-dev \
    libsdl2-image-dev \
    libsdl2-mixer-dev \
    libsdl2-ttf-dev \
    git
echo ""

# --- Step 2: Virtual environment ---
echo "[2/5] Setting up Python virtual environment..."
sudo -u "$SERVICE_USER" python3 -m venv "$PROJECT_DIR/venv"
echo "  Upgrading pip..."
sudo -u "$SERVICE_USER" "$PROJECT_DIR/venv/bin/pip" install --upgrade pip
echo "  Installing Python packages..."
sudo -u "$SERVICE_USER" "$PROJECT_DIR/venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt"
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

if [ "$USE_KMS" = true ]; then
    # KMS/DRM mode: runs from a virtual console, no X11 needed.
    # Grant DRM device access via video+render groups.
    usermod -aG video "$SERVICE_USER" 2>/dev/null || true
    usermod -aG render "$SERVICE_USER" 2>/dev/null || true

    cat > /etc/systemd/system/piclock.service << EOF
[Unit]
Description=PiClock3 Analogue Clock (KMS/DRM)
After=multi-user.target
Wants=multi-user.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${PROJECT_DIR}
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
Description=PiClock3 Analogue Clock
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
systemctl start piclock.service

echo ""
echo "=== Installation Complete ==="
echo "PiClock3 is now running and will start on boot."
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
    echo "To switch to X11 mode: sudo bash $PROJECT_DIR/scripts/install.sh"
    echo ""
    echo "Recommended: boot to console instead of desktop to free resources:"
    echo "  sudo raspi-config  →  System Options  →  Boot / Auto Login  →  Console Autologin"
    echo ""
    echo "To disable unused audio services (saves ~10-15% CPU):"
    echo "  systemctl --user disable pipewire-pulse.service pipewire.service wireplumber.service"
else
    echo "Running in X11 mode."
    echo "To switch to tear-free KMS/DRM mode: sudo bash $PROJECT_DIR/scripts/install.sh --kms"
fi
echo ""
echo "To update later:  sudo bash $PROJECT_DIR/scripts/update.sh"
