# File Reader

Create and edit text files from the web UI. Every text file in your folder, **including subfolders**, becomes a sensor in Home Assistant through MQTT.
The sensor state is the **last line** of the file. The full text is in the `content` attribute (last 8000 characters), plus `path`, `line_count` and `truncated`.

Files you edit outside the add-on (Samba, File editor) are picked up automatically within the scan interval.

## Settings

| Option | What it does |
| --- | --- |
| Files folder | Where files are saved. Must start with `/data`, `/share`, `/media`, `/homeassistant` or `/config`. |
| Scan interval | Seconds between checks for files changed outside the add-on. Default 30. |
| REST API token | Password for the REST API on port 8100. Empty means the REST API is off. |
| MQTT host / port | Your broker. The defaults work with the Mosquitto add-on. |
| MQTT username / password | Leave empty to use the login Home Assistant provides for the Mosquitto add-on automatically. Only fill in for an external broker. |
| Backups on, Backup folder, Backups to keep, Hours between backups, Restore this backup | See [Backup and restore](#backup-and-restore). |

### Folder cheat sheet

| Path | Where it is |
| --- | --- |
| `/data/files` | Private to this add-on (default, hidden from you). |
| `/share/file_reader` | The `share` folder, visible in Samba and the File editor. Recommended. |
| `/media/file_reader` | The `media` folder. |
| `/homeassistant/file_reader` | Inside your Home Assistant config folder. |
| `/config/file_reader` | This add-on's own config folder. |

Use a **dedicated folder**. Every text file inside it (and below it) becomes a sensor. Binary files, hidden files, `secrets.yaml` and key/certificate/database files are ignored. The limit is 500 files.

After changing the folder, restart the add-on. Existing files from `/data/files` are copied over once.

## Backup and restore

The add-on saves your files to a zip file so you can recover them after a reinstall, a bad edit or a failed SD card.

| Option | Default | What it does |
| --- | --- | --- |
| `backup_enabled` | `true` | Turns automatic backups on or off. |
| `backup_path` | `/share/file_reader_backups` | Folder for the zip files. Use a folder this add-on can write to, such as one inside `/share`. |
| `backup_keep` | `20` | How many backups to keep. The oldest are deleted. |
| `backup_interval_hours` | `24` | Hours between backups. `0` backs up only when the add-on starts. |
| `restore_backup` | empty | File name of a backup to restore (see below). |

A backup is made about a minute after the add-on starts and then every `backup_interval_hours`. If nothing changed since the last backup, no new file is made.

A backup holds everything in your Files folder (files larger than 25 MB are skipped) and the add-on's private data. Each zip also has `options_reference.json`, a copy of your settings with the API token, MQTT password and similar secrets replaced by `***`. It is for reading only and is never restored.

**To restore:**

1. Open your backup folder (Samba or the File editor) and copy the name of the zip, for example `file_reader-20261115-021500.zip`. The add-on log also lists the newest backups each time it starts.
2. Paste that name into `restore_backup` on the Configuration tab and save.
3. Restart the add-on.

The add-on first saves a safety copy of the current files (named `file_reader-prerestore-...zip`), puts the backed up files back before it starts, and clears `restore_backup` itself. Files that are not in the backup are left alone. If the option does not clear, empty it by hand so the restore is not repeated.

If you moved the Files folder since the backup was made, set the Files folder back to the old path before restoring.

## Sending updates from automations and scripts

### Option 1: MQTT (easiest, no token)

Add a line to a file (a new line is added only if the file already has content):

```yaml
action: mqtt.publish
data:
  topic: file_reader/append/logs/door.txt
  payload: "Front door opened at {{ now().strftime('%H:%M') }}"
```

Replace the whole file:

```yaml
action: mqtt.publish
data:
  topic: file_reader/overwrite/status/house.txt
  payload: "{{ states('alarm_control_panel.home') }}"
```

JSON version (file name, text and mode in one message):

```yaml
action: mqtt.publish
data:
  topic: file_reader/write
  payload: >-
    {{ {"file": "logs/door.txt", "text": "Door opened", "mode": "append"} | tojson }}
```

Do **not** turn on `retain` for these. Retained messages are ignored on purpose.

### Option 2: REST API (rest_command, curl, scripts)

1. Set **REST API token** in the add-on settings and restart.
2. Put the token in your `secrets.yaml` and add this to `configuration.yaml`:

```yaml
rest_command:
  file_reader_append:
    url: "http://127.0.0.1:8100/api/file/{{ file }}"
    method: post
    headers:
      Authorization: "Bearer YOUR_TOKEN"
      Content-Type: application/json
    payload: '{"text": {{ text | tojson }}, "mode": "append"}'
```

3. Call it from an automation or script:

```yaml
action: rest_command.file_reader_append
data:
  file: logs/door.txt
  text: "Front door opened"
```

If `127.0.0.1` doesn't work on your install, use your Home Assistant IP address instead.

From a computer or script:

```
curl -X POST -H "Authorization: Bearer YOUR_TOKEN" \
  --data "hello" "http://HA_IP:8100/api/file/logs/door.txt?mode=append"
```

| Request | What it does |
| --- | --- |
| `GET /api/files` | List every file (with folders). |
| `GET /api/file/<path>` | Read a file. |
| `POST /api/file/<path>` | Write. JSON `{"text": "...", "mode": "append" or "overwrite"}`, or a plain text body with `?mode=`. |
| `DELETE /api/file/<path>` | Delete a file. |

## Notes
- Folders are created automatically when you write to `folder/sub/file.txt`.
- Sensor attributes hold at most the last 8000 characters of a file.
- The web editor opens files up to 2 MB.
