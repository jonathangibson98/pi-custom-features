# Changelog

## 4.1.0

- **Backups.** New options `backup_enabled`, `backup_path` (default `/share/photo_shuffle_backups`), `backup_keep` (default 20) and `backup_interval_hours` (default 24). Your folder shuffles, Unsplash collections and settings are saved to a zip a minute after the add-on starts and then on that schedule. No new file is made when nothing changed. Your photos themselves are not copied.
- **Restore.** Put a backup's file name in the new `restore_backup` option and restart. A safety copy of the current settings is saved first, and the option clears itself afterwards.
- Each zip also holds `options_reference.json`, a copy of your settings with the Unsplash key and MQTT password hidden.
- The `share` folder is now mounted read-write (it was read-only) so backups can be saved there. Photo Hub still only reads your photo folders.

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
