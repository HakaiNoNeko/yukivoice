<h1 align="center">YukiVoice</h1>

<p align="center">
  Type text and hear it spoken in your chosen voice <b>through a virtual microphone</b>, in Discord, games, OBS,
  calls, or anything else that accepts a mic.<br>
  YukiVoice can also play sound files into the mic and route another application's audio to it.
</p>

<p align="center">
  <img alt="Visitors" src="https://count.getloli.com/@HakaiNoNeko-yukivoice?name=HakaiNoNeko-yukivoice&theme=yuki-catboy&padding=7&offset=0&align=top&scale=0.5&pixelated=1&darkmode=auto">
</p>

<p align="center">
  <a href="../../releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/HakaiNoNeko/yukivoice?style=flat-square"></a>
  <a href="https://github.com/HakaiNoNeko/yukivoice/actions/workflows/build.yml"><img alt="Build status" src="https://img.shields.io/github/actions/workflow/status/HakaiNoNeko/yukivoice/build.yml?style=flat-square"></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-green?style=flat-square"></a>
  <img alt="Platforms: Windows and Linux" src="https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey?style=flat-square">
  <img alt="Text-to-speech: Kokoro, offline" src="https://img.shields.io/badge/TTS-Kokoro%20(offline)-8A2BE2?style=flat-square">
</p>

<p align="center">
  <a href="#installation">Installation</a> |
  <a href="#features">Features</a> |
  <a href="#custom-voices">Custom voices</a> |
  <a href="#custom-api-engine">Custom API engine</a> |
  <a href="#running-from-source">From source</a> |
  <a href="#building">Building</a>
</p>

---

## Features

YukiVoice has two tabs:

| Tab | Purpose |
|-----|---------|
| **Voice** | Text-to-speech with [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M): 54 voices, 9 languages, runs fully offline |
| **Audio** | Play an audio file into the mic, or capture one application's sound and send it to the mic |

Also included:

- Custom voices, made by blending stock voices or importing Kokoro voice files.
- Support for an external OpenAI-compatible speech server instead of the built-in engine.
- A system tray icon that keeps the microphone live when the window is closed.
- In-place updates from GitHub releases.
- A quick-entry mode: `yukivoice --quick` raises the running window with the text box focused, suitable for a hotkey.

## Installation

| OS | Download | How to run |
|----|----------|------------|
| Windows 10 (2004+) / 11, 64-bit | `YukiVoice.exe` | Double-click |
| Linux x86-64 (PipeWire or PulseAudio) | `YukiVoice-x86_64.AppImage` | `chmod +x YukiVoice-x86_64.AppImage && ./YukiVoice-x86_64.AppImage` |

Download them from the latest [release](../../releases). There is nothing else to install. The first launch opens a
**setup wizard**:

