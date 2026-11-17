# Party Lights

Music-synced lights, light shows and party games, set up on the add-on page. No AppDaemon needed: this replaces the `media_lights_sync` and `art_color` apps.

## Setup

1. Install and start the add-on, turn on **Show in sidebar**, open **Party Lights**.
2. **Setup** tab: pick your party lights (color bulbs or light groups). Pick a TTS voice and speakers if you want announcements, and **Test the speakers**.
3. **Music sync** tab: pick the music players to follow and the lights to color.
4. Hit **Start the party**. The lights are saved first and put back when you end it (turn that off on Setup).

## Party tab

- **Light show**: Off, Music sync, Static colors, Color loop, Rainbow wave, Disco, Chase, Pulse to the beat (set the BPM), Breathe, Strobe, Sparkle, Fire, Police, Lightning storm. **Speed** and **Brightness** sliders.
- **Colors**: color themes for the shows, including the current album art, team colors (from a sensor with `team_colors`, like Team Tracker), your own colors, or **✨ AI colors**: describe a vibe and your Home Assistant AI picks the colors, effect and speed.
- **Quick hits**: Flash, Drop the beat (build-up, a second of darkness, then 20 seconds of chaos), Birthday blast (with the name you type) and Blackout.

Strobe and fast effects are limited by **Fastest change** on Setup (default 0.5 s) so slow bulbs and Zigbee networks keep up. Strobe can bother people with light sensitivity; use it with care.

## Games & extras

- **Power hour**: every minute the lights flash and it calls "Drink!" (or your words), optionally skipping to the next song.
- **Shot caller**: every few minutes it picks someone who's home (from `person` entities) and calls them out. Write your own lines with `{name}`. Leave people out under **Leave out**.
- **Countdown**: to a time (midnight for New Year's): "one minute!", a 10-second light countdown, a message and a 45-second celebration.
- **AI hype MC**: your AI writes a short hype line about the song and the crowd every few minutes.

Announcements use `tts.speak` with the voice and speakers from Setup. The AI uses `ai_task_entity`, or your default AI from Personalized Info, then the first AI Task.

## Music sync

- Each light gets a different color from the art, in the order you list them (or all the same color).
- **Boost colors** makes dull art look good on bulbs. **Brightness** 0 keeps the lights' current brightness.
- **Only sync when this entity is in this state**: for a mode helper (for example `select.sync_lights_mode` = `Music`). When set, it syncs whenever the helper says so, party mode or not. **Always sync** syncs whenever music plays.

## Album art sensor

`sensor.music_art_brightness` by default: state = how bright the art is (0–255), attributes `color` (main color), `palette`, `text_color` (black or white, whichever reads better over the art), `title`, `player`. Needs MQTT.

## Home Assistant entities (MQTT)

`switch.party_mode`, `select.party_effect`, `select.party_colors`, `number.party_speed`, `number.party_brightness`, `number.party_bpm`, `switch.party_power_hour`, `switch.party_shot_caller`, `switch.party_countdown`, `switch.party_hype_mc`, `button.party_flash`, `button.party_drop`, `button.party_birthday`, `button.party_blackout`, `sensor.party_status`. Put them on a dashboard or use them in automations (for example: start the party when a playlist starts).

## Moving from AppDaemon

Turn off the `media_lights_sync` and `art_color` apps (remove them from `apps.yaml`), restart AppDaemon, restart Home Assistant once so the old `sensor.music_art_brightness` is gone, then start this add-on so its sensor takes the same entity ID.
