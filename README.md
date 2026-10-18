# LotusLamp Linux 🏮

Desktop control for **LotusLamp X / ELK-BLEDOM** family BLE LED strips on Arch Linux.
Replaces the phone app: full color, brightness, 70 effects, and **music sync from your laptop's audio** (PipeWire), all from a sleek black-&-white local web panel.

Protocol reverse-engineered from the official app — see `lotuslampctl/protocol.py` for the full 9-byte frame table.

## Features

- 🔌 Auto-discovery + connect over Bluetooth LE (no phone needed — only one host can hold the strip at a time, so close the phone app first)
- 🎨 16.7M RGB colors + color temperature + brightness
- 🌈 70 animation modes with speed control
- 🎵 **Music sync** — captures system audio via PipeWire/PulseAudio, FFT → 4-band spectrum, drives the strip at 20 Hz. Modes: `spectrum`, `pulse`, `bassflash`. Palettes: spectrum, fire, ocean, sunset, mono
- 🖥️ Minimal B&W web UI with live spectrum visualizer
- 🧪 `MOCK=1` dev mode — runs the whole stack with no hardware

## Install (Arch)

```bash
git clone <repo> && cd lotuslamp-linux
./install.sh        # bluez + pipewire + python deps + systemd service
```

Or manually:

```bash
sudo pacman -S --needed bluez bluez-utils pipewire pipewire-pulse python
pip install --user -r requirements.txt
sudo systemctl enable --now bluetooth
```

## Run

```bash
python3 -m lotuslampctl
# → http://localhost:8321
```

First use: disconnect/close LotusLamp X on your phone, then **scan → connect** in the panel.

Optional autostart:

```bash
sudo systemctl enable --now lotuslampctl
```

## Configuration

- `PORT=8321` — panel port
- `MOCK=1` — hardware-free demo mode
- `LOGLEVEL=DEBUG` — see BLE frames on the wire

## Compatibility

Tested protocol targets: `ELK-BLEDOM*`, `ELK~*`, `LED LIGHT STRIP*`, `XSL-*`.
Devices whose name contains literal `ELK-*` use an XOR write-cipher for some commands — not yet implemented; the vast majority of AliExpress strips are plaintext and work out of the box.

## Troubleshooting

- **No device found** — strip can only hold one BLE master. Disconnect the phone app (force-stop), retry scan.
- **Writes drop after a few seconds** — move closer; these strips are flaky past ~-75 dBm RSSI.
- **Music sync silent** — verify PipeWire: `pactl list short sources` should show a `monitor` source. The app captures from the default monitor source.

## Disclaimer

Unofficial, reverse-engineered. Not affiliated with the lamp or app vendor.
