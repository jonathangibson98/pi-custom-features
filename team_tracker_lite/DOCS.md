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
