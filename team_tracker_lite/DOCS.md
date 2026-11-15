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
- `backup_enabled`, `backup_path`, `backup_keep`, `backup_interval_hours`, `restore_backup`: see [Backup and restore](#backup-and-restore).

Refresh speeds and the calendar time are set in the panel, not here.

## Backup and restore

The add-on saves your teams and settings to a zip file so you can recover them after a reinstall or a failed SD card.

| Option | Default | What it does |
|---|---|---|
| `backup_enabled` | `true` | Turns automatic backups on or off. |
| `backup_path` | `/share/team_tracker_lite_backups` | Folder for the zip files. Use a folder inside `/share`. |
| `backup_keep` | `20` | How many backups to keep. The oldest are deleted. |
| `backup_interval_hours` | `24` | Hours between backups. `0` backs up only when the add-on starts. |
| `restore_backup` | empty | File name of a backup to restore (see below). |

A backup is made about a minute after the add-on starts and then every `backup_interval_hours`. If nothing changed since the last backup, no new file is made.

A backup holds everything in the add-on's data folder (your saved teams, tracked team, refresh speeds and calendar time). Each zip also has `options_reference.json`, a copy of your settings with the MQTT password replaced by `***`. It is for reading only and is never restored.

**To restore:**

1. Open your backup folder (Samba or the File editor) and copy the name of the zip, for example `team_tracker_lite-20261115-021500.zip`. The add-on log also lists the newest backups each time it starts.
2. Paste that name into `restore_backup` on the Configuration tab and save.
3. Restart the add-on.

The add-on first saves a safety copy of the current settings (named `team_tracker_lite-prerestore-...zip`), puts the backed up files back before it starts, and clears `restore_backup` itself. If the option does not clear, empty it by hand so the restore is not repeated.

## Not supported
Golf, tennis, racing, UFC and custom API paths. Team sports only.
