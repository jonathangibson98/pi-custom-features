# Photo Hub

Publishes photos to Home Assistant as **image entities** over MQTT, from two sources, managed in one web UI (sidebar: Photo Hub).

## Setup

1. Install and start the **Mosquitto broker** add-on with the MQTT integration, or set the `mqtt_*` options below to use your own broker.
2. Start Photo Hub and open it from the sidebar.
3. Add a **folder shuffle** or an **Unsplash collection**. Entities appear in Home Assistant automatically.

## Options

| Option | Description |
| --- | --- |
| `photo_paths` | Folders the add-on may read. Must start with `/media`, `/share`, `/homeassistant` or `/addon_configs`. |
| `formats` | Picture types included in folder shuffles. `jpg` covers `.jpg` and `.jpeg`. |
| `max_dimension` | Longest side of every published picture, in pixels. Larger photos are scaled down. |
| `jpeg_quality` | Quality of the published JPEG (30 to 100). |
| `unsplash_access_key` | Optional. The Unsplash **Access Key** (not the Secret Key). |
| `unsplash_interval_minutes` | How often each Unsplash collection gets a new photo. The free tier allows 50 requests per hour. |
| `unsplash_image_size` | `full`, `regular` (about 1080px) or `small`. |
| `mqtt_host`, `mqtt_port`, `mqtt_username`, `mqtt_password` | Optional. Leave empty to use the Mosquitto add-on automatically. |
| `backup_enabled`, `backup_path`, `backup_keep`, `backup_interval_hours`, `restore_backup` | See [Backup and restore](#backup-and-restore). |

## Folders

Each folder shuffle is an image entity that moves to a random photo on a timer, with no repeats until the folder has been used up. Each also gets a "next" button.

## Backup and restore

Photo Hub saves your setup to a zip file so you can recover it after a reinstall or a failed SD card.

| Option | Default | What it does |
| --- | --- | --- |
| `backup_enabled` | `true` | Turns automatic backups on or off. |
| `backup_path` | `/share/photo_shuffle_backups` | Folder for the zip files. Use a folder inside `/share`. |
| `backup_keep` | `20` | How many backups to keep. The oldest are deleted. |
| `backup_interval_hours` | `24` | Hours between backups. `0` backs up only when the add-on starts. |
| `restore_backup` | empty | File name of a backup to restore (see below). |

A backup is made about a minute after the add-on starts and then every `backup_interval_hours`. If nothing changed since the last backup, no new file is made.

A backup holds your folder shuffles, Unsplash collections and their saved state. **Your photos are not copied**, and the Unsplash preview thumbnails are rebuilt automatically. Each zip also has `options_reference.json`, a copy of your settings with the Unsplash key and MQTT password replaced by `***`. It is for reading only and is never restored.

**To restore:**

1. Open your backup folder (Samba or the File editor) and copy the name of the zip, for example `photo_shuffle-20261115-021500.zip`. The add-on log also lists the newest backups each time it starts.
2. Paste that name into `restore_backup` on the Configuration tab and save.
3. Restart the add-on.

The add-on first saves a safety copy of the current setup (named `photo_shuffle-prerestore-...zip`), puts the backed up files back before it starts, and clears `restore_backup` itself. If the option does not clear, empty it by hand so the restore is not repeated.
