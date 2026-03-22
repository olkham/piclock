#!/usr/bin/env bash
# PiClock3 Installation Script
# Run on Raspberry Pi: sudo bash scripts/install.sh
# Installs dependencies, creates a venv, and sets up a systemd service
# that runs PiClock3 directly from this project directory.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

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
echo "To update later:  sudo bash $PROJECT_DIR/scripts/update.sh"
