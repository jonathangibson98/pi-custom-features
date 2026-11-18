# Changelog

## 1.1.1 - 2026-11-17

- Store description updated for the new modes and games. Docs and README rewritten.

## 1.1.0 - 2026-11-17

- **New page**, built for phones first: tabs at the bottom, a now-playing card with the current mode and running games, a grid of light modes with icons, sliders that stay in view, game cards with their own settings, filters and pop-up confirmations. Two columns on a computer.
- **12 new light modes**: Twinkle, Comet, Ping pong, Heartbeat, Aurora, Ocean waves, Alternate, Fireworks, Spotlight, Glitch, Lava lamp and Shuffle shows. New color themes: Aurora, Candy cane and Tropical.
- **13 new games and extras**: Freeze dance, Red light green light, Never have I ever, Truth or dare, Party trivia, Name that tune, Rule maker, Welcome arrivals, Last call, Hot potato, Light roulette, Cheers! and Dance battle. The prompt games use your AI, with a built-in list when there's no AI.
- **Pick the mode without the page**: link a dropdown helper (or let the add-on make `input_select.party_lights_mode`). Pick a mode on a dashboard, in an automation or by voice; Off ends the party. It stays in step both ways. Also: `hassio.addon_stdin` commands (`off`, `disco`, `party on`, `game trivia on`), and MQTT switches and buttons for every new game.

## 1.0.0 - 2026-11-17

- First release. Replaces the `media_lights_sync` and `art_color` AppDaemon apps (no AppDaemon needed) and adds light shows and party games:
  - **Music sync**: lights take the album art's colors, one color per light, with color boost, brightness, fade, an "only when" mode helper and an always-on option.
  - **Album art sensor**: brightness (0–255), main color, palette and a readable text color for the current art. Defaults to `sensor.music_art_brightness`.
  - **Light shows**: static, color loop, rainbow wave, disco, chase, pulse to a BPM, breathe, strobe, sparkle, fire, police and lightning storm, with speed and brightness.
  - **Colors**: party, rainbow, neon, chill, sunset, ocean, Christmas, Halloween, 4th of July, Valentine's, St. Patrick's, New Year's, birthday, the album art, team colors from a Team Tracker sensor, your own, or ✨ AI colors from a description.
  - **Games & extras**: power hour, shot caller (picks someone who's home), countdown with a 10-second light countdown and celebration, AI hype MC, flash, drop the beat, birthday blast and blackout.
  - Lights are put back the way they were when the party ends.
  - Every control is also a Home Assistant entity over MQTT: `switch.party_mode`, `select.party_effect`, `select.party_colors`, `number.party_speed`, `number.party_brightness`, `number.party_bpm`, switches for the games, buttons for the quick hits and `sensor.party_status`.
