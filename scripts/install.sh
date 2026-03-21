#!/usr/bin/env bash
# PiClock3 Installation Script
# Run on Raspberry Pi: sudo bash install.sh

set -e

INSTALL_DIR="/opt/piclock3"
SERVICE_USER="pi"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== PiClock3 Installer ==="
echo ""

# Check we're on a Pi (or at least Linux)
if [ "$(uname)" != "Linux" ]; then
    echo "This installer is designed for Raspberry Pi / Linux."
    echo "For development on other platforms, use: pip install -r requirements.txt"
    exit 1
fi

# Install system dependencies
echo "[1/5] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq \
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
    sqlite3 \
    > /dev/null

# Copy project files
echo "[2/5] Installing PiClock3 to ${INSTALL_DIR}..."
mkdir -p "$INSTALL_DIR"
cp -r "$PROJECT_DIR"/* "$INSTALL_DIR/"
chown -R "$SERVICE_USER":"$SERVICE_USER" "$INSTALL_DIR"

# Create virtual environment and install Python packages
echo "[3/5] Setting up Python virtual environment..."
sudo -u "$SERVICE_USER" python3 -m venv "$INSTALL_DIR/venv"
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q

# Create data directories
echo "[4/5] Creating data directories..."
sudo -u "$SERVICE_USER" mkdir -p "$INSTALL_DIR/data/themes"
sudo -u "$SERVICE_USER" mkdir -p "$INSTALL_DIR/data/sounds"
sudo -u "$SERVICE_USER" mkdir -p "$INSTALL_DIR/data/uploads"

# Install systemd service
echo "[5/5] Installing systemd service..."
cat > /etc/systemd/system/piclock.service << EOF
[Unit]
Description=PiClock3 Analogue Clock
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
Environment=DISPLAY=:0
ExecStart=${INSTALL_DIR}/venv/bin/python -m src.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
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
