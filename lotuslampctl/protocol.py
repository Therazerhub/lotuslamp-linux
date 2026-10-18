"""
LotusLamp X / ELK-BLEDOB 9-byte BLE frame protocol.

All commands are 9 bytes:
    0x7E  LEN  CMD  P1  P2  P3  P4  P5  0xEF

- 0x7E (126)  start byte
- LEN         payload length marker
- CMD         command type
- P1..P5      params (padded 0xFF/0x00 when unused)
- 0xEF (239)  end byte

Service 0xFFF0, write characteristic 0xFFF3 (writeCharacteristic / with response).

Frames below follow the tested ELK-BLEDOM / LotusLamp family layout
(cross-validated against the lotuslantern-go and Home Assistant projects).

For device-name prefix "ELK-*" a GATT-write XOR/encryption layer is required
for CMD in {1,3,4}. Not implemented here (plaintext default) — covered in README.
"""

# UUIDs
SERVICE = "0000fff0-0000-1000-8000-00805f9b34fb"
CHAR_WRITE = "0000fff3-0000-1000-8000-00805f9b34fb"

# Device-name prefixes we auto-discover
NAME_PREFIXES = ("ELK-", "ELK~", "LED LIGHT STRIP", "XSL-", "BLEDOB", "MELK-OA10")

_MAX_BRIGHTNESS = 255
_MAX_SPEED = 100


def _frame(cmd: int, params: list, length: int) -> bytes:
    p = list(params) + [0xFF] * (5 - len(params))  # pad to 5
    return bytes([0x7E, length, cmd, p[0], p[1], p[2], p[3], p[4], 0xEF])


def power(on: bool) -> bytes:
    # 7E 07 04 [FF|00] 00 01 02 01 EF
    return _frame(0x04, [0xFF if on else 0x00, 0x00, 0x01 if on else 0x00, 0x02, 0x01], 7)


def rgb(r: int, g: int, b: int) -> bytes:
    # 7E 07 05 03 R G B 10 EF
    return _frame(0x05, [0x03, r & 0xFF, g & 0xFF, b & 0xFF, 0x10], 7)


def rgb_music_mode(r: int, g: int, b: int) -> bytes:
    # music-reactive RGB with amplitude flag 0x20
    return _frame(0x05, [0x03, r & 0xFF, g & 0xFF, b & 0xFF, 0x20], 7)


def color_temp(warm: int, cold: int) -> bytes:
    # 7E 06 05 02 warm cold FF 08 EF
    return _frame(0x05, [0x02, warm & 0xFF, cold & 0xFF, 0xFF, 0x08], 6)


def brightness(level: int, light_mode: int = 1) -> bytes:
    # 7E 04 01 BR lightMode FF 02 01 EF
    level = max(0, min(255, int(level)))
    return _frame(0x01, [level, light_mode, 0xFF, 0x02, 0x01], 4)


def mode(index: int) -> bytes:
    # 7E 07 03 (0x80|mode) 03 FF FF 00 EF
    # Mode gets high bit set (0x80..0xFF). Index passed 0-based.
    idx = max(0, min(0x7C, int(index)))  # 0..124
    return _frame(0x03, [0x80 | idx, 0x03, 0xFF, 0xFF, 0x00], 7)


def mode_speed(speed: int) -> bytes:
    # 7E 07 02 SP FF FF FF 00 EF
    spd = max(0, min(255, int(speed)))
    return _frame(0x02, [spd, 0xFF, 0xFF, 0xFF, 0x00], 7)


def laser_speed(speed: int) -> bytes:
    # 7E 04 02 speed 04 FF FF FF EF  -> LEN 7 per family
    spd = max(0, min(255, int(speed)))
    return _frame(0x02, [spd, 0x04, 0xFF, 0xFF, 0xFF], 7)


def external_mic(on: bool) -> bytes:
    return _frame(0x07, [0x01 if on else 0x00, 0xFF, 0xFF, 0xFF, 0x00], 4)


def set_time(hour: int, minute: int, second: int, weekday: int) -> bytes:
    # 7E 06 83 hh mm ss dow 00 EF  (time sync on connect)
    return _frame(0x83, [hour & 0xFF, minute & 0xFF, second & 0xFF, weekday & 0xFF, 0x00], 6)


# ---- mode catalog (0-based indices that map to 0x80|i). Names from the app. ----
MODES = [
    "Solid (off) - static color",          # 0
    "Color jump",                          # 1
    "Color gradient",                      # 2
    "Color strobe",                        # 3
    "Red gradient",                        # 4
    "Green gradient",                      # 5
    "Blue gradient",                       # 6
    "Yellow gradient",                     # 7
    "Cyan gradient",                       # 8
    "Purple gradient",                     # 9
    "White gradient",                      # 10
    "Red-green gradient",                  # 11
    "Red-blue gradient",                   # 12
    "Green-blue gradient",                 # 13
    "Colorful strobe",                     # 14
    "Red strobe",                          # 15
    "Green strobe",                        # 16
    "Blue strobe",                         # 17
    "Seven color jump",                    # 18
    "Seven color fade",                    # 19
    "Red fade",                            # 20
    "Green fade",                          # 21
    "Blue fade",                           # 22
    "Yellow fade",                         # 23
    "Cyan fade",                           # 24
    "Purple fade",                         # 25
    "White fade",                          # 26
    "Red green swap",                      # 27
    "Red blue swap",                       # 28
    "Green blue swap",                     # 29
    "Seven color strobe",                  # 30
    "Red slow fade",                       # 31
    "Green slow fade",                     # 32
    "Blue slow fade",                      # 33
    "RGB breathing",                       # 34
    "Red breathing",                       # 35
    "Green breathing",                     # 36
    "Blue breathing",                      # 37
    "Yellow breathing",                    # 38
    "Cyan breathing",                      # 39
    "Purple breathing",                    # 40
    "White breathing",                     # 41
    "Seven color breath",                  # 42
    "Colorful meteor",                     # 43
    "Red meteor",                          # 44
    "Green meteor",                        # 45
    "Blue meteor",                         # 46
    "Red comet",                           # 47
    "Green comet",                         # 48
    "Blue comet",                          # 49
    "Red stars",                           # 50
    "Green stars",                         # 51
    "Blue stars",                          # 52
    "Colorful stars",                      # 53
    "Red streaking",                       # 54
    "Green streaking",                     # 55
    "Blue streaking",                      # 56
    "Colorful flow",                       # 57
    "Red flow",                            # 58
    "Green flow",                          # 59
    "Blue flow",                           # 60
    "Colorful meteor 2",                   # 61
    "Colorful comet",                      # 62
    "Music mode (color)",                  # 63
    "Music mode (red)",                    # 64
    "Music mode (green)",                  # 65
    "Music mode (blue)",                   # 66
    "Music mode (yellow)",                 # 67
    "Music mode (cyan)",                   # 68
    "Music mode (purple)",                 # 69
]
