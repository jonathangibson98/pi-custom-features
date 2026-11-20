# Changelog

## 1.5.0 - 2026-11-20

- **Make as many music modes as you want, named whatever you like.** On the Music tab, tap **+ New mode** (Movie night, Dinner, Kitchen only…), pick an icon, and start blank or as a copy of the mode you're on. Each mode has its own lights, players, per-light edits, condition and options. **Music sync** stays as the first one.
- Every new mode shows up in the light mode list everywhere: the Party tab, the dashboard dropdown (added to a linked `input_select` automatically), the `Light mode` select over MQTT and `hassio.addon_stdin` (`input: movie night`). Pick it to run it.
- A mode can also run by itself: give it a condition, a template, or **Sync even when the party is off**, like separate `media_lights_sync` apps did. Each mode has its own "put lights back" snapshot.
- **Rename** and **Delete** a mode from the Music tab. Deleting the running one switches to Music sync.
- **Import from AppDaemon** makes a mode for every block you paste from `apps.yaml`, named after the block. One block fills the mode you're on.

## 1.4.0 - 2026-11-20

- **Devices section on the Music tab.** Every light and music player music sync uses is in one list: tap ✎ to edit it, ↑↓ to change which light gets which color, and a switch to turn a device off for music sync without removing it. Add or remove devices from the same place.
- **Per-light settings**: pick which cover color a light gets (Auto or Color 1–8), and give it its own brightness and fade instead of the shared ones.
- **`media_lights_sync` options, now built in**: put the lights back when the music stops (`reset_lights_after`), choose how colors are picked from the cover (Fast octree, Median cut, Max coverage, libimagequant), an "only sync when this template is true" condition (`value_template`), HTTPS certificate checking (`verify_cert`) and a Home Assistant URL for relative cover links (`ha_url`).
- **Import from AppDaemon**: paste your `media_lights_sync` block from `apps.yaml` on the Music tab and its lights, players, condition and options are filled in for you.
- The Dockerfile now installs `pyyaml` for the import.

## 1.3.0 - 2026-11-17

- **One dropdown for sports and party lights.** New **Sports** mode in every mode list (page, `input_select.party_lights_mode`, the `Light mode` select and `hassio.addon_stdin`). Picking it stops the party and hands the lights to Team Tracker Lite's Score lights; picking any other mode (or Off) takes them back and Off puts the lights back as they were. Set Score lights' "only when" to the same dropdown with the state `Sports`, and you can drop the second dropdown.
- A linked `input_select` now gets every mode added to it automatically (nothing is removed), so an existing helper becomes the one dropdown.

## 1.2.0 - 2026-11-17

- **Fixed: music sync never changed the lights** when no player was picked under *Music players to follow* (only the album-art sensor's player). It now follows the album-art player, or whatever is playing, when that list is empty.
- **Fixed: "All lights the same color"** used the first color from the cover, often a dull near-black. It now uses the most colorful one.
- **Music sync checklist**: the Music tab shows ✓/✕ for the player, playback, lights and your helper, plus when it last synced and to what colors.
- **Far fewer Home Assistant entities**: one switch, light mode, colors, brightness, speed, a **Game** dropdown, a **Quick hit** dropdown and a status sensor, instead of a switch or button per game. The old ones are removed automatically.
- **New page, built for iPhone**: bottom tab bar clear of the home indicator, big round party button, 3-across light modes, swipeable colors, iOS-style switches for games, game settings in a pull-up sheet (long-press a quick hit for its settings), 16 px inputs so iOS doesn't zoom, haptic taps where supported. Players, lights and speakers save as soon as you pick them.
- Shared phone fixes like every other add-on: text fields no longer make iOS zoom in, buttons and switches are finger-sized, rows of tabs swipe sideways instead of getting cut off, and wide content or long error text no longer pushes the page sideways.

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
