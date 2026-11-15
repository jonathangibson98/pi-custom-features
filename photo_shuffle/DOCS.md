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
