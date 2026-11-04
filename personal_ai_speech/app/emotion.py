"""Emotion tags: [happy] Hello there! [sad] But not today."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    """How an emotion changes the speech.

    speed/gain/pause are used by the local Kokoro engine (it has no emotion control of its
    own, so this is an approximation). text is the plain-English instruction sent to engines
    that DO understand instructions, like OpenAI's gpt-4o-mini-tts.
    """

    speed: float
    gain: float
    pause: float
    text: str


EMOTIONS: dict[str, Profile] = {
    "neutral": Profile(1.0, 1.0, 1.0, "Speak in a natural, even, conversational tone."),
    "happy": Profile(1.07, 1.0, 0.85, "Speak in a warm, happy, upbeat tone with a smile in your voice."),
    "cheerful": Profile(1.08, 1.0, 0.85, "Speak in a bright, cheerful, friendly tone."),
    "excited": Profile(1.15, 1.08, 0.7, "Speak with high energy and real excitement, quick and enthusiastic."),
    "sad": Profile(0.86, 0.9, 1.4, "Speak in a soft, sad, heavy-hearted tone, slow and subdued."),
    "angry": Profile(1.08, 1.12, 0.7, "Speak in an angry, intense, clipped tone."),
    "calm": Profile(0.93, 0.95, 1.2, "Speak in a calm, soothing, relaxed tone."),
    "gentle": Profile(0.92, 0.85, 1.2, "Speak in a gentle, tender, kind tone."),
    "whisper": Profile(0.9, 0.45, 1.1, "Whisper softly, as if sharing a secret."),
    "shout": Profile(1.1, 1.35, 0.8, "Shout loudly with force and urgency."),
    "sarcastic": Profile(0.95, 1.0, 1.1, "Speak in a dry, sarcastic, deadpan tone."),
    "serious": Profile(0.95, 1.0, 1.1, "Speak in a serious, grounded, no-nonsense tone."),
    "nervous": Profile(1.1, 0.95, 0.8, "Speak in a nervous, slightly shaky, hesitant tone."),
    "curious": Profile(1.0, 1.0, 1.0, "Speak with curiosity and interest, with a questioning lift."),
    "surprised": Profile(1.1, 1.05, 0.85, "Speak with surprise and astonishment."),
    "tired": Profile(0.82, 0.85, 1.4, "Speak in a tired, sleepy, low-energy tone."),
    "playful": Profile(1.08, 1.0, 0.85, "Speak in a playful, teasing, mischievous tone."),
    "confident": Profile(0.98, 1.05, 1.0, "Speak in a confident, assured, steady tone."),
    "empathetic": Profile(0.9, 0.92, 1.25, "Speak in a warm, empathetic, caring tone."),
    "laughing": Profile(1.12, 1.0, 0.8, "Speak while laughing, light and amused."),
}

ALIASES = {
    "whispering": "whisper",
    "whispers": "whisper",
    "shouting": "shout",
    "yell": "shout",
    "laugh": "laughing",
    "laughs": "laughing",
    "mad": "angry",
    "upset": "sad",
    "joyful": "happy",
    "sleepy": "tired",
    "worried": "nervous",
    "soft": "gentle",
}

_TAG = re.compile(r"\[\s*([A-Za-z]{3,12})\s*\]")


def normalize(name: str | None) -> str | None:
    """Return the canonical emotion name, or None if it is not one we know."""
    if not name:
        return None
    key = name.strip().lower()
    key = ALIASES.get(key, key)
    return key if key in EMOTIONS else None


def infer_emotion(instructions: str | None) -> str | None:
    """Find an emotion word in a free-text style instruction ('speak in a sad, quiet voice')."""
    if not instructions:
        return None
    best: tuple[int, str] | None = None
    lowered = instructions.lower()
    for word in [*EMOTIONS, *ALIASES]:
        match = re.search(rf"\b{re.escape(word)}\b", lowered)
        if match and (best is None or match.start() < best[0]):
            canonical = normalize(word)
            if canonical:
                best = (match.start(), canonical)
    return best[1] if best else None


def split_segments(text: str, default: str = "neutral") -> list[tuple[str, str]]:
    """Split text on emotion tags into (emotion, text) pieces. Unknown [tags] stay as text."""
    segments: list[tuple[str, str]] = []
    current = normalize(default) or "neutral"
    position = 0
    buffer = ""
    for match in _TAG.finditer(text):
        emotion = normalize(match.group(1))
        if emotion is None:
            continue
        buffer += text[position : match.start()]
        if buffer.strip():
            segments.append((current, buffer.strip()))
        buffer = ""
        current = emotion
        position = match.end()
    buffer += text[position:]
    if buffer.strip():
        segments.append((current, buffer.strip()))
    return segments
