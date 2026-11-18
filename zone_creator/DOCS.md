<!-- docs:header (generated, edit .github/docsgen) -->
# Zone Creator

![Version](https://img.shields.io/badge/dynamic/yaml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fjonathangibson98%2Fpi-custom-features%2Fmain%2Fzone_creator%2Fconfig.yaml&query=%24.version&label=version&color=41BDF5&logo=homeassistant) ![Architectures](https://img.shields.io/badge/arch-aarch64%20%7C%20amd64-informational) ![Sidebar](https://img.shields.io/badge/sidebar-ingress-success) ![Prebuilt image](https://img.shields.io/badge/image-GHCR-2ea44f?logo=docker) ![AI Task](https://img.shields.io/badge/AI-ai__task-8A2BE2?logo=googlegemini)

> Search an address, drop a pin and create a Home Assistant zone, with optional AI name and icon suggestions.

## At a glance

| | |
|---|---|
| Version | `1.4.2` |
| Slug | `zone_creator` |
| Architectures | `aarch64`, `amd64` |
| Opens from | the sidebar (**Zone Creator**, ingress) |
| Extra ports | none |
| Folders it can reach | `share` |
| API access | Home Assistant API, Supervisor API |
| MQTT | not used |
| Takes commands via `hassio.addon_stdin` | yes |
| Install | prebuilt image from GHCR |

**You'll need:**

- Nothing extra
- An `ai_task` entity (optional)

## Contents

- [Using it](#using-it)
- [Options](#options)
- [How the AI part works](#how-the-ai-part-works)
- [How address search works](#how-address-search-works)
- [Troubleshooting](#troubleshooting)
- [Privacy](#privacy)
- [Backups](#backups)
- [Configuration reference](#configuration-reference)
- [Help and feedback](#help-and-feedback)
<!-- /docs:header -->

## Using it
1. Type an address or place in the search box and press Enter. You can also paste
   coordinates like `40.7128, -74.0060`.
2. Tap a result. The map jumps there and drops a pin.
3. Drag the pin or tap the map to adjust. Change the radius if needed.
4. Set the name and icon (or let the AI do it), then tap **Create zone**.

New zones appear immediately under Settings > Areas, labels & zones > Zones.

## Options

Every option is listed with its default in the [Configuration reference](#configuration-reference) at the end of this page.

Restart the add-on after changing options.

## How the AI part works
After you pick a result, the add-on sends the place name and your existing zone names
to the `ai_task.generate_data` service and asks for a short name and one mdi icon.
The ✨ AI button asks again for a different take. If the AI fails or returns junk,
you get an error message and can type the name and icon yourself.

## How address search works
Searches run against three free services at the same time and the results are merged:

- US Census Geocoder: best for US street addresses
- OpenStreetMap Nominatim: best for businesses and landmarks
- Photon: backup

No API keys needed. Only the text you search for leaves your network.

## Troubleshooting

**"No match" on an address**
- Use the format `123 Main St, City, ST`. Adding the city and state helps a lot.
- Read the red error box under the button. It lists what each service said.
- If the add-on can't reach the internet, check HA's DNS settings.
- Fallback: tap the map to place the pin yourself, or paste coordinates.

**Create zone fails**
The add-on creates zones over the Home Assistant websocket API using its Supervisor token.
Check the add-on log for the exact error and open an issue with it.

**Icon preview is blank**
The icon name isn't a real Material Design Icon. Look up a valid one at pictogrammers.com/library/mdi.

## Privacy
Searches go to the services above. The AI call goes only to your own Home Assistant.

## Backups

Tap **Backups** at the bottom of the add-on page to back up, download or restore. A backup is a `.zip` with its settings (zones themselves live in Home Assistant, so a Home Assistant backup covers them), plus everything in the Configuration tab.

| Option | Default | What |
|---|---|---|
| `backup_path` | `/share/addon_backups/zone_creator` | Where backups go, inside `/share`, `/media` or `/homeassistant`. A folder keeps several dated backups. A path ending in `.zip` keeps one file that is replaced each time |
| `backup_every` | `daily` | `off`, `daily` or `weekly` automatic backups |
| `backup_keep` | `10` | How many backups to keep in the folder. Older ones are deleted |

- **Back up now** makes one straight away. **Download** saves one to your phone or computer.
- **Restore** (tap twice) first saves a safety copy (`..._pre-restore_...zip`, the newest 3 are kept), puts the Configuration tab settings back, and restarts the add-on. The data is put back as it starts, before it reads anything.
- **Restore from a file** takes a backup `.zip` you downloaded, for example to move to another Home Assistant.
- A backup from a different add-on is refused. The page only works from the Home Assistant sidebar, never on the add-on's own ports, because backups include its settings.
- Backups also hold any passwords or API keys from the Configuration tab, so treat the backup folder like your secrets.

<!-- docs:config (generated from config.yaml) -->
## Configuration reference

Every option on the add-on's **Configuration** tab, with its default. Change them there, then restart the add-on.

| Option | Default | Type | What it does |
|---|---|---|---|
| `ai_task_entity` | *(empty)* | text, optional | **AI Task entity (optional).** An ai_task entity used to suggest a zone name and icon, for example ai_task.google_ai_task. Leave blank to turn AI suggestions off. |
| `default_radius` | `100` | whole number (10–5000) | **Default radius (meters).** Starting radius for new zones. You can still change it per zone in the UI. |
| `backup_path` | `/share/addon_backups/zone_creator` | text | **Backup folder.** Where backups are saved, inside /share, /media or /homeassistant. A folder keeps several dated backups. A path ending in .zip keeps one file that is replaced each time. Open Backups in the add-on page to back up, download or restore. |
| `backup_every` | `daily` | one of: `off`, `daily`, `weekly` | **Automatic backups.** How often a backup is made by itself (off, daily or weekly). |
| `backup_keep` | `10` | whole number (1–100) | **Backups to keep.** The newest this many backups are kept in the folder, older ones are deleted. |
| `wallpaper` | *(empty)* | text, optional | **Wallpaper.** Background image for this add-on's web UI. Leave empty to use your Home Assistant theme's wallpaper, "none" for no wallpaper, or an image: put it in /config/www and enter its file name (pic.jpg) or /local/pic.jpg, or a full https:// link. |
<!-- /docs:config -->

<!-- docs:footer (generated) -->
## Help and feedback

- **Logs:** the add-on's **Log** tab shows what it's doing and most errors in plain words.
- **Changes:** see the [changelog](CHANGELOG.md) (also on the add-on's **Changelog** tab).
- **Problems or ideas:** [open an issue](https://github.com/jonathangibson98/pi-custom-features/issues) and include the add-on version and the log.
- **Pages follow your theme:** every page in this repository picks up your Home Assistant theme and wallpaper automatically.
<!-- /docs:footer -->
