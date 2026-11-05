# Voice Chat

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
| `password` | Turns on the direct HTTPS page (below). |
| `certfile` / `keyfile` | Certificate names in `/ssl`. A self-signed one is generated if missing. |

If an entity ID is wrong, the page shows a banner listing the entity IDs that do exist.

## Using it

Open **Voice Chat** in the sidebar. Choose the **AI** and where it should **Speak on** (tick several if you like), then tap the mic, or type in the message box. Talk, pause, and the reply plays. The mic is paused while a reply plays, so it never hears itself. Tap the orb to send early, cancel, or stop the speakers. On desktop, Space toggles the mic and Escape ends the session.

- **Wake word:** with `wake_word` set, say "hey jarvis, what's the weather" or just "hey jarvis" and wait for the chime. After each reply there's a 20-second window with no wake word needed.
- **History:** the History button lists saved chats. Open continues the same conversation with the agent, Export downloads Markdown, Delete removes it.
- **New chat** starts a fresh conversation.

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
