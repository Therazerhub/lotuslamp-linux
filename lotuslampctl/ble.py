"""BLE controller for LotusLamp X / ELK-BLEDOB devices (async, bleak)."""

import asyncio
import logging
import time
from typing import Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from . import protocol

log = logging.getLogger("lotuslampctl.ble")

# Throttle: these strips drop the link if hammered faster than ~20Hz.
MIN_WRITE_INTERVAL = 0.05


class LampController:
    """Owns the BLE connection, writes frames, auto-reconnects."""

    def __init__(self):
        self.device: Optional[BLEDevice] = None
        self.client: Optional[BleakClient] = None
        self.connected = False
        self.device_name: str = ""
        self.device_address: str = ""
        self._queue: "asyncio.Queue[bytes]" = asyncio.Queue(maxsize=64)
        self._task: Optional[asyncio.Task] = None
        self._last_write = 0.0
        self._state = {
            "power": False,
            "brightness": 128,
            "color": [255, 255, 255],
            "mode": 0,
            "speed": 128,
        }

    # ---------- scanning ----------

    async def scan(self, timeout: float = 8.0) -> list:
        found = []
        devices = await BleakScanner.discover(timeout=timeout)

        for d in devices:
            name = (d.name or "").strip()
            if any(name.upper().startswith(p.upper()) for p in protocol.NAME_PREFIXES):
                found.append({
                    "name": name,
                    "address": d.address,
                    "rssi": d.rssi,
                })
        return found

    async def scan_all(self, timeout: float = 6.0) -> list:
        """Everything visible, for a manual pick if auto-discovery fails."""
        devices = await BleakScanner.discover(timeout=timeout)
        return [{"name": d.name or "(unnamed)", "address": d.address, "rssi": d.rssi}
                for d in devices]

    # ---------- connection ----------

    async def connect(self, address: str = None, name: str = None) -> bool:
        if self.connected:
            await self.disconnect()

        if address:
            self.device = await BleakScanner.find_device_by_address(address, timeout=10.0)
        else:
            matches = await self.scan(8.0)
            if not matches:
                log.warning("no matching lamp found in scan")
                return False
            self.device = await BleakScanner.find_device_by_address(matches[0]["address"])

        if not self.device:
            return False

        try:
            self.client = BleakClient(self.device)
            await self.client.connect()
            self.connected = True
            self.device_name = name or (self.device.name or "?")
            self.device_address = self.device.address
            # sync device clock so its timer feature works
            t = time.localtime()
            await self._send(protocol.set_time(t.tm_hour, t.tm_min, t.tm_sec, t.tm_wday + 1))
            log.info("connected to %s (%s)", self.device_name, self.device_address)
            return True
        except Exception as e:
            log.error("connect failed: %s", e)
            self.connected = False
            return False

    async def disconnect(self):
        if self.client and self.client.is_connected:
            try:
                await self.client.disconnect()
            except Exception:
                pass
        self.client = None
        self.connected = False
        self.device = None
        log.info("disconnected")

    async def _ensure(self) -> bool:
        if self.connected and self.client and self.client.is_connected:
            return True
        return await self.connect(self.device_address, self.device_name)

    # ---------- writer loop ----------

    def start(self):
        if not self._task or self._task.done():
            self._task = asyncio.get_event_loop().create_task(self._writer())

    async def _writer(self):
        while True:
            frame = await self._queue.get()
            try:
                if not await self._ensure():
                    log.warning("write skipped, no connection")
                    continue
                # throttle
                now = time.monotonic()
                await asyncio.sleep(max(0, MIN_WRITE_INTERVAL - (now - self._last_write)))
                await self.client.write_gatt_char(
                    protocol.CHAR_WRITE, frame, response=True)
                self._last_write = time.monotonic()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.error("write failed (%s); reconnecting", e)
                self.connected = False
                try:
                    await self.client.disconnect()
                except Exception:
                    pass
                self.client = None

    async def _send(self, frame: bytes):
        if self._queue.full():
            try:
                self._queue.get_nowait()  # drop oldest, keep freshest state
            except asyncio.QueueEmpty:
                pass
        await self._queue.put(frame)

    # ---------- public commands ----------

    async def set_power(self, on: bool):
        self._state["power"] = on
        await self._send(protocol.power(on))

    async def set_color(self, r, g, b):
        self._state["color"] = [r, g, b]
        await self._send(protocol.rgb(r, g, b))

    async def set_brightness(self, level: int):
        level = max(0, min(255, int(level)))
        self._state["brightness"] = level
        await self._send(protocol.brightness(level))

    async def set_mode(self, index: int):
        self._state["mode"] = index
        await self._send(protocol.mode(index))

    async def set_speed(self, speed: int):
        self._state["speed"] = speed
        await self._send(protocol.mode_speed(speed))

    async def set_color_temp(self, warm: int, cold: int):
        await self._send(protocol.color_temp(warm, cold))

    async def set_music_color(self, r, g, b):
        await self._send(protocol.rgb_music_mode(r, g, b))

    async def set_external_mic(self, on: bool):
        await self._send(protocol.external_mic(on))

    def get_state(self):
        return dict(self._state)

    def _on_notify(self, _h, data: bytes):
        log.debug("notify: %s", data.hex())
