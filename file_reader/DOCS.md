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

## Backups

Tap **Backups** at the bottom of the add-on page to back up, download or restore. A backup is a `.zip` with the files it manages (your files folder) and its own data, plus everything in the Configuration tab.

| Option | Default | What |
|---|---|---|
| `backup_path` | `/share/addon_backups/file_reader` | Where backups go, inside `/share`, `/media` or `/homeassistant`. A folder keeps several dated backups. A path ending in `.zip` keeps one file that is replaced each time |
| `backup_every` | `daily` | `off`, `daily` or `weekly` automatic backups |
| `backup_keep` | `10` | How many backups to keep in the folder. Older ones are deleted |

- **Back up now** makes one straight away. **Download** saves one to your phone or computer.
- **Restore** (tap twice) first saves a safety copy (`..._pre-restore_...zip`, the newest 3 are kept), puts the Configuration tab settings back, and restarts the add-on. The data is put back as it starts, before it reads anything.
- **Restore from a file** takes a backup `.zip` you downloaded, for example to move to another Home Assistant.
- A backup from a different add-on is refused. The page only works from the Home Assistant sidebar, never on the add-on's own ports, because backups include its settings.
- Backups also hold any passwords or API keys from the Configuration tab, so treat the backup folder like your secrets.
