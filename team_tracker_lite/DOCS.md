# Team Tracker Lite

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
