<!-- docs:header (generated, edit .github/docsgen) -->
# Team Tracker Lite

![Version](https://img.shields.io/badge/dynamic/yaml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fjonathangibson98%2Fpi-custom-features%2Fmain%2Fteam_tracker_lite%2Fconfig.yaml&query=%24.version&label=version&color=41BDF5&logo=homeassistant) ![Architectures](https://img.shields.io/badge/arch-aarch64%20%7C%20amd64-informational) ![Sidebar](https://img.shields.io/badge/sidebar-ingress-success) ![Prebuilt image](https://img.shields.io/badge/image-GHCR-2ea44f?logo=docker) ![MQTT](https://img.shields.io/badge/MQTT-optional-660066?logo=mqtt) ![AI Task](https://img.shields.io/badge/AI-ai__task-8A2BE2?logo=googlegemini)

> One lightweight sports sensor: pick any team from a menu and switch whenever you like.

## At a glance

| | |
|---|---|
| Version | `0.8.0` |
| Slug | `team_tracker_lite` |
| Architectures | `aarch64`, `amd64` |
| Opens from | the sidebar (**Team Tracker**, ingress) |
| Extra ports | `8100/tcp` |
| Folders it can reach | `share`, `addon_config` |
| API access | Home Assistant API, Supervisor API |
| MQTT | optional (used when available) |
| Takes commands via `hassio.addon_stdin` | yes |
| Install | prebuilt image from GHCR |

**You'll need:**

- MQTT (Mosquitto add-on or your own broker)

## Contents

- [Setup](#setup)
- [Live game](#live-game)
- [Calendar (one-time setup)](#calendar-one-time-setup)
- [Your settings](#your-settings)
- [Options](#options)
- [Not supported](#not-supported)
- [Backups](#backups)
- [AI help](#ai-help)
- [Score lights](#score-lights)
- [Configuration reference](#configuration-reference)
- [Help and feedback](#help-and-feedback)
<!-- /docs:header -->

One sensor. Any team. Picked from a menu in the sidebar panel.

## Setup
1. On the **Configuration** tab, enter your MQTT broker (host, port, user, password). Leave `mqtt_host` blank only if you use the Mosquitto broker add-on.
2. Start the add-on and open **Team Tracker** in the sidebar.
3. Pick a league, pick a team, tap **Add team**. Repeat for any teams you want to switch between.
4. Tap **Track** on the team you want the sensor to show.

The sensor is `sensor.team_tracker` (rename it in the panel). States are `PRE`, `IN`, `POST` and `NOT_FOUND`.

## Live game
In the panel's **Live game** card, pick a sport and tap **Track** next to a team in any game that's on now. The sensor follows that game. It is never added to the calendar.

## Calendar (one-time setup)
The add-on publishes a feed of every game for your saved teams. Add it to Home Assistant once:
1. Add your teams first.
2. Settings, Devices & services, Add integration, **Remote Calendar**.
3. Name it **Team Games** and paste the link shown in the panel's Calendar section.

Every day at the time you choose in the panel, the add-on refreshes the schedules and tells Home Assistant to reload the calendar. If your calendar entity isn't `calendar.team_games`, enter its name in the panel.

## Your settings
Saved in `/addon_configs/<id>_team_tracker_lite/data/settings.json`.

## Options
- `publish_team_selector`: also creates a `select` entity so automations and dashboards can switch teams (it includes the live game).
- `log_level`: `debug`, `info`, `warning` or `error`. Use `debug` when troubleshooting.

Refresh speeds and the calendar time are set in the panel, not here.

## Not supported
Golf, tennis, racing, UFC and custom API paths. Team sports only.

## Backups

Tap **Backups** at the bottom of the add-on page to back up, download or restore. A backup is a `.zip` with your saved teams, the tracked team and the calendar settings, plus everything in the Configuration tab.

| Option | Default | What |
|---|---|---|
| `backup_path` | `/share/addon_backups/team_tracker_lite` | Where backups go, inside `/share`, `/media` or `/homeassistant`. A folder keeps several dated backups. A path ending in `.zip` keeps one file that is replaced each time |
| `backup_every` | `daily` | `off`, `daily` or `weekly` automatic backups |
| `backup_keep` | `10` | How many backups to keep in the folder. Older ones are deleted |

- **Back up now** makes one straight away. **Download** saves one to your phone or computer.
- **Restore** (tap twice) first saves a safety copy (`..._pre-restore_...zip`, the newest 3 are kept), puts the Configuration tab settings back, and restarts the add-on. The data is put back as it starts, before it reads anything.
- **Restore from a file** takes a backup `.zip` you downloaded, for example to move to another Home Assistant.
- A backup from a different add-on is refused. The page only works from the Home Assistant sidebar, never on the add-on's own ports, because backups include its settings.
- Backups also hold any passwords or API keys from the Configuration tab, so treat the backup folder like your secrets.

## AI help

**✨ Preview / recap**: your Home Assistant AI Task writes a short preview before the game, a live update during it, or a recap after, from the live sensor (no made-up stats). Styles: plain, hype, trash talk or radio voice.

It uses a Home Assistant AI Task entity (`ai_task_entity` on the Configuration tab; empty uses the first one). The data shown is sent to your AI provider when you tap it.

## Score lights

On the add-on page under **Score lights**. Replaces the `sports_score_lights` AppDaemon app.

- **Group 1 / Group 2**: color lights (or light groups). Group 1 shows a team's main color, group 2 its second color; every *Swap teams every* seconds they switch to the other team.
- **Scores flash** the scoring team's colors (*Flashes per score*). *Big plays*: field goals and touchdowns in football (not a lone extra point), threes in basketball, any score in other sports. *Every score*: any change.
- **Celebrate a win**: a longer flash in your team's colors when the game ends in a win.
- **Only when this entity is in this state**: for a mode helper, for example `select.sync_lights_mode` = `Sports`. **Only on game day** leaves the lights alone when there's no game today.
- White and black team colors are swapped for bulb-friendly stand-ins (soft ice blue, deep amber) so both colors still show.

Moving from AppDaemon: remove `sports_score_lights` from `apps.yaml` (or stop AppDaemon), then turn on Score lights here with the same light groups and condition.

<!-- docs:config (generated from config.yaml) -->
## Configuration reference

Every option on the add-on's **Configuration** tab, with its default. Change them there, then restart the add-on.

| Option | Default | Type | What it does |
|---|---|---|---|
| `ai_task_entity` | *(empty)* | text, optional | **AI Task entity (optional).** The Home Assistant AI Task entity behind the ✨ AI button. Leave empty to use the first one Home Assistant has. |
| `mqtt_host` | *(empty)* | text, optional | **MQTT host (optional).** Leave empty to use the Mosquitto add-on automatically. |
| `mqtt_port` | `1883` | port | **MQTT port.** Only used with an MQTT host. Usually 1883. |
| `mqtt_username` | *(empty)* | text, optional | **MQTT username (optional).** Only used with an MQTT host. |
| `mqtt_password` | *(empty)* | secret, optional | **MQTT password (optional).** Only used with an MQTT host. |
| `publish_team_selector` | `false` | true / false | **Publish team selector.** Also create a select entity so dashboards and automations can switch the tracked team (it includes the live game). |
| `log_level` | `info` | one of: `debug`, `info`, `warning`, `error` | **Log level.** How chatty the add-on log is. Use debug when troubleshooting. |
| `backup_path` | `/share/addon_backups/team_tracker_lite` | text | **Backup folder.** Where backups are saved, inside /share, /media or /homeassistant. A folder keeps several dated backups. A path ending in .zip keeps one file that is replaced each time. Open Backups in the add-on page to back up, download or restore. |
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
