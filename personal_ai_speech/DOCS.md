<!-- docs:header (generated, edit .github/docsgen) -->
# Personal AI Speech

![Version](https://img.shields.io/badge/dynamic/yaml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fjonathangibson98%2Fpi-custom-features%2Fmain%2Fpersonal_ai_speech%2Fconfig.yaml&query=%24.version&label=version&color=41BDF5&logo=homeassistant) ![Architectures](https://img.shields.io/badge/arch-aarch64%20%7C%20amd64-informational) ![Sidebar](https://img.shields.io/badge/sidebar-ingress-success) ![Prebuilt image](https://img.shields.io/badge/image-GHCR-2ea44f?logo=docker)

> Natural text-to-speech with emotion tags and local speech-to-text, as an OpenAI-compatible server for the Personal AI integration.

## At a glance

| | |
|---|---|
| Version | `1.3.3` |
| Slug | `personal_ai_speech` |
| Architectures | `aarch64`, `amd64` |
| Opens from | the sidebar (**Personal AI Speech**, ingress) |
| Extra ports | `8880/tcp` |
| Folders it can reach | `share` |
| API access | Supervisor API |
| MQTT | not used |
| Takes commands via `hassio.addon_stdin` | yes |
| Install | prebuilt image from GHCR |

**You'll need:**

- A 64-bit system, 4 GB RAM or more recommended
- About 120 MB download on first start
- The Personal AI integration (to use it from Home Assistant)

## Contents

- [Install](#install)
- [Connect Home Assistant](#connect-home-assistant)
- [Emotion](#emotion)
- [Tips](#tips)
- [Emotion tags](#emotion-tags)
- [API](#api)
- [Backups](#backups)
- [Configuration reference](#configuration-reference)
- [Help and feedback](#help-and-feedback)
<!-- /docs:header -->

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
- The voice list for your engine is on the add-on page and at `GET /v1/audio/voices`.

## Emotion tags

`angry`, `calm`, `cheerful`, `confident`, `curious`, `empathetic`, `excited`, `gentle`, `happy`, `laughing`, `nervous`, `neutral`, `playful`, `sad`, `sarcastic`, `serious`, `shout`, `surprised`, `tired`, `whisper`.

Common spellings work too: `whispering`, `shouting`/`yell`, `laugh`/`laughs`, `mad`, `upset`, `joyful`, `sleepy`, `worried`, `soft`. A tag applies until the next tag.

## API

The server speaks the OpenAI audio API, so most apps that can use OpenAI's speech endpoints can point at it. Base URL: `http://<home-assistant-ip>:8880/v1`. If you set `api_key`, send it as `Authorization: Bearer <key>`.

| Method | Path | What it does |
|---|---|---|
| `POST` | `/v1/audio/speech` | Text to speech. JSON body: `input` (text, tags allowed), `voice`, `speed`, `response_format` (`mp3`, `wav`, `flac`, `opus` or `pcm`; default `mp3`), optional `instructions` |
| `POST` | `/v1/audio/transcriptions` | Speech to text. Form upload: `file`, optional `language`, `response_format` (`json`, `text` or `verbose_json`) |
| `GET` | `/v1/audio/voices` | The voices for the current engine and the default one |
| `GET` | `/v1/models` | The models it answers to |
| `GET` | `/health` | Whether the engines are loaded (no key needed) |

```bash
# speak
curl http://<home-assistant-ip>:8880/v1/audio/speech \
  -H "Content-Type: application/json" -H "Authorization: Bearer <key>" \
  -d '{"input": "[happy] Dinner is ready! [whisper] Keep it a secret.", "voice": "af_heart"}' \
  -o reply.mp3

# transcribe
curl http://<home-assistant-ip>:8880/v1/audio/transcriptions \
  -H "Authorization: Bearer <key>" -F file=@question.wav -F response_format=text
```

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

<!-- docs:config (generated from config.yaml) -->
## Configuration reference

Every option on the add-on's **Configuration** tab, with its default. Change them there, then restart the add-on.

| Option | Default | Type | What it does |
|---|---|---|---|
| `api_key` | *(empty)* | secret, optional | **API key.** Optional password for the speech API. Leave blank on a trusted home network. |
| `tts_engine` | `kokoro` | one of: `kokoro`, `proxy` | **Voice engine.** kokoro runs on this Pi. proxy forwards to OpenAI or another server (real emotion acting). |
| `kokoro_model` | `int8` | one of: `int8`, `fp16`, `fp32` | **Kokoro model size.** int8 is fastest and smallest (best for a Pi). fp16/fp32 sound slightly better but are slower. |
| `default_voice` | `af_heart` | text | **Default voice (Kokoro).** e.g. af_heart, af_bella, am_adam, bf_emma. Blend with + (af_heart+af_bella). |
| `default_speed` | `1.0` | number (0.5–2.0) | **Default speed.** 1.0 is normal. |
| `upstream_url` | *(empty)* | text, optional | **Upstream URL (proxy only).** e.g. https://api.openai.com/v1 or http://192.168.1.50:8000/v1 |
| `upstream_api_key` | *(empty)* | secret, optional | **Upstream API key (proxy only).** Key for the upstream server. |
| `upstream_model` | `gpt-4o-mini-tts` | text, optional | **Upstream model (proxy only).** e.g. gpt-4o-mini-tts |
| `upstream_voice` | `coral` | text, optional | **Upstream default voice (proxy only).** e.g. coral |
| `upstream_send_instructions` | `true` | true / false | **Send emotion instructions upstream.** Turn off for models that reject instructions, like tts-1. |
| `stt_enabled` | `true` | true / false | **Enable speech-to-text.** Local Whisper transcription. |
| `stt_model` | `base.en` | one of: `tiny.en`, `base.en`, `small.en`, `tiny`, `base`, `small` | **Whisper model.** base.en is a good Pi balance. tiny.en is faster, small.en is more accurate but slow. |
| `stt_language` | *(empty)* | text, optional | **Whisper language.** Optional two-letter code. Leave blank to follow the voice assistant. |
| `stt_preload` | `true` | true / false | **Load Whisper at start.** Uses RAM all the time but the first command isn't slow. |
| `log_level` | `info` | one of: `debug`, `info`, `warning`, `error` | **Log level.** How chatty the add-on log is. Use debug when troubleshooting. |
| `backup_path` | `/share/addon_backups/personal_ai_speech` | text | **Backup folder.** Where backups are saved, inside /share, /media or /homeassistant. A folder keeps several dated backups. A path ending in .zip keeps one file that is replaced each time. Open Backups in the add-on page to back up, download or restore. |
| `backup_every` | `daily` | one of: `off`, `daily`, `weekly` | **Automatic backups.** How often a backup is made by itself (off, daily or weekly). |
| `backup_keep` | `10` | whole number (1–100) | **Backups to keep.** The newest this many backups are kept in the folder, older ones are deleted. |
| `wallpaper` | *(empty)* | text, optional | **Wallpaper.** Background image for this add-on's web UI. Leave empty to use your Home Assistant theme's wallpaper, "none" for no wallpaper, or an image: put it in /config/www and enter its file name (pic.jpg) or /local/pic.jpg, or a full https:// link. |
<!-- /docs:config -->

<!-- docs:footer (generated) -->
## Help and feedback

- **Logs:** the add-on's **Log** tab shows what it's doing and most errors in plain words.
- **Changes:** see the [changelog](CHANGELOG.md) (also on the add-on's **Changelog** tab).
- **Problems or ideas:** [open an issue](https://github.com/jonathangibson98/pi-custom-features/issues) and include the add-on version and the log.
- **Pages follow your theme:** every page in this repository picks up your Home Assistant theme and wallpaper automatically.
- **On your phone:** the pages are built for the Home Assistant iPhone and Android apps. Turn on **Show in sidebar** to reach them from the app's menu.
<!-- /docs:footer -->
