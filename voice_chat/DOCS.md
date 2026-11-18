<!-- docs:header (generated, edit .github/docsgen) -->
# Voice Chat

![Version](https://img.shields.io/badge/dynamic/yaml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fjonathangibson98%2Fpi-custom-features%2Fmain%2Fvoice_chat%2Fconfig.yaml&query=%24.version&label=version&color=41BDF5&logo=homeassistant) ![Architectures](https://img.shields.io/badge/arch-aarch64%20%7C%20amd64-informational) ![Sidebar](https://img.shields.io/badge/sidebar-ingress-success) ![Prebuilt image](https://img.shields.io/badge/image-GHCR-2ea44f?logo=docker) ![Docker](https://img.shields.io/badge/also%20runs%20in-Docker-2496ED?logo=docker)

> Hands-free voice conversation with any Home Assistant conversation agent, answered out loud on the speakers you choose.

## At a glance

| | |
|---|---|
| Version | `2.5.2` |
| Slug | `voice_chat` |
| Architectures | `aarch64`, `amd64` |
| Opens from | the sidebar (**Voice Chat**, ingress) |
| Extra ports | `8443/tcp` |
| Folders it can reach | `share`, `ssl` (read only) |
| API access | Home Assistant API, Supervisor API |
| MQTT | not used |
| Takes commands via `hassio.addon_stdin` | yes |
| Install | prebuilt image from GHCR |

**You'll need:**

- A conversation agent, an STT and a TTS engine in Home Assistant
- HTTPS for the microphone (built-in self-signed port 8443, or Home Assistant's own HTTPS)

## Contents

- [Configuration](#configuration)
- [Using it](#using-it)
- [Household info](#household-info)
- [Which device listens, which device speaks](#which-device-listens-which-device-speaks)
- [Microphone access](#microphone-access)
- [Docker Compose (no add-on)](#docker-compose-no-add-on)
- [Troubleshooting](#troubleshooting)
- [Backups](#backups)
- [Configuration reference](#configuration-reference)
- [Help and feedback](#help-and-feedback)
<!-- /docs:header -->

Talk to any Home Assistant AI agent hands-free. Your voice is captured in the browser, the agent you pick answers, and the reply is spoken on the speakers you pick, on several at once, or in the browser itself.

```
mic (phone/browser) → speech-to-text → conversation agent → text-to-speech → media player(s) / this device
```

## Configuration

| Option | What to put |
|---|---|
| `conversation_agent` | Default AI, e.g. `conversation.home_assistant`, `conversation.ollama`, `conversation.google_generative_ai`, or a Personal AI agent. You can switch agents on the page. |
| `media_player` | Default speaker, e.g. `media_player.kitchen_speaker`. Empty = default to "This device". |
| `tts_entity` | Text-to-speech engine, e.g. `tts.piper` or `tts.home_assistant_cloud`. |
| `stt_entity` | Speech-to-text engine, e.g. `stt.faster_whisper`. Empty uses the browser's built-in recognition (Chrome/Edge/Safari, needs internet). |
| `language` | Optional language code (`en-US`, `de`, ...). Empty uses Home Assistant's language. |
| `hands_free` | On: keeps listening after every reply, like a phone call. Off: one question per tap. |
| `silence_ms` | How long you must pause before your sentence is sent (default 1200). |
| `volume` | 0 leaves speaker volume alone; 0.1–1 sets it before each reply (media players only). |
| `wake_word` | Optional, e.g. `hey jarvis`. Hands-free only reacts to sentences starting with it. Works best with an `stt_entity`. |
| `stop_words` | Comma-separated phrases that end the hands-free session. |
| `sensitivity` | `low` for noisy rooms, `high` for quiet voices. |
| `chimes` | Short beeps for listening, sent, wake word, error. |
| `idle_timeout_s` | End the hands-free session after this many quiet seconds (0 = never). |
| `browser_playback` | Offer "This device" as a speaker. |
| `save_history` / `history_limit` | Keep past chats (and how many). |
| `context_enabled` | On: the AI gets your household info (below). |
| `context_entity` | Sensor that holds it (blank by default), for example `sensor.combined_info`. |
| `context_attributes` | Which attributes to send, default `household_text,friends_text,notable_people,places`. |
| `context_skip_agents` | Agents that must not get it, default `conversation.home_assistant` (the built-in one matches fixed sentences only). |
| `context_max_chars` | Safety cap, default 40000. |
| `speaker_name` | Who is talking, e.g. `Alex`, so "I" and "my" make sense to the AI. |
| `password` | Turns on the direct HTTPS page (below). |
| `certfile` / `keyfile` | Certificate names in `/ssl`. A self-signed one is generated if missing. |

If an entity ID is wrong, the page shows a banner listing the entity IDs that do exist.

## Using it

Open **Voice Chat** in the sidebar. Choose the **AI** and where it should **Speak on** (tick several if you like), then tap the mic, or type in the message box. Talk, pause, and the reply plays. The mic is paused while a reply plays, so it never hears itself. Tap the orb to send early, cancel, or stop the speakers. On desktop, Space toggles the mic and Escape ends the session.

- **Wake word:** with `wake_word` set, say "hey jarvis, what's the weather" or just "hey jarvis" and wait for the chime. After each reply there's a 20-second window with no wake word needed.
- **History:** the History button lists saved chats. Open continues the same conversation with the agent, Export downloads Markdown, Delete removes it.
- **New chat** starts a fresh conversation.

## Household info

With `context_enabled` on, the first message of each conversation carries the text from `context_entity` (people, nicknames, relationships, places, music) in front of what you said. The AI uses it quietly and doesn't read it back. It is not shown in the chat or saved in History. If Home Assistant forgets the conversation after about five quiet minutes, it is sent again with your next message. Turn it off for one browser with the **AI knows my household info** switch.

### Live info (locations and anything else that changes)

Tap **Live info** on the page, search for an entity (for example `sensor.everybodys_locations`), tap it to add it, rename it if you like, and press **Save**. Each entry can also list the attributes to send (for example `alex,sam,chris`); leave it blank to send the state and every attribute. Add the word `state` to the list to include the state too. Up to 40 entities.

Their current values are read from Home Assistant at the moment you send a message. The AI gets them with the first message of a conversation and again whenever they have changed since it last saw them. Press **Preview what the AI sees** to check the text. The list lives in `/data/live_entities.json`.

It only works with AI agents that understand free text (Google Generative AI, Ollama, OpenAI, ...). The built-in Home Assistant agent is skipped.

## Which device listens, which device speaks

- **Listens:** the microphone of the phone, tablet or PC that has the page open. Google and Alexa speakers don't share their microphones with Home Assistant, so they can only speak. To listen from a room, open the page on a wall tablet there.
- **Speaks:** any media player entity `tts.speak` can play on, and/or "This device" (the browser). Phones allow browser audio only after a tap, which starting the mic counts as.

## Microphone access

Browsers only allow the microphone on secure pages. Try the sidebar panel first. If the mic is blocked (common in the Home Assistant mobile app):

1. Set a `password`, save, restart the add-on.
2. In the add-on's **Network** section, set a host port for `8443/tcp` and restart.
3. Open `https://<your-ha-address>:8443`, accept the certificate warning (or use a real certificate from `/ssl`), enter the password.

The direct page is off unless a password is set, because it could otherwise drive your AI agent without a login.

## Docker Compose (no add-on)

Everything above also works as a normal container, for Home Assistant Container/Core or when you'd rather not run an add-on.

```bash
cd voice_chat
cp .env.example .env      # set HA_URL, HA_TOKEN (long-lived token), entity IDs
docker compose up -d --build
# open https://<this-machine>:8443 and enter the password
```

The same options are environment variables with a `VC_` prefix (`VC_MEDIA_PLAYER`, `VC_WAKE_WORD`, ...). Standalone always asks for a password; if `VC_PASSWORD` is empty one is generated and printed in `docker compose logs voice-chat` and saved in `./data/password.txt`. Chat history, the generated certificate and the password live in `./data`.

## Troubleshooting

- **"Speech recognition failed"**: set `language` to a code your STT engine supports.
- **Reply shows but nothing plays on the speaker**: confirm `tts_entity` works with that player via Developer tools → Actions → `tts.speak`.
- **Nothing plays in the browser**: tap the orb or Send once first (phones block audio before a tap), and check the page isn't muted.
- **Cuts in on itself**: raise `silence_ms`, lower `sensitivity`, or move the speaker away from the phone.
- **Wake word never triggers**: set an `stt_entity` (better than browser recognition) and try a longer phrase such as "hey computer".
- Docker: `docker compose logs -f voice-chat` shows each exchange and config problems.

## Backups

Tap **Backups** at the bottom of the add-on page (the Backups button at the top for Voice Chat) to back up, download or restore. A backup is a `.zip` with your live info entities and chat history (the self-signed certificate is left out, a new one is made), plus everything in the Configuration tab.

| Option | Default | What |
|---|---|---|
| `backup_path` | `/share/addon_backups/voice_chat` | Where backups go, inside `/share`, `/media` or `/homeassistant`. A folder keeps several dated backups. A path ending in `.zip` keeps one file that is replaced each time |
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
| `conversation_agent` | `conversation.home_assistant` | text | **Conversation agent.** The AI entity to talk to, for example conversation.home_assistant or conversation.ollama. |
| `media_player` | *(empty)* | text, optional | **Default speaker.** The media player that speaks replies by default, for example media_player.kitchen_speaker. Leave empty to default to this device (browser). You can pick several speakers on the page. |
| `tts_entity` | *(empty)* | text | **Text-to-speech engine.** The TTS entity that turns replies into audio, for example tts.piper. |
| `stt_entity` | *(empty)* | text, optional | **Speech-to-text engine.** The STT entity that transcribes your voice, for example stt.faster_whisper. Leave empty to use the browser's built-in recognition. |
| `language` | *(empty)* | text, optional | **Language.** Optional language code such as en-US or de. Leave empty to use Home Assistant's language. |
| `hands_free` | `true` | true / false | **Hands-free.** Keep listening after every reply. Turn off for one question per tap. |
| `silence_ms` | `1200` | whole number (400–5000) | **Pause before sending (ms).** How long you must stay quiet before your sentence is sent. Default 1200. |
| `volume` | `0` | number (0–1) | **Speaker volume.** 0 leaves the speaker's volume alone. 0.1 to 1 sets it before each reply. |
| `password` | *(empty)* | secret, optional | **Password for direct HTTPS page.** Setting a password turns on the direct HTTPS page on port 8443. Leave empty to keep it off. |
| `certfile` | `fullchain.pem` | text | **Certificate file.** Certificate name inside /ssl. A self-signed one is generated if it doesn't exist. |
| `keyfile` | `privkey.pem` | text | **Private key file.** Private key name inside /ssl. |
| `wake_word` | *(empty)* | text, optional | **Wake word.** Optional. When set, hands-free mode only reacts to sentences that start with this phrase, for example "hey jarvis". After a reply you can keep talking for 20 seconds without repeating it. Needs an stt_entity for reliable results. |
| `stop_words` | `stop listening,goodbye,never mind,cancel` | text, optional | **Stop phrases.** Comma-separated phrases that end the hands-free session when you say them on their own. |
| `sensitivity` | `normal` | one of: `low`, `normal`, `high` | **Microphone sensitivity.** High picks up quiet voices but also noise. Low suits noisy rooms. |
| `chimes` | `true` | true / false | **Sound cues.** Short beeps when listening starts, a message is sent, or something fails. |
| `idle_timeout_s` | `120` | whole number (0–3600) | **Stop listening after (seconds).** Ends the hands-free session when nobody has spoken for this long. 0 keeps it listening forever. |
| `browser_playback` | `true` | true / false | **Allow playing replies in the browser.** Adds "This device" to the speaker list so replies play on the phone or PC that has the page open, no media player needed. |
| `save_history` | `true` | true / false | **Save chat history.** Keeps past chats so you can reopen, export or delete them from the History button. |
| `history_limit` | `100` | whole number (10–1000) | **Chats to keep.** Oldest chats are deleted beyond this number. |
| `context_enabled` | `true` | true / false, optional | **Give the AI my household info.** Sends the background from your combined info sensor to the AI with the first message of each conversation, so it knows who everyone is. Not shown in chat or saved in history. |
| `context_entity` | *(empty)* | text, optional | **Household info sensor.** The sensor that holds your household info, for example sensor.combined_info. |
| `context_attributes` | `household_text,friends_text,notable_people,places` | text, optional | **Sensor attributes to send.** Comma-separated attributes of that sensor. Default household_text,friends_text,notable_people,places covers everyone. Text and nested data are both fine. |
| `context_skip_agents` | `conversation.home_assistant` | text, optional | **Agents that should not get it.** Comma-separated agents that only match fixed sentences and would break with extra text. Default conversation.home_assistant. |
| `context_max_chars` | `40000` | whole number (0–200000), optional | **Maximum characters.** Safety cap on how much household info is sent. 0 means no cap. |
| `speaker_name` | *(empty)* | text, optional | **Who is talking.** Your name, for example Alex, so the AI knows who "I", "me" and "my" mean. Leave empty if several people use the page. |
| `backup_path` | `/share/addon_backups/voice_chat` | text | **Backup folder.** Where backups are saved, inside /share, /media or /homeassistant. A folder keeps several dated backups. A path ending in .zip keeps one file that is replaced each time. Open Backups in the add-on page to back up, download or restore. |
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
<!-- /docs:footer -->
