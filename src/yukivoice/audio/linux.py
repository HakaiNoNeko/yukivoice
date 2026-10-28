"""Linux backend: PipeWire / PulseAudio virtual mic via pactl.

  null-sink    yvc_sink   <- TTS and files are played here
  remap-source yvc_mic    -> other apps pick it as "YukiVoice Mic"

Capturing an app moves its streams onto a private sink (yvc_capture) that is
looped into yvc_sink (and, with Monitor, into the speakers). Releasing puts the
streams back where they were. Everything is removed on quit.
"""

import json
import os
import shutil
import subprocess
import time
from typing import Optional

from ..log import log
from . import player
from .base import AppInfo, Backend, Check

SINK = "yvc_sink"
SINK_DESC = "YukiVoice (sink)"
MIC = "yvc_mic"
MIC_DESC = "YukiVoice Mic"
CAP = "yvc_capture"
CAP_DESC = "YukiVoice capture"
_PREFIX = "yvc_"


def pactl(*args):
    return subprocess.run(["pactl", *args], capture_output=True, text=True)


def _pwlink(*args):
    return subprocess.run(["pw-link", *args], capture_output=True, text=True)


def _desc(s):
    return 'device.description="%s"' % s.replace(" ", r"\ ")


def hw_default(kind):
    """Real default sink/source, ignoring our own devices."""
    name = pactl("get-default-" + kind).stdout.strip()
    if name and _PREFIX not in name:
        return name
    for ln in pactl("list", "short", kind + "s").stdout.splitlines():
        parts = ln.split("\t")
        if len(parts) >= 2 and _PREFIX not in parts[1] and ".monitor" not in parts[1]:
            return parts[1]
    return None


def _sink_index(name) -> Optional[str]:
    for ln in pactl("list", "short", "sinks").stdout.splitlines():
        p = ln.split("\t")
        if p[1:2] == [name]:
            return p[0]
    return None


def _unload_ours():
    """Remove any module of ours, including leftovers from a crashed run."""
    for ln in reversed(pactl("list", "short", "modules").stdout.splitlines()):
        p = ln.split("\t")
        if len(p) >= 3 and _PREFIX in p[2]:
            pactl("unload-module", p[0])
            log(f"unloaded module {p[0]} ({p[1]})")


def _links_into(port):
    lines = _pwlink("-l").stdout.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip() != port:
            continue
        srcs, j = [], i + 1
        while j < len(lines) and lines[j].startswith((" ", "\t")):
            s = lines[j].strip()
            if s.startswith("|<-"):
                srcs.append(s[3:].strip())
            j += 1
        return srcs
    return []


def _fix_routing():
    # PipeWire sometimes races the remap-source's capture stream onto the
    # default sink's monitor, leaking all system audio into the mic.
    if not shutil.which("pw-link"):
        return
    stream_in = f"input.{MIC}"
    for _ in range(15):
        if f"{stream_in}:input_FL" in _pwlink("-l").stdout:
            break
        time.sleep(0.15)
    for ch in ("FL", "FR"):
        dst = f"{stream_in}:input_{ch}"
        for src in _links_into(dst):
            if not src.startswith(f"{SINK}:monitor_"):
                _pwlink("-d", src, dst)
                log(f"mic routing: disconnected leak {src} -> {dst}")
        _pwlink(f"{SINK}:monitor_{ch}", dst)


def _sink_inputs():
    try:
        return json.loads(pactl("-f", "json", "list", "sink-inputs").stdout)
    except ValueError:
        return []


def _app_key(si):
    p = si.get("properties", {})
    return p.get("application.process.binary") or p.get("application.name") or "unknown"


def _app_label(si):
    p = si.get("properties", {})
    return p.get("application.name") or _app_key(si)


