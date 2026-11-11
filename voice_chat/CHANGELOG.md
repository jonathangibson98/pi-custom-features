# Changelog

## 2.2.0

- **Live info.** New **Live info** button on the page. Search for any Home Assistant entity (for example `sensor.everybodys_locations`), give it a name, optionally pick which attributes to send, and save. The AI reads their current values fresh from Home Assistant, so it knows where everyone is right now.
- Live values go along with your message only when they changed since the AI last saw them, and always with the first message of a conversation. Nothing is repeated every turn, and none of it shows up in the chat or the saved history.
- **Preview** button shows exactly what the AI is being sent.
- The list is saved in `/data/live_entities.json` and starts with `sensor.everybodys_locations`.
- The page switch is now "Give the AI my household & live info" and turns off both.

## 2.1.0

- **The AI now knows your household.** Voice Chat reads your combined info sensor (`sensor.combined_info`) and gives it to the AI with the first message of every conversation, so when you say "Von", "Guapo" or "MJ's sister" it knows who you mean. It is sent again automatically if Home Assistant forgets the conversation after a few quiet minutes. The background never shows up in the chat or the saved history.
- New options: `context_enabled`, `context_entity`, `context_attributes`, `context_skip_agents`, `context_max_chars`, `speaker_name`.
- "AI knows my household info" switch on the page (remembered per browser). Hidden for the built-in Home Assistant agent, which only matches fixed sentences.
- A banner appears if `context_entity` doesn't exist.

## 2.0.0

- **Standalone Docker version.** `docker-compose.yml` + `Dockerfile.standalone` run Voice Chat anywhere, against any Home Assistant, using a long-lived access token. Settings come from `VC_*` environment variables. A password is always required (one is generated if you don't set it).
- **"This device" playback.** Replies can play in the phone or PC browser itself, no media player needed.
- **Several speakers at once.** Tick as many media players as you like (plus this device); they all speak together.
- **Pick the AI on the page.** A menu lists every conversation agent in Home Assistant; your choice is remembered.
- **Wake word.** Optional phrase (for example "hey jarvis") so hands-free mode ignores room chatter. After a reply you can keep talking for 20 seconds without repeating it.
- **Stop phrases.** Say "stop listening", "goodbye", "never mind" or "cancel" to end the hands-free session.
- **Chat history.** Past chats are saved; reopen, export as Markdown, or delete them from the History button. Opening one continues the same conversation.
- **Sound cues** for listening, sent, wake word, and errors.
- **Quiet-spell timeout** ends a forgotten hands-free session by itself.
- **Microphone sensitivity** low / normal / high.
- Space bar toggles the mic on desktop, Escape ends the session.
- `media_player` is now optional when browser playback is on.

## 1.2.0

- Type to the AI as well as talk: a message box under the chat. Replies to typed messages are spoken on the chosen speaker by default; untick "Speak replies to typed messages" to read them silently. Typing and talking share the same conversation.

## 1.1.0

- Speaker picker on the page: switch between any of your media players (Google, Sonos, Alexa and others) without touching the add-on configuration. Your choice is remembered per browser; the `media_player` option is the default.

## 1.0.0

- First release.
- Hands-free voice conversation with any Home Assistant conversation agent.
- Replies are spoken on the media player chosen in the add-on configuration.
- Speech-to-text through a Home Assistant STT entity, or the browser's built-in recognition when none is set.
- Automatic silence detection, with push-to-talk style single turns when `hands_free` is off.
- Tap the orb to send early, cancel, or stop the speaker; New chat resets the conversation.
- Optional direct HTTPS page (port 8443, password protected, self-signed certificate generated if none is in `/ssl`).
- Config check: wrong or missing entity IDs are listed in the page and the add-on log, with the IDs that do exist.
