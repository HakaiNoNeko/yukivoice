"""Kokoro text-to-speech: model download/install, voice list, synthesis.

The engine (kokoro-onnx + onnxruntime + espeak-ng) ships inside the app. What the
setup wizard "installs" is the model weights and the voice pack, downloaded once
from the kokoro-onnx GitHub release into the user's data folder.
"""

import re
import threading
from dataclasses import dataclass

import numpy as np
import requests

from . import config
from .log import log

_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/"

VOICES_FILE = ("voices-v1.0.bin", 28214398)

# variant -> (label, (filename, exact size in bytes))
MODELS = {
    "standard": ("Standard — best quality (310 MB)", ("kokoro-v1.0.onnx", 325505369)),
    "lite": ("Lite — smaller and faster, slightly lower quality (110 MB)", ("kokoro-v1.0.int8.onnx", 114119327)),
}

# (kokoro lang code, label, preview sentence)
LANGUAGES = [
    ("en-us", "English (US)", "Hello! This is what I sound like."),
    ("en-gb", "English (UK)", "Hello! This is what I sound like."),
    ("ja", "Japanese", "こんにちは、これが私の声です。"),
    ("cmn", "Mandarin Chinese", "你好，这是我的声音。"),
    ("es", "Spanish", "¡Hola! Así es como sueno."),
    ("fr-fr", "French", "Bonjour ! Voici ma voix."),
    ("hi", "Hindi", "नमस्ते, यह मेरी आवाज़ है।"),
    ("it", "Italian", "Ciao! Questa è la mia voce."),
    ("pt-br", "Portuguese (Brazil)", "Olá! Esta é a minha voz."),
]
_LANG_BY_PREFIX = {"a": "en-us", "b": "en-gb", "j": "ja", "z": "cmn", "e": "es",
                   "f": "fr-fr", "h": "hi", "i": "it", "p": "pt-br"}
_LANG_INFO = {code: (label, sample) for code, label, sample in LANGUAGES}


@dataclass(frozen=True)
class Voice:
    id: str
    lang: str
    lang_label: str
    gender: str
    name: str

    @property
    def display(self) -> str:
        return f"{self.name} ({self.gender})"


def describe_voice(voice_id: str) -> Voice:
    prefix, _, rest = voice_id.partition("_")
    lang = _LANG_BY_PREFIX.get(prefix[:1], "en-us")
    gender = "female" if prefix[1:2] == "f" else "male"
    return Voice(voice_id, lang, _LANG_INFO[lang][0], gender, rest.replace("_", " ").title() or voice_id)


def sample_text(lang: str) -> str:
    return _LANG_INFO.get(lang, _LANG_INFO["en-us"])[1]


# ── install / download ──────────────────────────────────────────────────────

def model_path(variant: str):
    return config.model_dir() / MODELS[variant][1][0]


def voices_path():
    return config.model_dir() / VOICES_FILE[0]


def is_installed(variant: str) -> bool:
    return model_path(variant).is_file() and voices_path().is_file()


def voice_ids() -> list:
    """Voice ids from the installed voice pack (an .npz of style vectors)."""
    with np.load(voices_path()) as z:
        return sorted(z.files)


class Cancelled(Exception):
    pass


def _fetch(url, dest, expected, done_before, grand_total, progress, cancel):
    part = dest.with_suffix(dest.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    with requests.get(url, headers=headers, stream=True, timeout=30) as r:
        if r.status_code == 416:       # the .part file is already complete
            have = expected
        elif r.status_code == 206:
            pass
        else:
            r.raise_for_status()
            have = 0                   # server ignored Range → restart
        mode = "ab" if have and r.status_code == 206 else "wb"
        got = have
        if r.status_code != 416:
            with open(part, mode) as f:
                for chunk in r.iter_content(1 << 17):
                    if cancel.is_set():
                        raise Cancelled()
                    f.write(chunk)
                    got += len(chunk)
                    progress(done_before + got, grand_total)
    if part.stat().st_size != expected:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"{dest.name}: downloaded size does not match (corrupt download, try again)")
    part.replace(dest)


def install(variant: str, progress, cancel: threading.Event) -> None:
    """Download the model + voice pack. progress(done_bytes, total_bytes)."""
    model_name, model_size = MODELS[variant][1]
    files = [(model_name, model_size), VOICES_FILE]
    total = sum(size for _, size in files)
    done = 0
    for name, size in files:
        dest = config.model_dir() / name
        if dest.is_file() and dest.stat().st_size == size:
            done += size
            progress(done, total)
            continue
        log(f"downloading {name}")
        _fetch(_RELEASE + name, dest, size, done, total, progress, cancel)
        done += size
    log("kokoro install complete")


# ── text preparation (ported from the original Kokoro API wrapper) ──────────

_kks = None


def _kakasi():
    global _kks
    if _kks is None:
        import pykakasi
        _kks = pykakasi.kakasi()
    return _kks


