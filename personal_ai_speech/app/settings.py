"""Add-on settings, read from the Supervisor's /data/options.json."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Everything the user can set in the add-on's Configuration tab."""

    api_key: str
    tts_engine: str
    kokoro_model: str
    default_voice: str
    default_speed: float
    upstream_url: str
    upstream_api_key: str
    upstream_model: str
    upstream_voice: str
    upstream_send_instructions: bool
    stt_enabled: bool
    stt_model: str
    stt_language: str
    stt_preload: bool
    log_level: str
    data_dir: Path
    port: int


def _s(value: object, default: str = "") -> str:
    return str(value).strip() if value is not None else default


def load_settings() -> Settings:
    """Load options. PAS_OPTIONS_FILE / PAS_DATA_DIR let you run this outside Home Assistant."""
    options_path = Path(os.environ.get("PAS_OPTIONS_FILE", "/data/options.json"))
    try:
        raw = json.loads(options_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        raw = {}
    return Settings(
        api_key=_s(raw.get("api_key")),
        tts_engine=_s(raw.get("tts_engine"), "kokoro"),
        kokoro_model=_s(raw.get("kokoro_model"), "int8"),
        default_voice=_s(raw.get("default_voice"), "af_heart"),
        default_speed=float(raw.get("default_speed") or 1.0),
        upstream_url=_s(raw.get("upstream_url")).rstrip("/"),
        upstream_api_key=_s(raw.get("upstream_api_key")),
        upstream_model=_s(raw.get("upstream_model")),
        upstream_voice=_s(raw.get("upstream_voice"), "coral"),
        upstream_send_instructions=bool(raw.get("upstream_send_instructions", True)),
        stt_enabled=bool(raw.get("stt_enabled", True)),
        stt_model=_s(raw.get("stt_model"), "base.en"),
        stt_language=_s(raw.get("stt_language")),
        stt_preload=bool(raw.get("stt_preload", True)),
        log_level=_s(raw.get("log_level"), "info").lower(),
        data_dir=Path(os.environ.get("PAS_DATA_DIR", "/data")),
        port=int(os.environ.get("PAS_PORT", "8880")),
    )
