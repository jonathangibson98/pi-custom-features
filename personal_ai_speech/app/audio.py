"""Audio helpers: encode/decode and stitching."""

from __future__ import annotations

import io

import numpy as np
import soundfile as sf

MEDIA_TYPES = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "flac": "audio/flac",
    "opus": "audio/ogg",
    "pcm": "audio/pcm",
}


def encode(samples: np.ndarray, sample_rate: int, fmt: str) -> bytes:
    """Encode mono float samples as mp3, wav, flac, opus or raw 16-bit pcm."""
    fmt = fmt.lower()
    samples = np.clip(samples, -1.0, 1.0)
    if fmt == "pcm":
        return (samples * 32767).astype("<i2").tobytes()
    buffer = io.BytesIO()
    if fmt == "wav":
        sf.write(buffer, samples, sample_rate, format="WAV", subtype="PCM_16")
    elif fmt == "flac":
        sf.write(buffer, samples, sample_rate, format="FLAC", subtype="PCM_16")
    elif fmt == "mp3":
        sf.write(buffer, samples, sample_rate, format="MP3")
    elif fmt == "opus":
        sf.write(buffer, samples, sample_rate, format="OGG", subtype="OPUS")
    else:
        raise ValueError(f"Unsupported format '{fmt}'. Use mp3, wav, flac, opus or pcm.")
    return buffer.getvalue()


def decode(data: bytes) -> tuple[np.ndarray, int]:
    """Decode any audio libsndfile can read to mono float32."""
    samples, rate = sf.read(io.BytesIO(data), dtype="float32", always_2d=False)
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    return samples.astype("float32"), int(rate)


def silence(sample_rate: int, seconds: float) -> np.ndarray:
    """Return a block of silence."""
    return np.zeros(max(0, int(sample_rate * seconds)), dtype="float32")


def match_rate(samples: np.ndarray, rate: int, target: int) -> np.ndarray:
    """Cheap linear resample, only used if an upstream changes sample rate between calls."""
    if rate == target or len(samples) == 0:
        return samples
    new_len = int(len(samples) * target / rate)
    return np.interp(
        np.linspace(0, len(samples) - 1, new_len), np.arange(len(samples)), samples
    ).astype("float32")
