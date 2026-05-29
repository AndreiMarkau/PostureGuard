"""
player.py — alert sound playback via sounddevice OutputStream callback.
Volume changes are applied sample-accurate with zero latency.
Supports WAV natively; MP3/OGG/FLAC via soundfile if available.
"""
from __future__ import annotations

import os
import wave
import struct
import threading
from typing import Optional

try:
    import sounddevice as sd
    import numpy as np
    _SD_OK = True
except ImportError:
    _SD_OK = False
    print("[AudioPlayer] sounddevice/numpy not available — audio disabled")

try:
    import soundfile as sf
    _SF_OK = True
except ImportError:
    _SF_OK = False


def _default_sound_path() -> str:
    import sys
    base = getattr(sys, '_MEIPASS',
                   os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "assets", "alert.wav")


def _load_audio(path: str):
    """Return (samples float32 [frames x channels], samplerate)."""
    if _SF_OK:
        try:
            arr, rate = sf.read(path, dtype='float32', always_2d=True)
            return arr, rate
        except Exception as e:
            print(f"[AudioPlayer] soundfile failed ({e}), trying wave…")

    with wave.open(path, 'rb') as wf:
        n_ch     = wf.getnchannels()
        sampw    = wf.getsampwidth()
        rate     = wf.getframerate()
        n_frames = wf.getnframes()
        raw      = wf.readframes(n_frames)

    fmt = {1: 'b', 2: 'h', 4: 'i'}.get(sampw, 'h')
    samples = struct.unpack(f'<{n_frames * n_ch}{fmt}', raw)
    max_val  = float(2 ** (8 * sampw - 1))
    arr = np.array(samples, dtype=np.float32) / max_val
    arr = arr.reshape(-1, n_ch) if n_ch > 1 else arr.reshape(-1, 1)
    return arr, rate


class AudioPlayer:
    """
    Streams audio via sd.OutputStream callback — volume is applied
    per-buffer so changes are heard within one callback period (~10 ms).
    Mute sets effective volume to 0; the stream keeps running for
    instant unmute without any click or gap.
    """

    def __init__(self):
        self._initialized = _SD_OK
        self._volume: float = 0.8   # set by slider
        self._muted:  bool  = False  # set by mute button
        self._sound_path: Optional[str] = None

        # Playback state (accessed from callback thread — use atomic ops only)
        self._arr:  Optional["np.ndarray"] = None   # [frames x channels]
        self._rate: int = 44100
        self._pos:  int = 0          # current read position in _arr

        self._stream: Optional["sd.OutputStream"] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ API

    def set_sound(self, path: Optional[str]):
        if path != self._sound_path:
            self._sound_path = path
            self._arr = None  # invalidate cache

    def set_volume(self, volume: float):
        """Called from UI thread — applied immediately on next callback."""
        self._volume = max(0.0, min(1.0, volume))

    def get_volume(self) -> float:
        """Return current volume (0.0–1.0), ignoring mute state."""
        return self._volume

    def set_muted(self, muted: bool):
        """Mute/unmute — zero volume, stream keeps running."""
        self._muted = muted

    @property
    def effective_volume(self) -> float:
        return 0.0 if self._muted else self._volume

    @property
    def is_playing(self) -> bool:
        return self._stream is not None and self._stream.active

    # ------------------------------------------------------------------ play/stop

    def play(self):
        with self._lock:
            if self._stream is not None:
                return  # already playing
            if not self._initialized:
                return

            path = self._sound_path or _default_sound_path()
            if not os.path.isfile(path):
                print(f"[AudioPlayer] Sound file not found: {path}")
                return

            if self._arr is None:
                try:
                    self._arr, self._rate = _load_audio(path)
                except Exception as e:
                    print(f"[AudioPlayer] Failed to load audio: {e}")
                    return

            self._pos = 0
            channels = self._arr.shape[1]

            try:
                self._stream = sd.OutputStream(
                    samplerate=self._rate,
                    channels=channels,
                    dtype='float32',
                    blocksize=1024,
                    callback=self._callback,
                    finished_callback=None,
                )
                self._stream.start()
            except Exception as e:
                print(f"[AudioPlayer] Stream start error: {e}")
                self._stream = None

    def stop(self):
        with self._lock:
            stream = self._stream
            self._stream = None
        if stream is not None:
            try:
                stream.stop(ignore_errors=True)
                stream.close(ignore_errors=True)
            except Exception:
                pass

    def cleanup(self):
        self.stop()

    # ------------------------------------------------------------------ callback (audio thread)

    def _callback(self, outdata: "np.ndarray", frames: int,
                  time_info, status) -> None:
        """
        Called by sounddevice from a high-priority audio thread.
        Must be fast and non-blocking.
        """
        arr = self._arr
        if arr is None:
            outdata[:] = 0
            return

        vol   = self.effective_volume  # single float read — atomic on CPython
        total = len(arr)
        out   = np.empty((frames, arr.shape[1]), dtype=np.float32)
        written = 0

        # Loop the sample to fill the output buffer
        while written < frames:
            remaining_in_arr = total - self._pos
            need = frames - written
            take = min(need, remaining_in_arr)
            out[written:written + take] = arr[self._pos:self._pos + take]
            self._pos += take
            written   += take
            if self._pos >= total:
                self._pos = 0  # loop

        outdata[:] = out * vol
