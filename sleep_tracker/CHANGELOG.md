# Changelog

## 1.3.2 - 2026-11-17

- **Easier to read over wallpapers.** When the page shows a wallpaper (your theme's, the shared one from Photo Hub, or your own), it now checks how bright the picture is and lays down just enough of a tint for the text to stay readable: bright wallpapers get more, dark ones barely any. Text also gets a soft shadow.

## 1.3.1 - 2026-11-17

- Uses the shared **add-on wallpaper** you pick in Photo Hub (new *Add-on wallpaper* tab). This add-on's own Wallpaper option still wins when set.

## 1.3.0 - 2026-11-16

- **Pick the web UI wallpaper.** New **Wallpaper** option on the Configuration tab. Leave it empty to use your Home Assistant theme's wallpaper, enter `none` for no wallpaper, or point it at your own image: drop it in `/config/www` and enter the file name (e.g. `wallpaper.jpg`), `/local/wallpaper.jpg`, or a full `https://` link.

## 1.2.0 - 2026-11-16

- **Follows your Home Assistant theme.** The web UI now uses the colors of whatever theme Home Assistant is showing, light or dark, and changes live when you switch. Themes with a dashboard wallpaper and frosted-glass cards (like Apple / Liquid Glass themes) carry over too: wallpaper behind, see-through blurred cards, matching corners. Opened outside Home Assistant it keeps its own look.

## 1.1.2

- Removed personal names, places and home-specific entity IDs from the defaults, examples and docs, so new installs start clean.

## 1.1.1 - 2026-11-15

- **Back up from Home Assistant.** The add-on now listens on stdin, so the `hassio.addon_stdin` action with `input: backup` makes a backup right away. One script can back up every add-on at once (see the repository README, "Back up all add-ons with one action")

## 1.1.0 - 2026-11-15

- **Backups.** New **Backups** page (link at the bottom of the add-on page) to back up now, download, restore, or restore from an uploaded file. Backups go to `backup_path` (a folder, or one `.zip` file) automatically on the `backup_every` schedule, and the newest `backup_keep` are kept
- A backup holds your people, their signals and settings, the current sleep state and the sleep history, plus the Configuration tab settings. Restoring saves a safety copy first, puts the settings back and restarts the add-on to put the data back
- The add-on now has Supervisor access (`hassio_api`, to restore its settings and restart itself) and `/share` access for the backup folder

## 1.0.0 - 2026-11-15

- First release. Track any `person`: weighted signals with a sleep confidence score, fall-asleep and wake levels, settle and
  wake times, must-be-true signals that wake instantly, night hours, optional naps and home-only tracking
- Signals suggested from the person's Companion app sensors (charging, Focus, activity, Android sleep confidence and screen)
  and a bedroom area's lights, TVs and motion sensors
- Bedtime is dated back to when the signals first agreed. Short wake-ups are interruptions of the same night
- MQTT entities: asleep, sleep status, confidence, last sleep (with history and a 7-night average), mark asleep / awake buttons,
  and Everyone asleep
- Web UI with live signals, recent nights, manual marking and deleting wrong nights
