"""
Music sync engine: captures system audio (PipeWire via PulseAudio compat),
FFT → 4-band spectrum (bass/mid/treble), maps to strip color + intensity.

Drives the strip via LampController at ~20 Hz. Falls back to a simulated
spectrum (mock mode) when no audio capture is available.
"""

import asyncio
import logging
import math
import struct
import time
import random

import numpy as np

from . import protocol

log = logging.getLogger("lotuslampctl.music")

SAMPLE_RATE = 48000
CHUNK = 1024            # ~21 ms at 48kHz
BANDS = 4               # bass / low-mid / high-mid / treble
SEND_INTERVAL = 0.05    # 20 Hz — matches BLE throttle


def _rfft_mag(samples: np.ndarray) -> np.ndarray:
    win = np.hanning(len(samples))
    spec = np.abs(np.fft.rfft(samples * win))
    return spec


def _band_energies(mag: np.ndarray) -> list:
    n = len(mag)
    freqs = np.fft.rfftfreq(CHUNK, 1.0 / SAMPLE_RATE)
    edges = [0, 120, 500, 2000, 8000]
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        idx = (freqs >= lo) & (freqs < hi)
        e = float(np.mean(mag[idx])) if idx.any() else 0.0
        out.append(e)
    return out


class MusicSync:
    def __init__(self, lamp):
        self.lamp = lamp
        self.running = False
        self._task = None
        self.mode = "off"  # off | pulse | spectrum
        self.sensitivity = 1.0
        self.palette = "spectrum"  # spectrum | fire | ocean | sunset | mono
        self._smoothed = [0.0] * BANDS
        self._beat_flash = 0.0
        self._last_bass = 0.0
        self._stream = None

    # ---------- audio capture ----------

    def _open_pipewire_stream(self):
        """Open a monitor capture of default sink via PulseAudio compat."""
        import soundcard as sc  # optional dep
        mic = sc.default_microphone()
        if mic is None:
            raise RuntimeError("no audio capture device")
        return mic.recorder(samplerate=SAMPLE_RATE, channels=1, blocksize=CHUNK)

    # ---------- palettes ----------

    @staticmethod
    def _mix(c1, c2, t):
        return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))

    def _palette_color(self, pos: float, intensity: float):
        """pos 0..1 across spectrum, intensity 0..1 → (r,g,b)."""
        i = max(0.0, min(1.0, intensity))
        if self.palette == "fire":
            base = (255, 60, 0)
            hot = (255, 220, 80)
        elif self.palette == "ocean":
            base = (0, 40, 255)
            hot = (0, 220, 255)
        elif self.palette == "sunset":
            base = (255, 0, 120)
            hot = (255, 160, 0)
        elif self.palette == "mono":
            v = int(255 * i)
            return (v, v, v)
        else:  # spectrum
            # bass=red → treble=violet
            r = int(255 * min(1.0, pos * 2.0))
            b = int(255 * max(0.0, (pos - 0.5) * 2.0))
            g = int(255 * (1.0 - abs(pos - 0.5) * 2.0) * 0.8)
            return (int(r * i), int(g * i), int(b * i))
        return self._mix(base, hot, i)

    # ---------- main loop ----------

    async def start(self, mode: str, sensitivity: float = 1.0, palette: str = "spectrum"):
        if self.running:
            await self.stop()
        self.mode = mode
        self.sensitivity = sensitivity
        self.palette = palette
        self.running = True
        self._task = asyncio.get_event_loop().create_task(self._run())

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                self._task = None
            except Exception:
                pass
        self.mode = "off"

    async def _run(self):
        reader = None
        proc = None
        try:
            # Try pw-record/pactl monitor capture via subprocess (PipeWire native).
            # Fallback: mock spectrum so the UI + light still demo.
            reader, proc = await self._open_capture()
            if reader is None:
                log.info("no audio capture; using simulated spectrum")
                await self._run_simulated()
                return
            await self._run_real(reader)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.error("music sync error: %s — falling back to simulation", e)
            await self._run_simulated()
        finally:
            if proc:
                proc.kill()

    async def _open_capture(self):
        """Return (asyncStreamReader, process) capturing default output monitor."""
        import shutil
        pw_record = shutil.which("pw-record")
        if not pw_record:
            return None, None
        proc = await asyncio.create_subprocess_exec(
            pw_record, "--target", "auto", "--format", "f32", "--rate", str(SAMPLE_RATE),
            "--channels", "1", "--raw", "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return proc.stdout, proc

    async def _run_real(self, reader):
        bytes_per_chunk = CHUNK * 4  # f32
        pending = b""
        while self.running:
            data = await reader.read(bytes_per_chunk - len(pending))
            if not data:
                await asyncio.sleep(0.01)
                continue
            pending += data
            while len(pending) >= bytes_per_chunk:
                chunk, pending = pending[:bytes_per_chunk], pending[bytes_per_chunk:]
                samples = np.frombuffer(chunk, dtype=np.float32)
                await self._process(samples)

    async def _run_simulated(self):
        rng = random.Random()
        t0 = time.monotonic()
        while self.running:
            t = time.monotonic() - t0
            # fake a beat at 120bpm plus melody wobble
            beat = max(0.0, 1.0 - ((t * 2.0) % 1.0) * 2.5)
            bands = [
                max(0.0, beat + 0.1 * rng.random()),
                0.3 + 0.25 * math.sin(t * 3.1) + 0.1 * rng.random(),
                0.3 + 0.25 * math.sin(t * 4.7 + 1.0) + 0.1 * rng.random(),
                0.2 + 0.2 * math.sin(t * 6.3 + 2.0) + 0.1 * rng.random(),
            ]
            await self._process_bands([min(1.0, max(0.0, b)) for b in bands])
            await asyncio.sleep(SEND_INTERVAL)

    async def _process(self, samples: np.ndarray):
        mag = _rfft_mag(samples.astype(np.float64))
        energies = _band_energies(mag)
        # normalize + sensitivity
        m = max(energies) or 1.0
        bands = [min(1.0, (e / m) * self.sensitivity) if m > 0 else 0.0 for e in energies]
        await self._process_bands(bands)

    async def _process_bands(self, bands: list):
        # exponential smoothing
        a = 0.35
        self._smoothed = [a * b + (1 - a) * s for b, s in zip(bands, self._smoothed)]

        bass = self._smoothed[0]
        # beat detection: bass energy jump
        if bass > self._last_bass * 1.4 and bass > 0.25:
            self._beat_flash = 1.0
        self._last_bass = bass
        self._beat_flash *= 0.85

        level = min(1.0, sum(self._smoothed) / len(self._smoothed) * 1.6 + self._beat_flash * 0.5)

        if self.mode == "pulse":
            # whole-strip color pulses with bass
            r, g, b = self._palette_color(0.2, level)
            await self.lamp.set_color(r, g, b)
        elif self.mode == "spectrum":
            # strip color shifts hue across the spectrum with overall energy
            pos = (sum(self._smoothed[i] * i for i in range(BANDS))
                   / max(0.001, sum(self._smoothed)))
            r, g, b = self._palette_color(pos, level)
            await self.lamp.set_color(r, g, b)

    # ---------- status ----------

    def status(self):
        return {
            "running": self.running,
            "mode": self.mode,
            "sensitivity": self.sensitivity,
            "palette": self.palette,
            "bands": [round(s, 3) for s in self._smoothed],
            "beat": round(self._beat_flash, 3),
        }
