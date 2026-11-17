# Team Tracker Lite

A Home Assistant add-on that gives you **one** live sports sensor, and lets you choose which team feeds it from a menu in the sidebar. No YAML, no pile of per-team sensors eating RAM.

It pulls scores and schedules from ESPN's public API for the single team you're tracking and publishes them over MQTT. State values (`PRE`, `IN`, `POST`, `NOT_FOUND`) and attribute names (`team_abbr`, `team_score`, `opponent_logo`, ...) match the [Team Tracker integration](https://github.com/vasqued2/ha-teamtracker), so cards built for it keep working.

## Features
- One sensor (`sensor.team_tracker` by default, rename it in the panel)
- Pick a league, then a team, from dropdowns, with a search box for long lists
- Save as many teams as you like and switch the tracked one with a single tap
- Refreshes slowly when nothing is on and quickly during a game, and you set both speeds in the panel
- **Calendar:** every game this season for every saved team, as a Home Assistant calendar entity, refreshed at a time you choose
- **Live game slot:** pick a sport, pick a game that's on right now, and track its score. It never goes in the calendar
- Optional `select` entity so dashboards and automations can switch teams
- Settings survive restarts and reinstalls of the add-on image
- Log level you can turn up when something misbehaves

## Install
1. Copy the `team_tracker_lite` folder into `/addons/` on your Home Assistant.
2. Settings > Add-ons > Add-on Store > the three dots > **Check for updates**.
3. Open **Team Tracker Lite** under Local add-ons and install it.
4. On the **Configuration** tab, enter your MQTT broker (host, port, user, password). Leave `mqtt_host` blank only if you use the Mosquitto broker add-on.
5. Start it, open **Team Tracker** in the sidebar, add a team, and tap **Track**.

## Calendar
Home Assistant doesn't let an add-on create a calendar entity directly, so the add-on publishes a standard `.ics` feed of every game for your saved teams (regular season and postseason, final scores filled in for finished games) and you add it once with HA's built-in **Remote Calendar** integration.

**One-time setup**
1. Add your teams in the panel first.
2. Settings > Devices & services > Add integration > **Remote Calendar**.
3. Name it **Team Games** (that gives you `calendar.team_games`) and paste the link from the panel's Calendar section. It looks like `http://e707995f-team-tracker-lite:8100/calendar.ics`.

**How it updates**
- Every day at the time you set in the panel (default 04:00, in your Home Assistant time zone), the add-on re-downloads each saved team's schedule, rebuilds the feed, then tells Home Assistant to refresh the calendar entity. Remote Calendar only checks its link once a day on its own, so this is what makes your chosen time actually matter.
- Adding or removing a team rebuilds the calendar about 20 seconds later. Switching which team is tracked does not.
- **Update calendar now** forces it.
- If ESPN fails for any team, the old calendar is kept untouched and the add-on retries in 30 minutes.
- If you named the calendar something else, type its entity ID into **Calendar entity to refresh** in the panel.
- The calendar only ever contains your saved teams. The live game is not in it.

To subscribe from a phone or another app too, give port 8100 a host port on the add-on's **Network** tab.

## Live game
The **Live game** card in the panel is a one-off slot that sits alongside your saved teams.
1. Pick a sport. The panel lists every game in progress right now, with the score and clock.
2. Tap **Track KC** or **Track DEN** to choose which side the sensor treats as "your team".
3. The sensor switches to that game straight away and refreshes at your during-a-game speed.

When the game ends the sensor shows the final score. Pick another game or tap **Track** on a saved team whenever you like. The slot holds one game at a time. Tapping the X clears it.

## Where your settings are saved
Everything you set in the panel (saved teams, the tracked team, the live game, sensor name, refresh speeds, calendar time) is written to one file in the add-on's config folder:

```
/addon_configs/<repository id>_team_tracker_lite/data/settings.json
```

On a typical local install the folder is `/addon_configs/e707995f_team_tracker_lite/data/`. The calendar feed and its status sit beside it as `team_games.ics` and `calendar_status.json`. You can read them with the Samba share or the File editor add-on, copy it to back it up, or edit it (restart the add-on afterwards). If that folder can't be written to, the add-on logs a warning and falls back to its private `/data` folder.

## Configuration tab options
| Option | Default | What it does |
| --- | --- | --- |
| `mqtt_host` | blank | Your MQTT broker. Blank means "use the Mosquitto add-on". |
| `mqtt_port` | 1883 | Broker port. |
| `mqtt_username` / `mqtt_password` | blank | Broker login. |
| `publish_team_selector` | off | Also create a `select` entity that switches the tracked team. |
| `log_level` | info | `debug`, `info`, `warning` or `error`. |

Calendar time and refresh speeds are not here. They live in the panel.


## Logging
Open the add-on's **Log** tab.

| Level | You will see |
| --- | --- |
| `error` | Problems that stop something working (no MQTT broker, a failed poll). |
| `warning` | Things that recovered or degraded (MQTT dropped, live scoreboard fell back to schedule data). |
| `info` | Startup details, MQTT connection, teams added/removed/tracked, and state changes (PRE to IN to POST). The default. |
| `debug` | Everything above plus every ESPN request, every refresh result, the next wait time, and MQTT traffic. Noisy, so switch it back when you're done. |

## Troubleshooting
- **Build fails with "network is unreachable" for registry-1.docker.io.** The host can't reach Docker Hub, often an IPv6 problem. Retry, or disable IPv6 under Settings > System > Network.
- **The sensor never appears.** Check the footer of the panel for "Connected to MQTT". If it says not connected, fix the broker settings and restart. Set `log_level` to `debug` for details.
- **Calendar integration says it can't connect.** Open the link in a browser on the same network to check it, and make sure the add-on is running. Use the hostname shown in the panel, not `localhost`.
- **The calendar doesn't change after an update.** Check that **Calendar entity to refresh** matches the real entity ID. The add-on log says whether Home Assistant accepted the refresh.
- **Team list or scores are empty.** Set `log_level` to `debug` and look for the ESPN URL being requested and its error.
- **State is `NOT_FOUND`.** ESPN has no scheduled game for that team right now (offseason, or the schedule isn't published yet).

## Limits
Team sports only, and one live game at a time: NFL, NBA, MLB, NHL, WNBA, college football and basketball, MLS, NWSL and the major soccer leagues. Golf, tennis, racing, UFC and custom API paths are not supported.

## Credits
Inspired by [vasqued2/ha-teamtracker](https://github.com/vasqued2/ha-teamtracker) (itself a fork of zacs/ha-nfl). This add-on is a separate, much smaller implementation and uses ESPN's unofficial public API, which can change without notice.
