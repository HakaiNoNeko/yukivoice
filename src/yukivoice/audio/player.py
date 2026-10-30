"""Cross-platform playback built on miniaudio (PulseAudio/PipeWire, WASAPI, CoreAudio).

A clip is played to one or two output devices at once: the virtual mic (so other
apps hear it) and, if Monitor is on, the user's normal speakers.
"""

import threading
import time
from array import array

import miniaudio
import numpy as np

from ..log import log


def _close_device(dev) -> None:
    """Stop and fully release a miniaudio device.

    pyminiaudio gives every device its own ma_context (one PulseAudio/PipeWire
    client connection) but close() only uninits the device, never the context.
    Without freeing it, each playback leaks a connection until the server hits
    its client limit and refuses everything ("virtual mic isn't available").
    """
    try:
        dev.close()
    finally:
        ctx = getattr(dev, "_context", None)
        if ctx is not None:
            dev._context = None
            miniaudio.lib.ma_context_uninit(ctx)


def playback_devices() -> list:
    """[{'name': str, 'id': cdata}, …] for every output device."""
    try:
        return list(miniaudio.Devices().get_playbacks())
    except Exception as e:  # no audio server at all
        log(f"device enumeration failed: {e}")
        return []


def find_playback(*needles: str):
    """First output device whose name contains any needle (case-insensitive)."""
    for d in playback_devices():
        name = d["name"].lower()
        if any(n.lower() in name for n in needles):
            return d
    return None


class Playback:
    """Plays audio to a list of target devices; `targets[0]` decides when it's over.

    A target is a device dict from `playback_devices()` or None for the default
    output. `make_stream(device_index)` returns a miniaudio-style generator of
    float32 stereo/mono sample arrays at (rate, channels).
    """

    def __init__(self, make_stream, targets, rate, channels, on_done=None):
        self._make_stream = make_stream
        self._targets = targets
        self._rate = rate
        self._channels = channels
        self._on_done = on_done
        self._devices = []
        self._finished = threading.Event()
        self._stopped = False
        self._stop_lock = threading.Lock()

    def start(self):
        try:
            for i, target in enumerate(self._targets):
                dev = miniaudio.PlaybackDevice(
                    output_format=miniaudio.SampleFormat.FLOAT32,
                    nchannels=self._channels,
                    sample_rate=self._rate,
                    buffersize_msec=80,
                    device_id=None if target is None else target["id"],
                    app_name="YukiVoice",
                )
                self._devices.append(dev)
                dev.start(self._wrap(self._make_stream(i), primary=(i == 0)))
        except Exception:
            self.stop()
            raise
        threading.Thread(target=self._watch, daemon=True).start()
        return self

    def _wrap(self, stream, primary):
        """Wrap a primed stream so the primary one reports when it runs dry.
        Returns a primed generator, as miniaudio's start() requires."""
        def gen():
            required = yield b""
            while True:
                try:
                    samples = stream.send(required)
                except StopIteration:
                    if primary:
                        self._finished.set()
                    return
                required = yield samples
        g = gen()
        next(g)
        return g

    def _watch(self):
        self._finished.wait()
        time.sleep(0.25)  # let the device buffer drain
        self.stop()

    def stop(self):
        with self._stop_lock:
            if self._stopped:
                return
            self._stopped = True
        self._finished.set()
        devices, self._devices = self._devices, []
        for d in devices:
            try:
                _close_device(d)
            except Exception:
                pass
        if self._on_done:
            self._on_done()

    def wait(self, timeout=None):
        self._finished.wait(timeout)
        while not self._stopped:
            time.sleep(0.02)


def _primed(fn):
    """miniaudio wants generators that are already past their first yield."""
    def wrapper(*a, **kw):
        g = fn(*a, **kw)
        next(g)
        return g
    return wrapper


@_primed
def _array_stream(samples: np.ndarray):
    """Generator feeding a float32 array to miniaudio (interleaved if stereo)."""
    flat = array("f", np.ascontiguousarray(samples, dtype=np.float32).ravel().tobytes())
    ch = 1 if samples.ndim == 1 else samples.shape[1]
    pos = 0
    required = yield b""
    while pos < len(flat):
        want = required * ch
        chunk = flat[pos:pos + want]
        pos += want
        required = yield chunk


def play_samples(samples: np.ndarray, rate: int, targets, on_done=None) -> Playback:
    """Play float32 mono samples (e.g. TTS output) to every target at once."""
    return Playback(lambda i: _array_stream(samples), targets, rate, 1, on_done).start()


def play_file(path: str, targets, on_done=None) -> Playback:
    """Stream an audio file (wav/mp3/flac/ogg) to every target at once."""
    return Playback(
        lambda i: miniaudio.stream_file(
            path, output_format=miniaudio.SampleFormat.FLOAT32, nchannels=2,
            sample_rate=48000, frames_to_read=1024),
        targets, 48000, 2, on_done).start()


class PcmPipe:
    """Live float32 stereo 48 kHz audio fed from another thread (app capture)."""

    def __init__(self, max_seconds=0.4):
        self._buf = bytearray()
        self._lock = threading.Lock()
        self._max = int(48000 * 2 * 4 * max_seconds)
        self.closed = False

    def feed(self, data: bytes):
        with self._lock:
            self._buf += data
            if len(self._buf) > self._max:      # clocks drift; drop the oldest audio
                del self._buf[:len(self._buf) - self._max]

    @_primed
    def stream(self):
        required = yield b""
        while not self.closed:
            need = required * 2 * 4
            with self._lock:
                data = bytes(self._buf[:need])
                del self._buf[:need]
            if len(data) < need:
                data += b"\0" * (need - len(data))  # underrun → silence
            required = yield array("f", data)


def play_pipe(pipe: PcmPipe, targets, on_done=None) -> Playback:
    return Playback(lambda i: pipe.stream(), targets, 48000, 2, on_done).start()
