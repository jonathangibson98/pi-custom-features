"""Local speech-to-text with faster-whisper (runs on the Pi's CPU)."""

from __future__ import annotations

import logging
import os
import threading

from .settings import Settings

LOGGER = logging.getLogger("personal_ai_speech.stt")


class WhisperService:
    """Lazy-loading faster-whisper wrapper."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.state = "idle" if settings.stt_enabled else "disabled"  # idle|loading|ready|error
        self.error = ""
        self._model = None
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.settings.stt_enabled

    def preload(self) -> None:
        """Load the model in the background so the first voice command isn't slow."""
        if self.enabled:
            threading.Thread(target=self._safe_load, name="whisper-preload", daemon=True).start()

    def _safe_load(self) -> None:
        try:
            self._load()
        except Exception:
            LOGGER.exception("Whisper failed to load")

    def _load(self):
        with self._lock:
            if self._model is not None:
                return self._model
            self.state = "loading"
            try:
                from faster_whisper import WhisperModel

                LOGGER.info("Loading Whisper model '%s' (downloads on first use)", self.settings.stt_model)
                self._model = WhisperModel(
                    self.settings.stt_model,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=os.cpu_count() or 4,
                    download_root=str(self.settings.data_dir / "models" / "whisper"),
                )
            except Exception as err:
                self.state = "error"
                self.error = str(err)
                raise
            self.state = "ready"
            LOGGER.info("Whisper ready")
            return self._model

    def transcribe(self, path: str, language: str | None, prompt: str | None) -> tuple[str, str, float]:
        """Transcribe an audio file. Returns (text, language, duration_seconds)."""
        model = self._load()
        lang = (language or self.settings.stt_language or "").split("-")[0].strip().lower() or None
        if self.settings.stt_model.endswith(".en"):
            lang = "en"
        segments, info = model.transcribe(
            path,
            language=lang,
            initial_prompt=prompt or None,
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return text, info.language, float(info.duration)
