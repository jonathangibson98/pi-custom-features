# Personal AI Speech (Home Assistant add-on)

Natural text-to-speech with emotion tags, plus local speech-to-text, as an OpenAI-compatible server for the **Personal AI** integration.

- **TTS:** Kokoro-82M running on the Pi (no cloud), 54 voices, voice blending, `[happy]` `[whisper]` `[sad]`... tags.
- **Or proxy** to OpenAI `gpt-4o-mini-tts` / a GPU box for real emotion acting.
- **STT:** faster-whisper on the Pi's CPU.
- A test page in the sidebar: type text, click emotion chips, listen.

Needs a 64-bit Pi (aarch64) with 4 GB RAM or more recommended.