def _is_jp_char(ch):
    return "\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff"


def _is_en_char(ch):
    return ch.isascii() and ch.isalpha()


def resolve_language(text: str, voice: str, choice: str = "auto") -> str:
    """Pick the kokoro language code for this message."""
    if choice != "auto":
        return choice
    voice_lang = describe_voice(voice).lang
    if voice_lang != "cmn":
        jp = sum(1 for c in text if _is_jp_char(c))
        en = sum(1 for c in text if _is_en_char(c))
        if jp > en:
            return "ja"
    # A Japanese voice reading non-Japanese text speaks English.
    return "en-us" if voice_lang == "ja" else voice_lang


def _romanize(text):
    out = []
    for item in _kakasi().convert(text):
        out.append(item["hepburn"] if any(_is_jp_char(c) for c in item["orig"]) else item["orig"])
    return "".join(out)


def _kanji_to_hira(text):
    out = []
    for item in _kakasi().convert(text):
        out.append(item["hira"] if any("\u4e00" <= c <= "\u9fff" for c in item["orig"]) else item["orig"])
    return "".join(out)


def _alpha_to_kana(text):
    import jaconv
    return re.sub(r"[A-Za-z]+", lambda m: jaconv.alphabet2kana(m.group(0)), text)


def prepare_text(text: str, lang: str) -> str:
    if lang == "ja":
        text = _alpha_to_kana(_kanji_to_hira(text))
        return re.sub("[^\u3000-\u9fff\uff00-\uffef\u3002\u3001\uff01\uff1f\u301c\u2026\u300c\u300d\u300e\u300f\u3010\u3011\\s]", "", text)
    # espeak's phonemizer mangles newlines and doubled spaces.
    text = re.sub(r"\s+", " ", text).strip()
    # pykakasi mangles pure-ASCII input, so only romanize real Japanese.
    if any(_is_jp_char(c) for c in text):
        text = _romanize(text)
    if text and text[-1] not in ".!?…:;,":
        text += "."
    return text


def _chunk_ja(text, max_chars=50):
    chunks = []
    for part in re.split(r"(?<=[。！？.!?])\s*", text):
        part = part.strip()
        while len(part) > max_chars:
            cut = max_chars
            for sep in ("、", "，", ",", " "):
                idx = part.rfind(sep, 0, max_chars)
                if idx > max_chars // 2:
                    cut = idx + 1
                    break
            chunks.append(part[:cut].strip())
            part = part[cut:].strip()
        if part:
            chunks.append(part)
    return chunks or [text]


_HAS_LETTER = re.compile(r"[^\W_]", re.UNICODE)


def _chunk_other(text, max_chars=320):
    """Sentence-aligned chunks; kokoro-onnx repeats the tail of long paragraphs
    when fed everything in one call."""
    chunks, cur = [], ""
    for sent in re.split(r"(?<=[.!?…])\s+", text.strip()):
        sent = sent.strip()
        if not sent:
            continue
        if cur and len(cur) + 1 + len(sent) > max_chars:
            chunks.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
        while len(cur) > max_chars:
            cut = max_chars
            for sep in (", ", "; ", " - ", " "):
                idx = cur.rfind(sep, 0, max_chars)
                if idx > max_chars // 2:
                    cut = idx + len(sep)
                    break
            chunks.append(cur[:cut].strip())
            cur = cur[cut:].strip()
    if cur:
        chunks.append(cur)
    return [c for c in chunks if _HAS_LETTER.search(c)] or [text]


# ── engine ──────────────────────────────────────────────────────────────────

class Engine:
    """Lazily loads Kokoro once and synthesizes on demand (thread-safe)."""

    def __init__(self, variant: str):
        self.variant = variant
        self._kokoro = None
        self._lock = threading.Lock()

    def _load(self):
        if self._kokoro is None:
            if not is_installed(self.variant):
                raise RuntimeError("The voice engine isn't installed yet. Run Setup (Tools → Setup wizard).")
            from kokoro_onnx import Kokoro
            log(f"loading Kokoro model {model_path(self.variant).name}")
            self._kokoro = Kokoro(str(model_path(self.variant)), str(voices_path()))
        return self._kokoro

    def synth(self, text: str, voice: str, speed: float = 1.0, language: str = "auto"):
        """Returns (float32 mono samples, sample rate)."""
        lang = resolve_language(text, voice, language)
        text = prepare_text(text, lang)
        chunks = _chunk_ja(text) if lang == "ja" else _chunk_other(text)
        with self._lock:
            k = self._load()
            parts, sr = [], 24000
            for chunk in chunks:
                if not chunk.strip():
                    continue
                s, sr = k.create(chunk, voice=voice, speed=speed, lang=lang)
                parts.append(s)
                parts.append(np.zeros(int(sr * 0.07), dtype=s.dtype))  # natural gap
        if not parts:
            return np.zeros(0, dtype=np.float32), sr
        return np.concatenate(parts).astype(np.float32), sr