1. **Audio.** On Windows this downloads the free [VB-Cable](https://vb-audio.com/Cable/) virtual-audio driver from
   vb-audio.com and starts its installer. A virtual microphone needs a driver on Windows: approve the admin prompt and
   click *Install Driver*. On Linux the app creates the microphone itself.
2. **Voice engine.** Downloads the Kokoro model and voice pack once (about 350 MB).
3. **Voice.** Choose a language and voice, with a preview button.

Then select the microphone in Discord, your game, or any other application:

| OS | Microphone to select |
|----|----------------------|
| Windows | **CABLE Output (VB-Audio Virtual Cable)** |
| Linux | **YukiVoice Mic** |

Closing the window keeps the app in the tray so the microphone stays live. Quit from the tray menu. You can rerun the
wizard from **Tools > Setup wizard**.

Settings and the log live in `%APPDATA%\YukiVoice` (Windows) or `~/.config/yukivoice` (Linux). The model lives in
`%LOCALAPPDATA%\YukiVoice` (Windows) or `~/.local/share/yukivoice` (Linux).

> [!NOTE]
> **Windows SmartScreen.** The exe is not code-signed, so Windows may show "Windows protected your PC". Click
> *More info*, then *Run anyway*.

### Requirements

- Windows 10 (version 2004 or later) or Windows 11, 64-bit; or a 64-bit Linux desktop running PipeWire or PulseAudio.
- Linux needs `pactl` (package `pipewire-pulse` or `pulseaudio-utils`), which is present on almost every desktop distribution.
- About 350 MB of disk space for the voice model.
- Optional: `ffmpeg` on your `PATH` to play formats beyond wav, mp3, flac and ogg.

## Usage notes

- **Monitor** plays what you send through your speakers as well, so you can hear it.
- **Capturing an application.** On Windows the application keeps playing normally and its sound is also sent to the
  mic (per-process WASAPI loopback). On Linux the application's streams are moved to a private sink and looped into
  the mic, then put back when you release it.
- **Playing files.** wav, mp3, flac and ogg play directly. Other formats (m4a, opus, video) work if `ffmpeg` is on your PATH.
- **Quick entry.** `yukivoice --quick`, or launching a second instance, raises the running window with the text box focused.

## Custom voices

**Tools > Custom voices...** lets you blend up to four stock voices with weights. Kokoro voices are style vectors, so a
blend is a weighted average. You can also choose the language the voice speaks under *Auto* and preview the result.

You can import a Kokoro voice file (`.npy`, shape 510x1x256) as well. Custom voices appear at the top of the voice list
and are stored in `custom_voices.json` next to the settings. No custom voices ship with the app.

## Custom API engine

Instead of the built-in Kokoro engine, YukiVoice can use your own OpenAI-compatible speech server, for example a Kokoro
API. Configure it under **Tools > Setup wizard > Voice engine > Custom API**. The server must provide:

| Endpoint | Details |
|---|---|
| `POST {address}/audio/speech` | Called with `model`, `voice`, `input`, `speed`, `response_format: "wav"`, and `language` unless it is set to Auto |
| `GET {address}/voices` | Returns `{"voices": [...]}` |

The address, key and model are stored in `settings.json` (`engine`, `api_url`, `api_key`, `api_model`). Blended custom
voices require the built-in engine.

## Updates

YukiVoice checks the latest GitHub release shortly after it starts. Toggle this under **Tools > Check for updates on
startup**, or run **Check for updates...** manually. If a newer release exists you can update and restart in place: the
AppImage or exe is replaced with the release build, after its size and SHA-256 are checked. Runs from source only open
the release page.

While the repository is private, GitHub requires a token. Provide one through `update_token` in `settings.json`, the
`YUKIVOICE_GITHUB_TOKEN`, `GITHUB_TOKEN` or `GH_TOKEN` environment variables, or a signed-in `gh` CLI.

## Running from source

```sh
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
PYTHONPATH=src python -m yukivoice               # Windows (PowerShell): $env:PYTHONPATH="src"; python -m yukivoice
```

Set `YUKIVOICE_HOME=/some/dir` to keep all settings and models in one folder.

`yukivoice --selftest [--download standard]` builds the UI offscreen and checks that speech is produced. CI runs this
against the packaged builds.

## Building

CI (`.github/workflows/build.yml`) builds both artifacts on every push to `main` and smoke-tests each one: the AppImage
on Ubuntu 22.04 and the exe on Windows. To build locally:

```sh
pip install -r requirements-build.txt
PY=python packaging/build_appimage.sh            # produces dist/YukiVoice-x86_64.AppImage
python -m PyInstaller packaging/yukivoice.spec   # on Windows, produces dist/YukiVoice.exe
```

### Releasing

```sh
gh release create vX.Y.Z --title "..." --notes "..."
```

This creates the tag. The tag push makes CI build both targets, smoke-test them, and attach `YukiVoice.exe` and
`YukiVoice-x86_64.AppImage` to the release.

## License

YukiVoice's own source code is released under the [MIT License](LICENSE).

The prebuilt `YukiVoice.exe` and AppImage bundle third-party components under their own licenses, including
GPL-3.0 packages (`phonemizer-fork`, `pykakasi`, and the espeak-ng library they rely on) and Qt for Python (LGPL-3.0).
Those components stay under their original terms, and the combined binaries are distributed under the terms of the
GPL-3.0. The complete source for everything in this repository is available here.

## Credits

- Speech: [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (Apache-2.0) via [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) (MIT)
- Windows per-application capture: [ProcTap](https://github.com/m96-chan/ProcTap)
- Virtual microphone on Windows: [VB-Cable](https://vb-audio.com/Cable/) by VB-Audio (donationware, downloaded from their site and not redistributed)
- UI: Qt for Python (LGPL)
- Visitor counter: [Moe Counter](https://github.com/journey-ad/Moe-Counter)
