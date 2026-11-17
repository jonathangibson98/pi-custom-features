# Personal AI Speech: setup

## Install
1. Add this repository to the Add-on Store (see the repository README), open **Personal AI Speech**, click **Install**, then **Start**. (Alternative: copy the `personal_ai_speech` folder into the `addons` share, check for updates, and install it from *Local add-ons*.)
2. First start downloads about 120 MB of voice model. Watch the **Log** tab until you see `Kokoro ready`. Whisper downloads on first use (or at start).
3. Click **Open Web UI** and press **Speak** to test.

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

## Backups

Tap **Backups** at the bottom of the add-on page to back up, download or restore. A backup is a `.zip` with its settings (the voice and speech models are left out, they download again by themselves), plus everything in the Configuration tab.

| Option | Default | What |
|---|---|---|
| `backup_path` | `/share/addon_backups/personal_ai_speech` | Where backups go, inside `/share`, `/media` or `/homeassistant`. A folder keeps several dated backups. A path ending in `.zip` keeps one file that is replaced each time |
| `backup_every` | `daily` | `off`, `daily` or `weekly` automatic backups |
| `backup_keep` | `10` | How many backups to keep in the folder. Older ones are deleted |

- **Back up now** makes one straight away. **Download** saves one to your phone or computer.
- **Restore** (tap twice) first saves a safety copy (`..._pre-restore_...zip`, the newest 3 are kept), puts the Configuration tab settings back, and restarts the add-on. The data is put back as it starts, before it reads anything.
- **Restore from a file** takes a backup `.zip` you downloaded, for example to move to another Home Assistant.
- A backup from a different add-on is refused. The page only works from the Home Assistant sidebar, never on the add-on's own ports, because backups include its settings.
- Backups also hold any passwords or API keys from the Configuration tab, so treat the backup folder like your secrets.
