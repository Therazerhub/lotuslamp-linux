#!/usr/bin/env bash
# LotusLamp Linux — Arch Linux installer
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${SCRIPT_DIR%/web}"          # repo root
SERVICE_NAME="lotuslampctl"

echo "==> LotusLamp Linux · Arch installer"

# 1) system packages: BlueZ for BLE, PipeWire for audio capture, python build
echo "==> Installing system packages (sudo)..."
sudo pacman -S --needed --noconfirm bluez bluez-utils pipewire pipewire-pulse python python-pip python-dbus

# 2) enable & start bluetooth
echo "==> Enabling bluetooth service..."
sudo systemctl enable --now bluetooth.service || echo "   (bluetooth service will start at next boot)"

# 3) Python deps
echo "==> Installing python deps..."
pip3 install --user --break-system-packages -r "$APP_DIR/requirements.txt"

# 4) install service file (run as current user so PulseAudio/PipeWire sees desktop session)
SVC="[Unit]
Description=LotusLamp Linux controller
After=bluetooth.service network.target

[Service]
Type=simple
Environment=DISPLAY=${DISPLAY:-:0}
User=$USER
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/python3 -m lotuslampctl
Restart=on-failure

[Install]
WantedBy=default.target
"
echo "$SVC" | sudo tee "/etc/systemd/system/$SERVICE_NAME.service" > /dev/null

# 5) config: trusted device autostore path used by the app
mkdir -p "$HOME/.config/lotuslampctl"
touch "$HOME/.config/lotuslampctl/config.json"

echo ""
echo "==> Done. Run it:"
echo "      cd $APP_DIR && python3 -m lotuslampctl"
echo "    Open:  http://localhost:8321"
echo "    Optional autostart on boot:"
echo "      sudo systemctl enable --now $SERVICE_NAME"
echo ""
echo "    First use: keep your strip's original app closed on the phone,"
echo "    then hit SCAN in the panel and CONNECT."
