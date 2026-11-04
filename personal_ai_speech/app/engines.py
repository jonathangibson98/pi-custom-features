"""Text-to-speech engines: local Kokoro, or a proxy to another OpenAI-compatible server."""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path

import httpx
import numpy as np

from . import audio
from .emotion import EMOTIONS
from .settings import Settings

LOGGER = logging.getLogger("personal_ai_speech.engines")

KOKORO_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
KOKORO_FILES = {
    "int8": "kokoro-v1.0.int8.onnx",
    "fp16": "kokoro-v1.0.fp16.onnx",
    "fp32": "kokoro-v1.0.onnx",
}
KOKORO_VOICES_FILE = "voices-v1.0.bin"

# Kokoro voice names start with a language letter.
LANG_BY_PREFIX = {
    "a": "en-us",
    "b": "en-gb",
    "e": "es",
    "f": "fr-fr",
    "h": "hi",
    "i": "it",
    "j": "ja",
    "p": "pt-br",
    "z": "cmn",
}

# So clients that ask for an OpenAI voice name still get something sensible.
OPENAI_VOICE_ALIASES = {
    "alloy": "af_alloy",
    "ash": "am_adam",
    "ballad": "bm_george",
    "coral": "af_bella",
    "echo": "am_echo",
    "fable": "bm_fable",
    "nova": "af_nova",
    "onyx": "am_onyx",
    "sage": "af_sarah",
    "shimmer": "af_sky",
    "verse": "am_michael",
}


class EngineError(Exception):
    """Raised when speech can't be made. status is the HTTP status to return."""

    def __init__(self, message: str, status: int = 500) -> None:
        super().__init__(message)
        self.status = status