class LinuxBackend(Backend):
    mic_label = MIC_DESC
    capture_mutes_app = True

    def __init__(self):
        self._cap_modules = []
        self._cap_monitor_mod = None
        self._moved = {}  # sink-input index -> sink it came from
        self.capturing = None

    # ── virtual mic ─────────────────────────────────────────────────────

    def prepare(self):
        if not shutil.which("pactl"):
            return "pactl not found — install pipewire-pulse (or pulseaudio-utils) and make sure it's running."
        if pactl("info").returncode != 0:
            return "No PipeWire/PulseAudio server is running."
        orig_sink, orig_source = hw_default("sink"), hw_default("source")
        _unload_ours()
        r = pactl("load-module", "module-null-sink", f"sink_name={SINK}",
                  f"sink_properties={_desc(SINK_DESC)}")
        log(f"null-sink rc={r.returncode} {r.stdout.strip()!r} {r.stderr.strip()!r}")
        if r.returncode != 0:
            return f"Virtual mic failed: {r.stderr.strip()}"
        r = pactl("load-module", "module-remap-source", f"master={SINK}.monitor",
                  f"source_name={MIC}", "channel_map=front-left,front-right",
                  f"source_properties={_desc(MIC_DESC)}")
        log(f"remap-source rc={r.returncode} {r.stdout.strip()!r} {r.stderr.strip()!r}")
        err = None if r.returncode == 0 else f"Mic source failed: {r.stderr.strip()}"
        if not err:
            _fix_routing()
        # Creating our devices must never flip the system defaults.
        if orig_sink:
            pactl("set-default-sink", orig_sink)
        if orig_source:
            pactl("set-default-source", orig_source)
        return err

    def shutdown(self):
        if self.capturing:
            self.stop_capture()
        _unload_ours()

    def mic_target(self):
        dev = player.find_playback(SINK_DESC)
        if not dev:
            raise RuntimeError("The virtual mic isn't available (is PipeWire/PulseAudio running?)")
        return dev

    def setup_checks(self):
        checks = []
        have = bool(shutil.which("pactl"))
        checks.append(Check(have, "pactl found" if have else
                            "pactl is missing — install pipewire-pulse or pulseaudio-utils"))
        if have:
            info = pactl("info")
            name = next((ln.split(":", 1)[1].strip() for ln in info.stdout.splitlines()
                         if ln.startswith("Server Name")), "")
            ok = info.returncode == 0
            checks.append(Check(ok, f"Audio server running ({name})" if ok else
                                "No PipeWire/PulseAudio server is running"))
        return checks

    # ── app capture ─────────────────────────────────────────────────────

    def _streams(self):
        # Skip loopbacks (owner_module set), anything already in the mic, and
        # our own playback so an app can't capture itself.
        mic_sink = _sink_index(SINK)
        me = str(os.getpid())
        return [si for si in _sink_inputs()
                if si.get("owner_module") is None
                and str(si["sink"]) != mic_sink
                and si.get("properties", {}).get("application.process.id") != me]

    def list_apps(self):
        seen = {}
        for si in self._streams():
            seen.setdefault(_app_key(si), _app_label(si))
        if self.capturing:
            seen.setdefault(self.capturing.key, self.capturing.label)
        return [AppInfo(k, v) for k, v in sorted(seen.items(), key=lambda kv: kv[1].lower())]

    def _load(self, *args):
        r = pactl("load-module", *args)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "pactl load-module failed")
        return r.stdout.strip()

    def start_capture(self, app, monitor):
        orig = hw_default("sink"), hw_default("source")
        try:
            self._cap_modules = [
                self._load("module-null-sink", f"sink_name={CAP}", f"sink_properties={_desc(CAP_DESC)}"),
                self._load("module-loopback", f"source={CAP}.monitor", f"sink={SINK}", "latency_msec=30"),
            ]
            if monitor:
                self._monitor_on()
        except RuntimeError:
            self._unload_capture()
            raise
        finally:  # loading modules must not move the system defaults
            if orig[0]:
                pactl("set-default-sink", orig[0])
            if orig[1]:
                pactl("set-default-source", orig[1])
        self.capturing = app
        self.poll()

    def _monitor_on(self):
        sink = hw_default("sink")
        if sink and not self._cap_monitor_mod:
            self._cap_monitor_mod = self._load("module-loopback", f"source={CAP}.monitor",
                                               f"sink={sink}", "latency_msec=30")

    def _monitor_off(self):
        if self._cap_monitor_mod:
            pactl("unload-module", self._cap_monitor_mod)
            self._cap_monitor_mod = None

    def set_capture_monitor(self, on):
        if self.capturing:
            self._monitor_on() if on else self._monitor_off()

    def poll(self):
        # Apps often open a fresh stream per track or tab; keep pulling them over.
        if not self.capturing:
            return
        cap = _sink_index(CAP)
        if not cap:
            return
        for si in self._streams():
            if _app_key(si) == self.capturing.key and str(si["sink"]) != cap:
                self._moved[si["index"]] = si["sink"]
                pactl("move-sink-input", str(si["index"]), CAP)

    def stop_capture(self):
        for idx, sink in list(self._moved.items()):  # put streams back first
            pactl("move-sink-input", str(idx), str(sink))
        self._moved.clear()
        self._unload_capture()
        self.capturing = None

    def _unload_capture(self):
        for m in [self._cap_monitor_mod, *reversed(self._cap_modules)]:
            if m:
                pactl("unload-module", m)
        self._cap_modules, self._cap_monitor_mod = [], None
