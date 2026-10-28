# YukiVoice

Type text and it's spoken in your chosen voice **through a virtual microphone** — in Discord, games, OBS, calls,
anywhere that takes a mic. Also plays sound files into the mic and can send another app's audio to it.

Two tabs:

- **Voice** — text-to-speech with [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) (54 voices, 9 languages, runs offline).
- **Audio** — play an audio file into the mic, or capture one app's sound and send it to the mic.

## Install

| OS | Download | Run |
|----|----------|-----|
| Windows 10 (2004+) / 11, 64-bit | `YukiVoice.exe` | double-click |
| Linux x86-64 (PipeWire or PulseAudio) | `YukiVoice-x86_64.AppImage` | `chmod +x YukiVoice-x86_64.AppImage && ./YukiVoice-x86_64.AppImage` |

Get them from the latest [release](../../releases). Nothing else to install; the first launch opens a **setup wizard**:

1. **Audio** — on Windows, downloads the free [VB-Cable](https://vb-audio.com/Cable/) virtual-audio driver from
   vb-audio.com and starts its installer (a virtual microphone needs a driver on Windows; approve the admin prompt, click
   *Install Driver*). On Linux the mic is created by the app itself.
2. **Voice engine** — downloads the Kokoro model and voice pack once (about 350 MB).
3. **Voice** — pick language and voice, with a preview button.

Then, in Discord/your game/etc. choose the microphone:

- Windows: **CABLE Output (VB-Audio Virtual Cable)**
- Linux: **YukiVoice Mic**

Closing the window keeps the app in the tray so the mic stays live; quit from the tray menu. Rerun the wizard from
**Tools → Setup wizard**. Settings and the log live in `%APPDATA%\YukiVoice` (Windows) / `~/.config/yukivoice` (Linux); the
model in `%LOCALAPPDATA%\YukiVoice` / `~/.local/share/yukivoice`.

> **Windows SmartScreen:** the exe isn't code-signed, so Windows may show "Windows protected your PC". Click
> *More info → Run anyway*.

### Notes

- **Monitor** plays what you send through your speakers too, so you can hear it.
- **Capturing an app** — Windows: the app keeps playing normally and its sound is also sent to the mic (per-process
  WASAPI loopback). Linux: the app's streams are moved to a private sink and looped into the mic, and put back on release.
- Playing files: wav, mp3, flac, ogg directly; other formats (m4a, opus, video…) if `ffmpeg` is on your PATH.
- `yukivoice --quick` (or launching a second time) raises the running window with the text box focused — bind it to a hotkey.
- Linux needs `pactl` (package `pipewire-pulse` / `pulseaudio-utils`; present on virtually every desktop distro).

## Run from source

```sh
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
PYTHONPATH=src python -m yukivoice               # Windows (PowerShell): $env:PYTHONPATH="src"; python -m yukivoice
```

`YUKIVOICE_HOME=/some/dir` keeps all settings and models in one folder. `yukivoice --selftest [--download standard]` builds the UI
offscreen and checks that speech is produced (this is what CI runs against the packaged builds).

## Build

CI (`.github/workflows/build.yml`) builds both artifacts on every push to `main` and smoke-tests each one: the AppImage
on Ubuntu 22.04, the exe on Windows. Locally:

```sh
pip install -r requirements-build.txt
PY=python packaging/build_appimage.sh            # → dist/YukiVoice-x86_64.AppImage
python -m PyInstaller packaging/yukivoice.spec   # on Windows → dist/YukiVoice.exe
```

To release: tag `vX.Y.Z`, wait for CI, download the two artifacts, and attach them to a GitHub release
(`gh release create vX.Y.Z YukiVoice.exe YukiVoice-x86_64.AppImage`).

## Credits

Speech: [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (Apache-2.0) via
[kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) (MIT). Windows per-app capture:
[ProcTap](https://github.com/m96-chan/ProcTap). Virtual mic on Windows: [VB-Cable](https://vb-audio.com/Cable/)
by VB-Audio (donationware — downloaded from their site, not redistributed). UI: Qt for Python (LGPL).
