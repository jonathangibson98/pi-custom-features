# Changelog

## 1.5.1 - 2026-11-17

- Uses the shared **add-on wallpaper** you pick in Photo Hub (new *Add-on wallpaper* tab). This add-on's own Wallpaper option still wins when set.

## 1.5.0 - 2026-11-16

- **Pick the web UI wallpaper.** New **Wallpaper** option on the Configuration tab. Leave it empty to use your Home Assistant theme's wallpaper, enter `none` for no wallpaper, or point it at your own image: drop it in `/config/www` and enter the file name (e.g. `wallpaper.jpg`), `/local/wallpaper.jpg`, or a full `https://` link.

## 1.4.0 - 2026-11-16

- **Follows your Home Assistant theme.** The web UI now uses the colors of whatever theme Home Assistant is showing, light or dark, and changes live when you switch. Themes with a dashboard wallpaper and frosted-glass cards (like Apple / Liquid Glass themes) carry over too: wallpaper behind, see-through blurred cards, matching corners. Opened outside Home Assistant it keeps its own look.

## 1.3.1

- **Back up from Home Assistant.** The add-on now listens on stdin, so the `hassio.addon_stdin` action with `input: backup` makes a backup right away. One script can back up every add-on at once (see the repository README, "Back up all add-ons with one action")

## 1.3.0

- **Backups.** New **Backups** page (link at the bottom of the add-on page) to back up now, download, restore, or restore from an uploaded file. Backups go to `backup_path` (a folder, or one `.zip` file) automatically on the `backup_every` schedule, and the newest `backup_keep` are kept
- A backup holds the files it manages (your files folder) and its own data, plus the Configuration tab settings. Restoring saves a safety copy first, puts the settings back and restarts the add-on to put the data back
- The add-on now has Supervisor access (`hassio_api`, to restore its settings and restart itself) and `/share` access for the backup folder

## 1.2.4

- Start script quotes the options path and no longer masks `jq` errors.

## 1.2.3

### Changed
- **Sensor state is now the time the file last changed** (a timestamp sensor). The text is in the `content` attribute, the newest line in the new `last_line` attribute. If an automation used the old state as the last line, use `state_attr('sensor.file_reader_<name>', 'last_line')` instead.
- **Easier automations:** every file in the web page has an **Automate** button with copy-paste Home Assistant code for adding a line, replacing the file, and reading it back.

## 1.2.2

### Changed
- The web page no longer shows the changelog.
- Files in the list show a friendly name (`music_fact.txt` shows as Music Fact). Hover to see the real path.

## 1.2.1

### Fixed
- **"MQTT connection refused: Not authorized" with the Mosquitto add-on.** Mosquitto does not allow anonymous logins, so the add-on now gets the broker login from Home Assistant automatically when the MQTT username option is empty. No manual setup needed.

## 1.2.0

### Added
- **Subfolders:** every text file in the Files folder and all of its subfolders is now listed and becomes a sensor (up to 500 files). Folders show up in the name, for example `logs/door.txt`.
- **Send updates over MQTT:** publish to `file_reader/append/<path>` or `file_reader/overwrite/<path>` with the text as the payload, or to `file_reader/write` with JSON. No token needed.
- **REST API on port 8100** for `rest_command`, `curl` and scripts. Protected by the new **REST API token** option (off until you set one).
- Plain text bodies work on the REST API too, for example `curl --data "hello" .../api/file/log.txt`.
- Files changed outside the add-on (Samba, File editor, other add-ons) now update their sensors automatically. Check interval is the new **Scan interval** option.
- Writing to a path like `folder/sub/file.txt` creates the folders for you. Empty folders are removed when you delete the last file.
- Sensors have a new `path` attribute.

### Changed
- Very large files are read from the end, so growing logs stay fast. `line_count` still counts every line.
- Binary files and certificate/key/database files are ignored. Hidden files and folders (starting with a dot) are ignored.
- Retained MQTT update messages are ignored, so an update can never be applied twice after a restart.

### Fixed
- Symlinks can no longer be used to read files outside the Files folder.

## 1.1.0

### Added
- New **Files folder** option: pick where your files live (for example `/share/file_reader`).
- Add-on logo and icon.
- Changelog tab, Documentation tab and friendly option labels in the add-on settings.
- Web UI now shows the version, the folder in use, MQTT status and the changelog.
- Files from the old `/data/files` folder are copied once into a newly chosen folder.

### Fixed
- Add-on crashing on start with current `paho-mqtt` (version 2.x).
- MQTT never reconnecting if the broker started after the add-on. It now retries and re-syncs all sensors.
- File names are checked, so nobody can read or write outside the files folder.
- File names with quotes or special characters no longer break or inject into the web page.
- Deleting a file now also clears its state and attributes from MQTT.
- Very large files no longer overload Home Assistant sensor attributes (content is capped at 8000 characters, the end of the file is kept).
- `secrets.yaml` is never listed or exposed.

### Changed
- Removed old 32-bit architectures and the unused `schema_version` key.
- MQTT password is now hidden in the settings.

## 1.0.1
- Initial version: web UI and MQTT sensors for text files.
