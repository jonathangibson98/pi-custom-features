# Personal AI Speech: setup

## Install
1. Copy the `personal_ai_speech` folder into the `addons` share (Samba: `\\homeassistant\addons`).
2. Settings, Add-ons, Add-on Store, three dots, **Check for updates**. Open **Personal AI Speech** under *Local add-ons*, click **Install**, then **Start**.
3. First start downloads about 120 MB of voice model. Watch the **Log** tab until you see `Kokoro ready`. Whisper downloads on first use (or at start).
4. Click **Open Web UI** and press **Speak** to test.

## Connect Home Assistant
1. Install the **Personal AI** integration (v1.2.0+), then Settings, Devices & Services, Add Integration, Personal AI.
2. Server URL: `http://local-personal-ai-speech:8880/v1` (check the add-on's Info tab for the exact hostname; `http://<pi-ip>:8880/v1` also works). API key: your add-on key if you set one.
3. On that entry click **Add AI voice (TTS)** and **Add AI transcription (STT)**.
4. Settings, Voice assistants: choose them as the text-to-speech and speech-to-text engines.

## Emotion
Put tags in the text: `[excited] We did it! [whisper] Quiet. [sad] Bye.` Or turn on **Speak with emotion** on a Personal AI conversation agent so the AI writes them.
- **kokoro engine:** emotion is approximated with speed, volume and pauses (Kokoro has no true emotion control).
- **proxy engine:** each tag becomes an acting instruction for the upstream model. OpenAI `gpt-4o-mini-tts` is the one that really acts. Set `upstream_url` `https://api.openai.com/v1`, your key, model `gpt-4o-mini-tts`.

## Tips
- Slow replies on the Pi? Keep `kokoro_model` on `int8`, keep replies short.
- Long-running Whisper? Use `tiny.en`.
- Languages: Kokoro voices starting `a`/`b` are English, `e` Spanish, `f` French, `h` Hindi, `i` Italian, `p` Portuguese. Japanese/Chinese need extra packages and are not included.
- API: `POST /v1/audio/speech`, `POST /v1/audio/transcriptions`, `GET /v1/audio/voices`, `GET /health`.
