"""OpenAI-compatible speech server: /v1/audio/speech and /v1/audio/transcriptions."""

from __future__ import annotations

import asyncio
import hmac
import logging
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel

from . import audio
from .emotion import EMOTIONS, infer_emotion, normalize, split_segments
from .engines import EngineError, KokoroEngine, ProxyEngine
from .settings import load_settings
from .stt import WhisperService

settings = load_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
LOGGER = logging.getLogger("personal_ai_speech")

# Home Assistant's ingress gateway. Requests from it are already authenticated by HA.
INGRESS_IP = "172.30.32.2"
MAX_INPUT_CHARS = 8000

engine = KokoroEngine(settings) if settings.tts_engine == "kokoro" else ProxyEngine(settings)
whisper = WhisperService(settings)
UI_HTML = (Path(__file__).parent / "ui.html").read_text(encoding="utf-8")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Start loading models in the background so the API answers immediately."""
    LOGGER.info("TTS engine: %s | STT: %s", engine.name, whisper.state)
    engine.start()
    if settings.stt_preload:
        whisper.preload()
    yield


app = FastAPI(title="Personal AI Speech", lifespan=lifespan)


def check_auth(request: Request) -> None:
    """Require the add-on API key when one is set."""
    if not settings.api_key:
        return
    if request.client and request.client.host == INGRESS_IP:
        return
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and hmac.compare_digest(token.strip(), settings.api_key):
        return
    raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.exception_handler(HTTPException)
async def http_error(_: Request, err: HTTPException) -> JSONResponse:
    """Return errors in the shape the OpenAI client library understands."""
    return JSONResponse({"error": {"message": err.detail, "type": "invalid_request_error"}}, err.status_code)


@app.exception_handler(EngineError)
async def engine_error(_: Request, err: EngineError) -> JSONResponse:
    """Turn engine problems into readable API errors."""
    return JSONResponse({"error": {"message": str(err), "type": "server_error"}}, err.status)


class SpeechRequest(BaseModel):
    """Body of /v1/audio/speech (OpenAI schema plus an optional emotion)."""

    model: str | None = None
    input: str
    voice: str | None = None
    response_format: str | None = "mp3"
    speed: float | None = None
    instructions: str | None = None
    emotion: str | None = None


@app.get("/", response_class=HTMLResponse)
async def ui() -> str:
    """Small test page (also the add-on's sidebar panel)."""
    return UI_HTML


@app.get("/health")
async def health() -> dict:
    """Status for the test page and for debugging."""
    return {
        "status": "ok",
        "tts": {
            "engine": engine.name,
            "state": engine.state,
            "error": getattr(engine, "error", ""),
            "voices": len(engine.voices()),
        },
        "stt": {
            "enabled": whisper.enabled,
            "model": settings.stt_model,
            "state": whisper.state,
            "error": whisper.error,
        },
        "auth_required": bool(settings.api_key),
    }


@app.get("/v1/models", dependencies=[Depends(check_auth)])
async def models() -> dict:
    """List the models. The Personal AI integration calls this to check the connection."""
    tts_id = "kokoro-82m" if engine.name == "kokoro" else (settings.upstream_model or "proxy")
    data = [{"id": tts_id, "object": "model", "owned_by": "personal_ai_speech"}]
    if whisper.enabled:
        data.append({"id": f"whisper-{settings.stt_model}", "object": "model", "owned_by": "personal_ai_speech"})
    return {"object": "list", "data": data}


@app.get("/v1/audio/voices", dependencies=[Depends(check_auth)])
async def voices() -> dict:
    """Voices and emotion tags this server understands."""
    return {
        "voices": engine.voices(),
        "default": engine.default_voice,
        "emotions": sorted(EMOTIONS),
    }


@app.post("/v1/audio/speech", dependencies=[Depends(check_auth)])
async def speech(req: SpeechRequest) -> Response:
    """Turn text into speech. Inline [emotion] tags switch the delivery mid-sentence."""
    text = req.input.strip()
    if not text:
        raise HTTPException(400, "'input' is empty")
    if len(text) > MAX_INPUT_CHARS:
        raise HTTPException(400, f"'input' is longer than {MAX_INPUT_CHARS} characters")
    fmt = (req.response_format or "mp3").lower()
    if fmt not in audio.MEDIA_TYPES:
        raise HTTPException(400, f"Unsupported response_format '{fmt}'. Use mp3, wav, flac, opus or pcm.")

    base_emotion = normalize(req.emotion) or infer_emotion(req.instructions) or "neutral"
    segments = split_segments(text, base_emotion)
    if not segments:
        raise HTTPException(400, "Nothing to say after removing emotion tags")
    speed = req.speed if req.speed else settings.default_speed

    pieces: list[np.ndarray] = []
    rate: int | None = None
    for emotion, chunk in segments:
        samples, chunk_rate = await engine.synth(chunk, req.voice, speed, emotion, req.instructions)
        if rate is None:
            rate = chunk_rate
        else:
            samples = audio.match_rate(samples, chunk_rate, rate)
        if pieces:
            pieces.append(audio.silence(rate, 0.12 * EMOTIONS[emotion].pause))
        pieces.append(samples)

    assert rate is not None
    data = await asyncio.to_thread(audio.encode, np.concatenate(pieces), rate, fmt)
    return Response(content=data, media_type=audio.MEDIA_TYPES[fmt])


@app.post("/v1/audio/transcriptions", dependencies=[Depends(check_auth)])
async def transcriptions(
    file: UploadFile = File(...),
    model: str | None = Form(None),
    language: str | None = Form(None),
    prompt: str | None = Form(None),
    response_format: str = Form("json"),
) -> Response:
    """Speech-to-text (OpenAI compatible)."""
    if not whisper.enabled:
        raise HTTPException(404, "Speech-to-text is switched off in the add-on options (stt_enabled).")
    data = await file.read()
    if not data:
        raise HTTPException(400, "The audio file is empty")
    suffix = Path(file.filename or "audio.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(data)
        path = handle.name
    try:
        text, detected, duration = await asyncio.to_thread(whisper.transcribe, path, language, prompt)
    except Exception as err:
        LOGGER.exception("Transcription failed")
        raise EngineError(f"Transcription failed: {err}", 500) from err
    finally:
        os.unlink(path)
    if response_format == "text":
        return PlainTextResponse(text)
    if response_format == "verbose_json":
        return JSONResponse({"text": text, "language": detected, "duration": duration})
    return JSONResponse({"text": text})
