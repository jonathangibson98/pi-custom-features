# Changelog

## 1.4.2 - 2026-11-17

- **Easier to read over wallpapers.** When the page shows a wallpaper (your theme's, the shared one from Photo Hub, or your own), it now checks how bright the picture is and lays down just enough of a tint for the text to stay readable: bright wallpapers get more, dark ones barely any. Text also gets a soft shadow.

## 1.4.1 - 2026-11-17

- Uses the shared **add-on wallpaper** you pick in Photo Hub (new *Add-on wallpaper* tab). This add-on's own Wallpaper option still wins when set.

## 1.4.0 - 2026-11-16

- **Pick the web UI wallpaper.** New **Wallpaper** option on the Configuration tab. Leave it empty to use your Home Assistant theme's wallpaper, enter `none` for no wallpaper, or point it at your own image: drop it in `/config/www` and enter the file name (e.g. `wallpaper.jpg`), `/local/wallpaper.jpg`, or a full `https://` link.

## 1.3.0 - 2026-11-16

- **Follows your Home Assistant theme.** The web UI now uses the colors of whatever theme Home Assistant is showing, light or dark, and changes live when you switch. Themes with a dashboard wallpaper and frosted-glass cards (like Apple / Liquid Glass themes) carry over too: wallpaper behind, see-through blurred cards, matching corners. Opened outside Home Assistant it keeps its own look.

## 1.2.2

- Removed personal names, places and home-specific entity IDs from the defaults, examples and docs, so new installs start clean.

## 1.2.1

- **Back up from Home Assistant.** The add-on now listens on stdin, so the `hassio.addon_stdin` action with `input: backup` makes a backup right away. One script can back up every add-on at once (see the repository README, "Back up all add-ons with one action")

## 1.2.0

- **Backups.** New **Backups** page (link at the bottom of the add-on page) to back up now, download, restore, or restore from an uploaded file. Backups go to `backup_path` (a folder, or one `.zip` file) automatically on the `backup_every` schedule, and the newest `backup_keep` are kept
- A backup holds its settings (zones themselves live in Home Assistant, so a Home Assistant backup covers them), plus the Configuration tab settings. Restoring saves a safety copy first, puts the settings back and restarts the add-on to put the data back
- The add-on now has Supervisor access (`hassio_api`, to restore its settings and restart itself) and `/share` access for the backup folder

## 1.1.1
- Now published as a prebuilt image (`ghcr.io/jonathangibson98/{arch}-addon-zone_creator`), so it installs without building on the Pi.
- The add-on page link now points at the repository that actually exists.

## 1.1.0
- Fixed "can't find address" searches. Search now asks three geocoders at once
  (US Census, OpenStreetMap Nominatim, Photon) and merges the results.
- Outbound lookups are forced to IPv4, which fixes hangs on some Docker/HAOS networks.
- When nothing is found, the real error from each provider is shown instead of a vague message.
- You can paste "lat, lon" into the search box to jump straight to a point.
- Added icon, logo, docs, and config option labels.

## 1.0.0
- First release: address search, draggable pin with live radius circle,
  optional AI name and icon suggestions, one-tap zone creation.
