<!-- docs:header (generated, edit .github/docsgen) -->
# Party Lights

![Version](https://img.shields.io/badge/dynamic/yaml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fjonathangibson98%2Fpi-custom-features%2Fmain%2Fparty_lights%2Fconfig.yaml&query=%24.version&label=version&color=41BDF5&logo=homeassistant) ![Architectures](https://img.shields.io/badge/arch-aarch64%20%7C%20amd64-informational) ![Sidebar](https://img.shields.io/badge/sidebar-ingress-success) ![Prebuilt image](https://img.shields.io/badge/image-GHCR-2ea44f?logo=docker) ![MQTT](https://img.shields.io/badge/MQTT-optional-660066?logo=mqtt) ![AI Task](https://img.shields.io/badge/AI-ai__task-8A2BE2?logo=googlegemini)

> Music-synced lights, 25 light modes, color themes and 20+ party games, run from a phone-friendly page, a dashboard dropdown, an automation or MQTT.

## At a glance

| | |
|---|---|
| Version | `1.3.0` |
| Slug | `party_lights` |
| Architectures | `aarch64`, `amd64` |
| Opens from | the sidebar (**Party Lights**, ingress) |
| Extra ports | none |
| Folders it can reach | only its own storage |
| API access | Home Assistant API, Supervisor API |
| MQTT | optional (used when available) |
| Takes commands via `hassio.addon_stdin` | yes |
| Install | prebuilt image from GHCR |

**You'll need:**

- Color lights
- A TTS engine and speakers (optional, for announcements)
- MQTT (optional, for the Home Assistant entities)
- An `ai_task` entity (optional)

## Contents

- [Setup](#setup)
- [Lights tab](#lights-tab)
- [Games & extras](#games--extras)
- [Music sync](#music-sync)
- [Album art sensor](#album-art-sensor)
- [Pick the mode without opening the page](#pick-the-mode-without-opening-the-page)
- [Home Assistant entities (MQTT)](#home-assistant-entities-mqtt)
- [Moving from AppDaemon](#moving-from-appdaemon)
- [Configuration reference](#configuration-reference)
- [Help and feedback](#help-and-feedback)
<!-- /docs:header -->

Music-synced lights, light shows and party games, set up on the add-on page. No AppDaemon needed: this replaces the `media_lights_sync` and `art_color` apps.

## Setup

The page works on a phone: the tabs (Lights, Games, Music, Setup) sit at the bottom of the screen, and the speed and brightness sliders stay in view while you scroll the light modes.

1. Install and start the add-on, turn on **Show in sidebar**, open **Party Lights**.
2. **Setup** tab: pick your party lights (color bulbs or light groups). Pick a TTS voice and speakers if you want announcements, and **Test the speakers**.
3. **Music sync** tab: pick the music players to follow and the lights to color.
4. Hit **Start the party**. The lights are saved first and put back when you end it (turn that off on Setup).

## Lights tab

- **Light mode**: tap one and the party starts. **Off** ends the party.
  - Off, Music sync, Static colors, Color loop, Rainbow wave, Disco, Chase, Pulse to the beat (set the BPM), Breathe, Strobe, Sparkle, Fire, Police, Lightning storm.
  - New in 1.1: **Twinkle** (random lights sparkle on and off), **Comet** (a bright head with a fading tail runs down the lights), **Ping pong** (one light bounces end to end), **Heartbeat** (double thump, follows the BPM), **Aurora** (slow greens, blues and purples), **Ocean waves** (blue swells), **Alternate** (every other light swaps colors, candy cane style), **Fireworks** (random bursts that fade out), **Spotlight** (one bright white light moves around, the rest stay dim), **Glitch** (random flickers), **Lava lamp** (slow, blobby color drift) and **Shuffle shows** (a different show every few minutes; set how often with the slider).
  - **Speed** and **Brightness** sliders.
- **Colors**: color themes for the shows, including the current album art, team colors (from a sensor with `team_colors`, like Team Tracker), your own colors, or **✨ AI colors**: describe a vibe and your Home Assistant AI picks the colors, effect and speed.
- New color themes: Aurora, Candy cane and Tropical.

Strobe and fast effects are limited by **Fastest change** on Setup (default 0.5 s) so slow bulbs and Zigbee networks keep up. Strobe can bother people with light sensitivity; use it with care.

## Games & extras

- **Power hour**: every minute the lights flash and it calls "Drink!" (or your words), optionally skipping to the next song.
- **Shot caller**: every few minutes it picks someone who's home (from `person` entities) and calls them out. Write your own lines with `{name}`. Leave people out under **Leave out**.
- **Countdown**: to a time (midnight for New Year's): "one minute!", a 10-second light countdown, a message and a 45-second celebration.
- **AI hype MC**: your AI writes a short hype line about the song and the crowd every few minutes.
- **Freeze dance**: the lights go ice blue and it shouts "Freeze!" at random times. Anyone who moves is out. It can pause a music player during the freeze.
- **Red light, green light**: all the lights go green ("Green light!") or red ("Red light!") at random.
- **Never have I ever** and **Truth or dare**: a new prompt every few minutes. Truth or dare picks someone who's home. Your AI writes new ones, or it uses the built-in list (keep it friendly; the built-in prompts are PG-13).
- **Party trivia**: asks a question, waits, then reads the answer. Pick a topic for AI questions, or use the built-in ones.
- **Name that tune**: says "Name that tune!", waits, then reveals the song and artist that's playing.
- **Rule maker**: adds a new house rule every so often (Kings Cup style).
- **Welcome arrivals**: flashes the lights and greets people by name when their `person` entity comes home.
- **Last call**: warns a set time before closing, dims the lights warm, then says goodnight and ends the party.
- **Quick hits** (one round each): Hot potato (lights tick faster until they blow), Light roulette (spins across the lights and lands on one), Cheers! (gold flash and a toast), Dance battle (two people home face off, each gets their own color), Flash, Drop the beat, Birthday blast and Blackout.

Every game has its own **⚙️ Settings**. Filter the list with **Games that run**, **Quick hits** or **Running now**. Ending the party stops every game.

Announcements use `tts.speak` with the voice and speakers from Setup. The AI uses `ai_task_entity`, or your default AI from Personalized Info, then the first AI Task.

## Music sync

The **Music** tab shows a checklist of what music sync needs (a player, music playing, lights, and your helper if you set one) with ✓ or ✕, so you can see straight away why it isn't syncing, and when it last synced.

- **Music players to follow**: empty follows the album-art sensor's player, or whatever is playing.

- Each light gets a different color from the art, in the order you list them (or all the same color).
- **Boost colors** makes dull art look good on bulbs. **Brightness** 0 keeps the lights' current brightness.
- **Only sync when this entity is in this state**: for a mode helper (for example `select.sync_lights_mode` = `Music`). When set, it syncs whenever the helper says so, party mode or not. **Always sync** syncs whenever music plays.

## Album art sensor

`sensor.music_art_brightness` by default: state = how bright the art is (0–255), attributes `color` (main color), `palette`, `text_color` (black or white, whichever reads better over the art), `title`, `player`. Needs MQTT.

## Pick the mode without opening the page

**A dropdown helper (easiest).** On **Setup**, under **Pick the mode without this page**, tap **Make one for me**. It creates `input_select.party_lights_mode` with every mode (Off, Music sync, Disco…). Put it on a dashboard, change it in an automation, or ask your voice assistant. Picking a mode starts the party with it; **Off** ends the party. When you change the mode on this page, the helper follows.

You can link a dropdown you already have instead (an `input_select` or `select`). Its options need to match the mode names. "On" or "Party" also works and starts the last mode.

**One dropdown for sports and party lights.** Every mode list has a **Sports** option next to Off and Music sync (the page, the helper, the `Light mode` select and `hassio.addon_stdin` with `input: sports`). Picking **Sports** stops the party, leaves the lights alone and lets Team Tracker Lite's **Score lights** take over: they show your team's colors and flash when someone scores. Picking any other mode (or **Off**) hands the lights back to the party, and **Off** puts the lights back the way they were before.

To set it up:
1. Make the helper above (or link your own `input_select`). Every mode, Sports included, is added to it for you. Nothing already in it is removed. A plain `select` (like the MQTT one) can't be changed from here, so it needs a **Sports** option of its own.
2. In **Team Tracker Lite → Score lights**, set *Only when this entity is in this state* to that same dropdown (for example `input_select.party_lights_mode`) and the state to `Sports`.
3. Turn off any second mode dropdown you had for sports.

Party Lights and Score lights never paint the lights at the same time: Score lights wait until the dropdown says Sports.

**From any automation or script, no MQTT needed**:

```yaml
action: hassio.addon_stdin
data:
  addon: <this add-on's slug, shown on Setup>
  input: disco
```

`input` can be `off`, any mode (`disco`, `rainbow wave`, `Lava lamp`), `party on` / `party off`, or `game trivia on` / `game trivia off` / `game roulette`.

## Home Assistant entities (MQTT)

With the Mosquitto broker add-on, you get one **Party Lights** device with just these:

| Entity | What it does |
|---|---|
| `switch.party_mode` | Party on or off |
| `select.party_effect` | Light mode. **Off** ends the party |
| `select.party_theme` | Colors |
| `number.party_brightness` / `number.party_speed` | Brightness and speed |
| `select.party_game` | Start a game. **None** stops every game |
| `select.party_quick_hit` | Run a quick hit (it goes back to "Pick one…" after) |
| `sensor.party_status` | What's happening: mode, colors, running games, music sync status |
| `sensor.music_art_brightness` | The album-art sensor (if it's on) |

Before 1.2 there was a switch or button for every game; they're removed automatically.

## Moving from AppDaemon

Turn off the `media_lights_sync` and `art_color` apps (remove them from `apps.yaml`), restart AppDaemon, restart Home Assistant once so the old `sensor.music_art_brightness` is gone, then start this add-on so its sensor takes the same entity ID.

<!-- docs:config (generated from config.yaml) -->
## Configuration reference

Every option on the add-on's **Configuration** tab, with its default. Change them there, then restart the add-on.

| Option | Default | Type | What it does |
|---|---|---|---|
| `ai_task_entity` | *(empty)* | text, optional | **AI Task entity (optional).** The Home Assistant AI Task behind the AI hype MC and AI colors. Empty uses your default AI (picked in Personalized Info), then the first one. |
| `mqtt_host` | *(empty)* | text, optional | **MQTT host (optional).** Leave empty to use the Mosquitto add-on automatically. MQTT makes the Home Assistant controls (switch.party_mode, select.party_effect, ...). |
| `mqtt_port` | `1883` | port, optional | **MQTT port (optional).** Usually 1883. |
| `mqtt_username` | *(empty)* | text, optional | **MQTT username (optional).** Only for your own broker. |
| `mqtt_password` | *(empty)* | secret, optional | **MQTT password (optional).** Only for your own broker. |
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
