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

## Folders

Each folder shuffle is an image entity that moves to a random photo on a timer, with no repeats until the folder has been used up. Each also gets a "next" button.

## Backups

Tap **Backups** at the bottom of the add-on page to back up, download or restore. A backup is a `.zip` with your shuffles and Unsplash collections (thumbnails are left out, they're rebuilt by themselves), plus everything in the Configuration tab.

| Option | Default | What |
|---|---|---|
| `backup_path` | `/share/addon_backups/photo_shuffle` | Where backups go, inside `/share`, `/media` or `/homeassistant`. A folder keeps several dated backups. A path ending in `.zip` keeps one file that is replaced each time |
| `backup_every` | `daily` | `off`, `daily` or `weekly` automatic backups |
| `backup_keep` | `10` | How many backups to keep in the folder. Older ones are deleted |

- **Back up now** makes one straight away. **Download** saves one to your phone or computer.
- **Restore** (tap twice) first saves a safety copy (`..._pre-restore_...zip`, the newest 3 are kept), puts the Configuration tab settings back, and restarts the add-on. The data is put back as it starts, before it reads anything.
- **Restore from a file** takes a backup `.zip` you downloaded, for example to move to another Home Assistant.
- A backup from a different add-on is refused. The page only works from the Home Assistant sidebar, never on the add-on's own ports, because backups include its settings.
- Backups also hold any passwords or API keys from the Configuration tab, so treat the backup folder like your secrets.

## Add-on wallpaper

The **Add-on wallpaper** tab sets one background for the web page of every add-on (Photo Hub, Sleep Tracker, AI Builder, Travel Times, Personal AI Gateway…):

- **Upload a picture** from your phone or computer.
- **Pick from your photo folders** (the paths in *photo_paths*).
- **Follow a folder shuffle or Unsplash collection**: the wallpaper changes every time it shows a new photo.
- **Off**: add-ons use your Home Assistant theme's wallpaper again.

Photo Hub saves it to `/config/www/addon-wallpaper/` (served by Home Assistant at `/local/addon-wallpaper/`). An add-on's own **Wallpaper** option on its Configuration tab still wins, if you set one.
