#!/usr/bin/env bash
# PiClock Uninstall Script
# Supports: Raspberry Pi OS, Debian, Ubuntu
# Usage:    sudo bash scripts/uninstall.sh [--purge]
#
# Stops and removes the systemd service, deletes the virtual environment,
# and optionally removes user data (faces, themes, alarms, settings).
#
# Options:
#   --purge   Also delete the data/ directory (themes, faces, alarms, settings, uploads).
#             Without this flag, data is preserved so you can reinstall later.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

PURGE=false
for arg in "$@"; do
    case "$arg" in
        --purge) PURGE=true ;;
    esac
done

# Determine the real user when run via sudo
if [ -n "$SUDO_USER" ]; then
    SERVICE_USER="$SUDO_USER"
else
    SERVICE_USER="$USER"
fi

echo "=== PiClock Uninstaller ==="
echo ""
echo "Project directory: $PROJECT_DIR"
echo "Service user:      $SERVICE_USER"
if [ "$PURGE" = true ]; then
    echo "Mode:              PURGE (will delete data/)"
else
    echo "Mode:              Keep data (use --purge to remove)"
fi
echo ""

if [ "$(id -u)" -ne 0 ]; then
    echo "Please run with sudo: sudo bash $0"
    exit 1
fi

# --- Step 1: Stop and disable the systemd service ---
echo "[1/4] Removing systemd service..."
if systemctl is-active --quiet piclock 2>/dev/null; then
    systemctl stop piclock
    echo "  Service stopped."
fi
if systemctl is-enabled --quiet piclock 2>/dev/null; then
    systemctl disable piclock
    echo "  Service disabled."
fi
if [ -f /etc/systemd/system/piclock.service ]; then
    rm /etc/systemd/system/piclock.service
    systemctl daemon-reload
    echo "  Service file removed."
else
    echo "  No service file found, skipping."
fi
# Remove sudoers rule
if [ -f /etc/sudoers.d/piclock ]; then
    rm /etc/sudoers.d/piclock
    echo "  Sudoers rule removed."
fi
# Remove disable-led service if installed
if [ -f /etc/systemd/system/disable-led.service ]; then
    systemctl disable disable-led.service 2>/dev/null || true
    rm /etc/systemd/system/disable-led.service
    systemctl daemon-reload
    echo "  LED service removed."
fi
# Re-enable getty on tty1 if it was disabled for KMS mode
if systemctl is-enabled --quiet getty@tty1.service 2>/dev/null; then
    : # already enabled
else
    systemctl enable getty@tty1.service 2>/dev/null || true
    systemctl start getty@tty1.service 2>/dev/null || true
    echo "  Re-enabled getty on tty1."
fi
echo ""

# --- Step 2: Restore graphical boot target if KMS mode was used ---
echo "[2/4] Checking boot target..."
CURRENT_TARGET=$(systemctl get-default 2>/dev/null || echo "")
if [ "$CURRENT_TARGET" = "multi-user.target" ]; then
    read -rp "  Boot target is multi-user (console). Restore to graphical (desktop)? [y/N] " restore
    if [[ "$restore" =~ ^[Yy]$ ]]; then
        systemctl set-default graphical.target
        echo "  Boot target restored to graphical.target."
    else
        echo "  Kept multi-user.target."
    fi
else
    echo "  Boot target is $CURRENT_TARGET, no change needed."
fi
echo ""

# --- Step 3: Remove virtual environment ---
echo "[3/4] Removing virtual environment..."
if [ -d "$PROJECT_DIR/venv" ]; then
    rm -rf "$PROJECT_DIR/venv"
    echo "  Removed venv/."
else
    echo "  No venv found, skipping."
fi
echo ""

# --- Step 4: Optionally remove data ---
echo "[4/4] Cleaning up data..."
# Always clean up Python cache
find "$PROJECT_DIR/src" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
echo "  Removed __pycache__ directories."

if [ "$PURGE" = true ]; then
    if [ -d "$PROJECT_DIR/data" ]; then
        rm -rf "$PROJECT_DIR/data"
        echo "  Removed data/ directory (themes, faces, alarms, settings, uploads)."
    fi
else
    echo "  Data directory preserved. Run with --purge to remove."
fi
echo ""

echo "=== Uninstall Complete ==="
echo ""
echo "The project source code remains in: $PROJECT_DIR"
echo "You can safely delete it with: rm -rf $PROJECT_DIR"
echo ""
echo "System packages (libcairo2-dev, libsdl2-dev, etc.) were left in place."
echo "Remove them manually with apt if no longer needed."