def _download(url: str, dest: Path) -> None:
    """Download url to dest (atomically), logging progress."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    LOGGER.info("Downloading %s", url)
    with httpx.stream("GET", url, follow_redirects=True, timeout=60.0) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length") or 0)
        done = 0
        next_mark = 10
        with part.open("wb") as handle:
            for chunk in response.iter_bytes(1 << 20):
                handle.write(chunk)
                done += len(chunk)
                if total and done * 100 // total >= next_mark:
                    LOGGER.info("  %s: %d%%", dest.name, next_mark)
                    next_mark += 10
    part.replace(dest)


class KokoroEngine:
    """Local Kokoro-82M (ONNX) text-to-speech."""

    name = "kokoro"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.state = "starting"  # starting | downloading | ready | error
        self.error = ""
        self._kokoro = None
        self._lock = threading.Lock()
        self._voices: list[str] = []

    def start(self) -> None:
        """Download (first run only) and load the model in the background."""
        threading.Thread(target=self._prepare, name="kokoro-prepare", daemon=True).start()

    def _prepare(self) -> None:
        try:
            model_dir = self.settings.data_dir / "models" / "kokoro"
            model_file = KOKORO_FILES.get(self.settings.kokoro_model, KOKORO_FILES["int8"])
            model_path = model_dir / model_file
            voices_path = model_dir / KOKORO_VOICES_FILE
            for path in (model_path, voices_path):
                if not path.exists():
                    self.state = "downloading"
                    _download(f"{KOKORO_RELEASE}/{path.name}", path)
            LOGGER.info("Loading Kokoro model %s", model_file)
            from kokoro_onnx import Kokoro  # imported late so the API starts instantly

            self._kokoro = Kokoro(str(model_path), str(voices_path))
            self._voices = sorted(self._kokoro.get_voices())
            self.state = "ready"
            LOGGER.info("Kokoro ready with %d voices", len(self._voices))
        except Exception as err:
            self.state = "error"
            self.error = str(err)
            LOGGER.exception("Kokoro failed to start")

    @property
    def default_voice(self) -> str:
        return self.settings.default_voice

    def voices(self) -> list[str]:
        return list(self._voices)

    def _resolve_voice(self, voice: str | None):
        """Return (style_or_name, language). Supports 'af_heart+af_bella' blends."""
        name = (voice or "").strip() or self.default_voice
        name = OPENAI_VOICE_ALIASES.get(name.lower(), name)
        if "+" in name:
            parts = [p.strip() for p in name.split("+") if p.strip() in self._voices]
            if len(parts) >= 2:
                style = np.mean([self._kokoro.get_voice_style(p) for p in parts], axis=0)
                return style, LANG_BY_PREFIX.get(parts[0][0], "en-us")
            name = parts[0] if parts else self.default_voice
        if name not in self._voices:
            LOGGER.warning("Unknown voice '%s', using %s", name, self.default_voice)
            name = self.default_voice if self.default_voice in self._voices else self._voices[0]
        return name, LANG_BY_PREFIX.get(name[0], "en-us")

    def _synth_blocking(self, text: str, voice: str | None, speed: float, emotion: str):
        profile = EMOTIONS[emotion]
        with self._lock:
            style, lang = self._resolve_voice(voice)
            samples, rate = self._kokoro.create(
                text,
                voice=style,
                speed=min(2.0, max(0.5, speed * profile.speed)),
                lang=lang,
                sentence_pause=0.25 * profile.pause,
                clause_pause=0.1 * profile.pause,
            )
        return (samples * profile.gain).astype("float32"), int(rate)

    async def synth(self, text, voice, speed, emotion, instructions=None):
        """Make one emotion segment of speech."""
        if self.state == "error":
            raise EngineError(f"Kokoro failed to start: {self.error}", 503)
        if self.state != "ready":
            raise EngineError(
                "The voice model is still downloading or loading (first start only). "
                "Check the add-on log and try again in a minute.",
                503,
            )
        try:
            return await asyncio.to_thread(self._synth_blocking, text, voice, speed, emotion)
        except EngineError:
            raise
        except Exception as err:
            LOGGER.exception("Kokoro synthesis failed")
            raise EngineError(f"Kokoro failed: {err}", 500) from err


class ProxyEngine:
    """Forward speech requests to another OpenAI-compatible server (OpenAI, a GPU box...)."""

    name = "proxy"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.state = "ready" if settings.upstream_url else "error"
        self.error = "" if settings.upstream_url else "Set 'upstream_url' in the add-on options."
        self._client = httpx.AsyncClient(timeout=120.0)

    def start(self) -> None:
        """Nothing to load."""

    @property
    def default_voice(self) -> str:
        return self.settings.upstream_voice

    def voices(self) -> list[str]:
        return []

    async def synth(self, text, voice, speed, emotion, instructions=None):
        """Make one segment by asking the upstream server."""
        if self.state != "ready":
            raise EngineError(self.error, 503)
        payload: dict[str, object] = {
            "model": self.settings.upstream_model,
            "input": text,
            "voice": voice or self.default_voice,
            "response_format": "wav",
        }
        if speed and abs(speed - 1.0) > 0.01:
            payload["speed"] = speed
        if self.settings.upstream_send_instructions:
            given = instructions or ""
            profile_text = ""
            # The Personal AI integration already writes "Emotion: happy. ..." itself.
            if emotion != "neutral" and f"Emotion: {emotion}" not in given:
                profile_text = f"Emotion: {emotion}. {EMOTIONS[emotion].text}"
            joined = " ".join(p for p in (profile_text, given) if p).strip()
            if joined:
                payload["instructions"] = joined
        headers = {}
        if self.settings.upstream_api_key:
            headers["Authorization"] = f"Bearer {self.settings.upstream_api_key}"
        try:
            response = await self._client.post(
                f"{self.settings.upstream_url}/audio/speech", json=payload, headers=headers
            )
        except httpx.HTTPError as err:
            raise EngineError(f"Could not reach the upstream server: {err}", 502) from err
        if response.status_code >= 400:
            raise EngineError(
                f"Upstream server said {response.status_code}: {response.text[:300]}", 502
            )
        try:
            return audio.decode(response.content)
        except Exception as err:
            raise EngineError(f"Upstream did not return readable audio: {err}", 502) from err
