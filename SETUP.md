# LotusLamp Linux — Setup Runbook

Complete setup instructions for Arch Linux. Written so a local agent (Hermes or otherwise) can execute it end-to-end without extra context.

## What this is

A desktop replacement for the LotusLamp X phone app. Controls ELK-BLEDOM-family BLE LED strips from your laptop: power, RGB color, brightness, 70 effect modes, speed, color temperature, and music sync that reacts to whatever plays on the laptop (PipeWire audio capture → FFT → strip at 20 Hz).

## Prerequisites

- Arch Linux with built-in Bluetooth (or a USB BLE dongle)
- PipeWire (default on modern Arch)
- Python 3.10+

## Setup steps

### 1. Clone

```bash
git clone https://github.com/Therazerhub/lotuslamp-linux.git
cd lotuslamp-linux
```

### 2. System packages

```bash
sudo pacman -S --needed --noconfirm bluez bluez-utils pipewire pipewire-pulse python python-pip
sudo systemctl enable --now bluetooth.service
```

### 3. Python dependencies

```bash
pip install --user --break-system-packages -r requirements.txt
```

Or in a venv (cleaner):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Verify Bluetooth

```bash
bluetoothctl show      # adapter must be present and powered
```

If the adapter is off: `bluetoothctl power on`.

### 5. Run

```bash
python -m lotuslampctl
```

Open http://localhost:8321

### 6. First connection

1. Force-stop LotusLamp X on the phone — the strip accepts only ONE BLE master.
2. In the panel: scan → connect.
3. Power on, pick a color, start music sync.

### 7. Music sync verification

The app captures the default PipeWire/PulseAudio monitor source:

```bash
pactl list short sources | grep -i monitor
```

If nothing shows, restart the Pulse compat layer:

```bash
systemctl --user restart pipewire-pulse
```

### 8. Optional autostart (systemd)

```bash
sudo tee /etc/systemd/system/lotuslampctl.service > /dev/null <<EOF
[Unit]
Description=LotusLamp Linux controller
After=bluetooth.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$PWD
ExecStart=$(which python3) -m lotuslampctl
Restart=on-failure

[Install]
WantedBy=default.target
EOF
sudo systemctl enable --now lotuslampctl
```

## Environment variables

- `PORT` — panel port, default 8321
- `MOCK=1` — hardware-free demo mode (no Bluetooth/audio needed)
- `LOGLEVEL=DEBUG` — log every BLE frame on the wire

## Troubleshooting

- No device found: strip is held by the phone app. Force-stop it, wait 5 s, rescan.
- Writes drop: get within ~2 m; these strips fade below RSSI -75.
- Permission denied on Bluetooth: `sudo usermod -aG lp $USER`, then re-login.
- Music sync silent: confirm a `.monitor` source exists (step 7).

## Layout

```
lotuslampctl/
├── __main__.py    entry point (uvicorn)
├── protocol.py    9-byte BLE frame encoding, full command table
├── ble.py         bleak controller: scan, connect, throttled write queue
├── music.py       PipeWire capture → FFT → 4-band → strip
└── server.py      FastAPI: REST + WebSocket + static panel
web/               minimal B&W control panel, zero CDN deps
```

</tool_call>