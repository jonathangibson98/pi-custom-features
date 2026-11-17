# Changelog

## 1.0.0 - 2026-11-17

- First release. Replaces the `media_lights_sync` and `art_color` AppDaemon apps (no AppDaemon needed) and adds light shows and party games:
  - **Music sync**: lights take the album art's colors, one color per light, with color boost, brightness, fade, an "only when" mode helper and an always-on option.
  - **Album art sensor**: brightness (0–255), main color, palette and a readable text color for the current art. Defaults to `sensor.music_art_brightness`.
  - **Light shows**: static, color loop, rainbow wave, disco, chase, pulse to a BPM, breathe, strobe, sparkle, fire, police and lightning storm, with speed and brightness.
  - **Colors**: party, rainbow, neon, chill, sunset, ocean, Christmas, Halloween, 4th of July, Valentine's, St. Patrick's, New Year's, birthday, the album art, team colors from a Team Tracker sensor, your own, or ✨ AI colors from a description.
  - **Games & extras**: power hour, shot caller (picks someone who's home), countdown with a 10-second light countdown and celebration, AI hype MC, flash, drop the beat, birthday blast and blackout.
  - Lights are put back the way they were when the party ends.
  - Every control is also a Home Assistant entity over MQTT: `switch.party_mode`, `select.party_effect`, `select.party_colors`, `number.party_speed`, `number.party_brightness`, `number.party_bpm`, switches for the games, buttons for the quick hits and `sensor.party_status`.
