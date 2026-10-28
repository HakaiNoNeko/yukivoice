"""Kokoro text-to-speech: model download/install, voice list, synthesis.

The engine (kokoro-onnx + onnxruntime + espeak-ng) ships inside the app. What the
setup wizard "installs" is the model weights and the voice pack, downloaded once
from the kokoro-onnx GitHub release into the user's data folder.
"""

import json
import re
import threading
from dataclasses import dataclass

import numpy as np
import requests

from . import config
from .log import log

_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"

VOICES_FILE = ("voices-v1.0.bin", 28214398)

# variant -> (label, (filename, exact size in bytes)).
# Must be the model-files-v1.0 release: the re-exported files in model-files-v1.1
# (including int8/fp16) take `input_ids` and need an integer speed, which breaks
# kokoro-onnx 0.4.7 and fractional speeds; fp16 also has no CPU kernels.
MODELS = {
    "standard": ("Kokoro v1.0 (310 MB)", ("kokoro-v1.0.onnx", 325532387)),
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
    custom: bool = False

    @property
    def display(self) -> str:
        return f"{self.name} (custom)" if self.custom else f"{self.name} ({self.gender})"


# ── custom voices ───────────────────────────────────────────────────────────
# A custom voice is a named blend of stock voices ({"mix": {voice: weight}}) or an
# imported style file ({"file": path to a (510, 1, 256) .npy}), plus the language
# it speaks by default. Kokoro voices are style vectors, so blends are weighted
# averages. "Yuki" ships as a preset (stock jf_alpha), and can be edited or deleted.

CUSTOM_PREFIX = "custom:"
_SEED = {"Yuki": {"mix": {"jf_alpha": 1.0}, "lang": "ja"}}
STYLE_SHAPE = (510, 1, 256)


def _custom_file():
    return config.config_dir() / "custom_voices.json"


def load_custom() -> dict:
    path = _custom_file()
    if not path.exists():
        save_custom(_SEED)
        return json.loads(json.dumps(_SEED))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_custom(data: dict) -> None:
    _custom_file().write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def import_style_file(src: str, name: str) -> str:
    """Copy a voice style .npy into the data folder; returns the stored path."""
    arr = np.load(src)
    if arr.shape != STYLE_SHAPE:
        raise ValueError(f"Not a Kokoro voice file: expected shape {STYLE_SHAPE}, got {arr.shape}")
    dest_dir = config.data_dir() / "voices"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (re.sub(r"[^\w.-]+", "_", name) + ".npy")
    np.save(dest, arr.astype(np.float32))
    return str(dest)


def custom_style(spec: dict, pack) -> np.ndarray:
    """Style array for a custom voice spec; `pack` is the loaded voice pack."""
    if spec.get("file"):
        arr = np.load(spec["file"])
        if arr.shape != STYLE_SHAPE:
            raise RuntimeError(f"Voice file {spec['file']} has the wrong shape {arr.shape}")
        return arr.astype(np.float32)
    mix = {v: float(w) for v, w in (spec.get("mix") or {}).items() if float(w) > 0}
    missing = [v for v in mix if v not in pack]
    if missing:
        raise RuntimeError(f"Custom voice uses voices that aren't in the voice pack: {', '.join(missing)}")
    if not mix:
        raise RuntimeError("This custom voice has no voices in its mix.")
    total = sum(mix.values())
    return (sum(w * pack[v] for v, w in mix.items()) / total).astype(np.float32)


def describe_voice(voice_id: str) -> Voice:
    if voice_id.startswith(CUSTOM_PREFIX):
        name = voice_id[len(CUSTOM_PREFIX):]
        lang = (load_custom().get(name) or {}).get("lang", "en-us")
        return Voice(voice_id, lang, _LANG_INFO.get(lang, _LANG_INFO["en-us"])[0], "custom", name, True)
    prefix, _, rest = voice_id.partition("_")
    lang = _LANG_BY_PREFIX.get(prefix[:1], "en-us")
    gender = "female" if prefix[1:2] == "f" else "male"
    return Voice(voice_id, lang, _LANG_INFO[lang][0], gender, rest.replace("_", " ").title() or voice_id)


def all_voices(variant_installed: bool = True) -> list:
    """Custom voices first, then everything in the installed voice pack."""
    out = [describe_voice(CUSTOM_PREFIX + n) for n in load_custom()]
    if variant_installed and voices_path().is_file():
        out += [describe_voice(v) for v in voice_ids()]
    return out


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


def resolve_language(text: str, voice: str, choice: str = "auto", voice_lang: str = None) -> str:
    """Pick the kokoro language code for this message."""
    if choice != "auto":
        return choice
    voice_lang = voice_lang or describe_voice(voice).lang
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

    def synth(self, text: str, voice, speed: float = 1.0, language: str = "auto"):
        """`voice` is a voice id, or a custom-voice spec dict (used by the editor's
        preview). Returns (float32 mono samples, sample rate)."""
        spec = voice if isinstance(voice, dict) else None
        if spec is None and voice.startswith(CUSTOM_PREFIX):
            spec = load_custom().get(voice[len(CUSTOM_PREFIX):])
            if spec is None:
                raise RuntimeError(f"Custom voice “{voice[len(CUSTOM_PREFIX):]}” no longer exists.")
        if spec is not None:
            lang = resolve_language(text, "custom", language, spec.get("lang", "en-us"))
        else:
            lang = resolve_language(text, voice, language)
        text = prepare_text(text, lang)
        chunks = _chunk_ja(text) if lang == "ja" else _chunk_other(text)
        with self._lock:
            k = self._load()
            style = custom_style(spec, k.voices) if spec is not None else voice
            parts, sr = [], 24000
            for chunk in chunks:
                if not chunk.strip():
                    continue
                s, sr = k.create(chunk, voice=style, speed=speed, lang=lang)
                parts.append(s)
                parts.append(np.zeros(int(sr * 0.07), dtype=s.dtype))  # natural gap
        if not parts:
            return np.zeros(0, dtype=np.float32), sr
        return np.clip(np.concatenate(parts), -1.0, 1.0).astype(np.float32), sr
