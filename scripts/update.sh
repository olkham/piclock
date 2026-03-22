#!/usr/bin/env bash
# PiClock3 Update Script
# Usage: sudo bash scripts/update.sh
# Pulls latest code, installs new dependencies, and restarts the service.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Determine the real user (not root) when run via sudo
if [ -n "$SUDO_USER" ]; then
    SERVICE_USER="$SUDO_USER"
else
    SERVICE_USER="$USER"
fi

echo "=== PiClock3 Updater ==="
echo ""
echo "Project directory: $PROJECT_DIR"
echo ""

cd "$PROJECT_DIR"

# --- Step 1: Pull latest code ---
echo "[1/3] Pulling latest code..."
if ! sudo -u "$SERVICE_USER" git -C "$PROJECT_DIR" diff --quiet 2>/dev/null; then
    echo "  Stashing local changes..."
    sudo -u "$SERVICE_USER" git -C "$PROJECT_DIR" stash
fi
sudo -u "$SERVICE_USER" git -C "$PROJECT_DIR" pull
echo ""

# --- Step 2: Update Python packages ---
echo "[2/3] Updating Python packages..."
if [ -d "$PROJECT_DIR/venv" ]; then
    sudo -u "$SERVICE_USER" "$PROJECT_DIR/venv/bin/pip" install --upgrade pip
    sudo -u "$SERVICE_USER" "$PROJECT_DIR/venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt"
else
    echo "  WARNING: venv not found. Run scripts/install.sh first."
    exit 1
fi
echo ""

# --- Step 3: Restart service ---
echo "[3/3] Restarting PiClock3 service..."
if systemctl is-active --quiet piclock; then
    systemctl restart piclock
    echo "  Service restarted."
else
    echo "  Service not running. Start with: sudo systemctl start piclock"
fi
echo ""

echo "=== Update Complete ==="
