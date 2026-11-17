# Party Lights

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

- Each light gets a different color from the art, in the order you list them (or all the same color).
- **Boost colors** makes dull art look good on bulbs. **Brightness** 0 keeps the lights' current brightness.
- **Only sync when this entity is in this state**: for a mode helper (for example `select.sync_lights_mode` = `Music`). When set, it syncs whenever the helper says so, party mode or not. **Always sync** syncs whenever music plays.

## Album art sensor

`sensor.music_art_brightness` by default: state = how bright the art is (0–255), attributes `color` (main color), `palette`, `text_color` (black or white, whichever reads better over the art), `title`, `player`. Needs MQTT.

## Pick the mode without opening the page

**A dropdown helper (easiest).** On **Setup**, under **Pick the mode without this page**, tap **Make one for me**. It creates `input_select.party_lights_mode` with every mode (Off, Music sync, Disco…). Put it on a dashboard, change it in an automation, or ask your voice assistant. Picking a mode starts the party with it; **Off** ends the party. When you change the mode on this page, the helper follows.

You can link a dropdown you already have instead (an `input_select` or `select`). Its options need to match the mode names. "On" or "Party" also works and starts the last mode.

**From any automation or script, no MQTT needed**:

```yaml
action: hassio.addon_stdin
data:
  addon: <this add-on's slug, shown on Setup>
  input: disco
```

`input` can be `off`, any mode (`disco`, `rainbow wave`, `Lava lamp`), `party on` / `party off`, or `game trivia on` / `game trivia off` / `game roulette`.

## Home Assistant entities (MQTT)

`switch.party_mode`, `select.party_effect`, `select.party_colors`, `number.party_speed`, `number.party_brightness`, `number.party_bpm`, `sensor.party_status`, a switch for every game (`switch.party_power_hour`, `switch.party_shot_caller`, `switch.party_countdown`, `switch.party_hype_mc`, `switch.party_freeze`, `switch.party_red_green`, `switch.party_never`, `switch.party_truth_dare`, `switch.party_trivia`, `switch.party_name_tune`, `switch.party_rules`, `switch.party_welcome`, `switch.party_last_call`) and a button for every quick hit (`button.party_hot_potato`, `button.party_roulette`, `button.party_cheers`, `button.party_dance_battle`, `button.party_flash`, `button.party_drop`, `button.party_birthday`, `button.party_blackout`). `select.party_effect` includes **Off**, so it also picks the mode or ends the party. Put them on a dashboard or use them in automations (for example: start the party when a playlist starts).

## Moving from AppDaemon

Turn off the `media_lights_sync` and `art_color` apps (remove them from `apps.yaml`), restart AppDaemon, restart Home Assistant once so the old `sensor.music_art_brightness` is gone, then start this add-on so its sensor takes the same entity ID.
