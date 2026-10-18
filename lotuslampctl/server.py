"""LotusLamp Linux — FastAPI server.

Serves the web UI and a JSON API. Runs the BLE controller and music-sync engine.
MOCK=1 env var runs without any Bluetooth/audio hardware (dev/demo).
"""

import asyncio
import json
import logging
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .ble import LampController
from .music import MusicSync

log = logging.getLogger("lotuslampctl.server")

MOCK = os.environ.get("MOCK", "") == "1"

app = FastAPI(title="LotusLamp Linux")
lamp = LampController()
music = MusicSync(lamp)

if MOCK:
    # Stub the BLE layer so the whole stack runs hardware-free.
    class _MockLamp(LampController):
        async def scan_all(self, timeout=8.0):
            return await self.scan(timeout)

        async def scan(self, timeout=8.0):
            return [{"name": "ELK-BLEDOM (mock)", "address": "BE:32:00:11:22:33", "rssi": -52}]

        async def connect(self, address=None, name=None):
            self.connected = True
            self.device_name = name or "ELK-BLEDOM (mock)"
            self.device_address = address or "BE:32:00:11:22:33"
            return True

        async def _writer(self):
            while True:
                frame = await self._queue.get()
                log.debug("mock write: %s", frame.hex(" "))

        async def _ensure(self):
            return self.connected

    lamp = _MockLamp()
    music = MusicSync(lamp)

web_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


@app.on_event("startup")
async def startup():
    lamp.start()
    log.info("LotusLamp server up (mock=%s)", MOCK)


# ---------- pages ----------

@app.get("/", response_class=HTMLResponse)
async def index():
    with open(os.path.join(web_dir, "index.html")) as f:
        return HTMLResponse(f.read())


# ---------- API ----------

@app.get("/api/status")
async def status():
    return {
        "connected": lamp.connected,
        "device": {"name": lamp.device_name, "address": lamp.device_address} if lamp.connected else None,
        "state": lamp.get_state(),
        "music": music.status(),
        "mock": MOCK,
    }


@app.post("/api/power/{on}")
async def power(on: str):
    await lamp.set_power(on == "on")
    return {"ok": True, "power": on == "on"}


@app.post("/api/color")
async def color(r: int, g: int, b: int):
    await music.stop()
    await lamp.set_color(r, g, b)
    return {"ok": True, "color": [r, g, b]}


@app.post("/api/brightness")
async def brightness(level: int):
    await lamp.set_brightness(level)
    return {"ok": True, "brightness": level}


@app.post("/api/mode")
async def mode(index: int):
    await music.stop()
    await lamp.set_mode(index)
    return {"ok": True, "mode": index}


@app.post("/api/speed")
async def speed(value: int):
    await lamp.set_speed(value)
    return {"ok": True, "speed": value}


@app.get("/api/modes")
async def modes():
    from . import protocol
    return {"modes": protocol.MODES}


@app.post("/api/colortemp")
async def colortemp(warm: int, cold: int):
    await lamp.set_color_temp(warm, cold)
    return {"ok": True}


# ---------- music sync ----------

@app.post("/api/music/{mode_name}")
async def music_mode(mode_name: str, sensitivity: float = 1.0, palette: str = "spectrum"):
    if mode_name == "off":
        await music.stop()
        return {"ok": True, "music": music.status()}
    await music.start(mode_name, sensitivity, palette)
    return {"ok": True, "music": music.status()}


@app.post("/api/music/config")
async def music_config(sensitivity: float = None, palette: str = None):
    if sensitivity is not None:
        music.sensitivity = sensitivity
    if palette is not None:
        music.palette = palette
    return {"ok": True, "music": music.status()}


# ---------- devices ----------

@app.get("/api/scan")
async def scan(timeout: float = 8.0):
    found = await lamp.scan(timeout)
    return {"devices": found}


@app.post("/api/connect")
async def connect(address: str = None, name: str = None):
    ok = await lamp.connect(address, name)
    return {"ok": ok, "connected": lamp.connected, "device": lamp.device_name}


@app.post("/api/disconnect")
async def disconnect():
    await music.stop()
    await lamp.disconnect()
    return {"ok": True}


@app.get("/api/devices/all")
async def devices_all(timeout: float = 6.0):
    found = await lamp.scan_all(timeout)
    return {"devices": found}


# ---------- websocket (live spectrum) ----------

@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()
    try:
        while True:
            await sock.send_json({"music": music.status(), "lamp": lamp.get_state()})
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
