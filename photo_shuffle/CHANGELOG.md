# Changelog

## 4.3.0 - 2026-11-16

- **Pick the web UI wallpaper.** New **Wallpaper** option on the Configuration tab. Leave it empty to use your Home Assistant theme's wallpaper, enter `none` for no wallpaper, or point it at your own image: drop it in `/config/www` and enter the file name (e.g. `wallpaper.jpg`), `/local/wallpaper.jpg`, or a full `https://` link.

## 4.2.0 - 2026-11-16

- **Follows your Home Assistant theme.** The web UI now uses the colors of whatever theme Home Assistant is showing, light or dark, and changes live when you switch. Themes with a dashboard wallpaper and frosted-glass cards (like Apple / Liquid Glass themes) carry over too: wallpaper behind, see-through blurred cards, matching corners. Opened outside Home Assistant it keeps its own look.

## 4.1.1

- **Back up from Home Assistant.** The add-on now listens on stdin, so the `hassio.addon_stdin` action with `input: backup` makes a backup right away. One script can back up every add-on at once (see the repository README, "Back up all add-ons with one action")

## 4.1.0

- **Backups.** New **Backups** page (link at the bottom of the add-on page) to back up now, download, restore, or restore from an uploaded file. Backups go to `backup_path` (a folder, or one `.zip` file) automatically on the `backup_every` schedule, and the newest `backup_keep` are kept
- A backup holds your shuffles and Unsplash collections (thumbnails are left out, they're rebuilt by themselves), plus the Configuration tab settings. Restoring saves a safety copy first, puts the settings back and restarts the add-on to put the data back
- The add-on now has Supervisor access (`hassio_api`, to restore its settings and restart itself) and `/share` access for the backup folder

## 4.0.3

- Fix: Photo Hub could lose its MQTT connection and never get it back, leaving every image entity unavailable until the add-on was restarted by hand. It now watches its own connection and, if it is down for more than a minute or stops answering, throws the connection away and rebuilds it with freshly fetched broker settings (this also covers a changed Mosquitto login).
- An error while announcing entities can no longer kill the MQTT network loop.
- Each connection uses a unique client id, so two copies of the add-on can no longer kick each other off the broker.
- Photos are no longer downloaded from Unsplash while MQTT is down (that wasted your hourly request limit). They are fetched again as soon as MQTT is back.
- A folder shuffle photo that could not be delivered is retried within 10 seconds instead of waiting a full interval.

## 4.0.2

- Now published as a prebuilt image (`ghcr.io/jonathangibson98/{arch}-addon-photo_shuffle`), so it installs without building on the Pi.
- The add-on page link now points at this repository.

## 4.0.1
- Fix: the image build failed for armv7. The Home Assistant base image no longer supports armv7, so Photo Hub now supports aarch64 and amd64 only.

## 2.0.0
- Photo Shuffle and Photo Puller merged into one add-on, Photo Hub
- Folder shuffles and Unsplash collections both publish over MQTT
- Single web UI with live previews and an activity log
