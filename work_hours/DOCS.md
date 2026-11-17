# Work Hours Tracker

## Setup

1. Install and start the add-on.
2. Turn on **Show in sidebar** (Info tab).
3. Open **Work Hours** in the sidebar.
4. Under **People**, pick a person from the drop-down and press **Add person**.
5. In their card, add their **work zones** from the zone drop-down and set their
   **pay period** (see below).
6. Press **Save**.

Only the people you add are shown, so there's no long list to scroll through.
Press **Edit** on a person to change their zones or pay period, or **Remove**
to stop tracking them. A new person starts with the same pay period as the last
person you added, since people often share one. Change it if theirs is different.

Every person has their own zone list, so one person can work at Site A while
someone else works at Site B and Site C. Someone standing in a zone that isn't
added for them is not logged.

## Options

| Option | Default | What it does |
| --- | --- | --- |
| `save_folder` | `/homeassistant/work_hours` | Where the files are saved. Must start with `/homeassistant/`, `/share/` or `/media/`. Created automatically. |
| `keep_days` | `365` | CSV rows older than this are deleted. `0` keeps everything forever. |
| `check_seconds` | `30` | How often locations are checked. |
| `grace_minutes` | `10` | How long someone can be outside the zone before the shift ends. |
| `min_minutes` | `5` | Visits shorter than this are ignored. |
| `mqtt_host`, `mqtt_port`, `mqtt_username`, `mqtt_password` | empty | Only if you do **not** use the Mosquitto add-on. |

Changing options requires restarting the add-on. Everything on the sidebar
page (people, zones and pay periods) takes effect as soon as you press Save.

## Pay periods

Every person has their **own** pay period, so people on different pay schedules
each get the right totals. Set it in the **Edit** section of their card.

The person's sensor shows the hours worked **in their current pay period**, then
starts again at zero when their next period begins (at midnight on the start day).

| Starts on | Length | Period |
| --- | --- | --- |
| Thursday | 1 week | Thursday to the next Wednesday, then resets on Thursday |
| Thursday | 2 weeks | Thursday to Wednesday two weeks later, then resets |
| Monday | 1 week | Monday to Sunday |

- **A pay period started on** only matters for periods of 2 weeks or more. It
  tells the add-on which weeks are paired together. Pick any date one of that
  person's pay periods began, for example `2026-10-29`. It is moved back to the
  start day automatically if it falls on a different weekday.
- **Periods of history to keep** is how many finished pay periods that person's
  sensor remembers in its `history` attribute.

If you change someone's period later, their finished periods stay in the history
exactly as they were recorded, and the new schedule applies from now on. Other
people are not affected.

## MQTT device

If MQTT is available, the add-on creates one device called **Work Hours
Tracker** in Home Assistant. No YAML needed, it appears on its own. For each
tracked person it adds:

- **`<Name> hours`**: a sensor whose state is the hours worked in the current pay period
- **`<Name> at work`**: on while the person is clocked in

The hours sensor has these attributes:

| Attribute | Meaning |
| --- | --- |
| `period_label`, `period_start`, `period_end` | The current pay period |
| `days_left` | Days left in the period, counting today |
| `today_hours`, `week_hours` | Hours today and this Monday-to-Sunday week |
| `last_period_hours` | Total for the previous pay period |
| `clocked_in`, `current_zone`, `clocked_in_since` | Live status |
| `history` | Totals for finished pay periods, newest first: `start`, `end`, `hours` |

The history keeps going even after old CSV rows are cleaned up by `keep_days`.
Periods with zero hours are left out.

The add-on uses the Mosquitto broker add-on automatically. If you use a
different broker, fill in the `mqtt_` options. If MQTT isn't available the
add-on still tracks hours and writes files, and tries MQTT again every 5 minutes.

Removing a person from the sidebar page removes their sensors.

## Files

Each person gets a CSV named after them. The name comes from the person
entity's name the first time they are saved, with spaces turned into
underscores, for example `Alex Smith` becomes `Alex_Smith.csv`:

```
date,zone,start,end,hours
2026-11-02,Work Site A,06:52,15:41,8.82
```

- A row is written when a visit **ends**. The sidebar page and the sensor
  include the current visit live, but it isn't in the file until the person leaves.
- The end time is when the person actually left, not when the grace period ran out.
- A visit that crosses midnight becomes two rows. The first ends at `24:00`.
- Lunch or errands shorter than the grace period do not split the shift.

Once a person's file name is set it never changes, even if you rename the
person in Home Assistant, so their history stays in one file. If two people
end up with the same name, the second gets `_2` on the end.

The files open in Excel, Numbers and Google Sheets.

## Cleanup

Every 6 hours (and at start-up) rows older than `keep_days` are removed. Before
that happens the add-on saves the totals of every pay period those rows
belong to, so the sensor history is not lost. Only CSV files with this add-on's
header are touched; other files in the folder are left alone.

## How it decides someone is "at work"

The add-on reads each person entity's state. If it matches the name of one of
the zones ticked for that person, the person is in that zone. If the person's
state is `unavailable` or `unknown`, nothing changes until a real state returns.

## Tips

- Make each zone at least **150 m** in radius, otherwise GPS drift will bounce
  people in and out.
- In the Companion app set Location permission to **Always** and turn on
  **Precise Location**.
- Compare the hours to a real timesheet for a couple of weeks before relying
  on them for pay.
- The sensor's entity ID is built from the device and person name, for example
  `sensor.work_hours_tracker_jonathan_gibson_hours`. You can rename it in HA.

## Troubleshooting

- **No people or zones listed:** check the Log tab for "Can't reach Home Assistant".
- **The person I want isn't in the drop-down:** only people already added are
  hidden from it. Check the person exists under Settings → People in Home Assistant.
- **No MQTT device:** install and start the Mosquitto broker add-on and the MQTT
  integration, then restart this add-on. The bottom of the sidebar page shows
  the MQTT status.
- **Nothing is being saved:** the save folder must start with `/homeassistant/`,
  `/share/` or `/media/`. Anything else isn't mounted into the add-on.
- **Visits missing:** they may be shorter than `min_minutes`.

## Backups

Tap **Backups** at the bottom of the add-on page to back up, download or restore. A backup is a `.zip` with your people, zones and pay periods, open sessions and history, plus the hours CSV files in your save folder, plus everything in the Configuration tab.

| Option | Default | What |
|---|---|---|
| `backup_path` | `/share/addon_backups/work_hours` | Where backups go, inside `/share`, `/media` or `/homeassistant`. A folder keeps several dated backups. A path ending in `.zip` keeps one file that is replaced each time |
| `backup_every` | `daily` | `off`, `daily` or `weekly` automatic backups |
| `backup_keep` | `10` | How many backups to keep in the folder. Older ones are deleted |

- **Back up now** makes one straight away. **Download** saves one to your phone or computer.
- **Restore** (tap twice) first saves a safety copy (`..._pre-restore_...zip`, the newest 3 are kept), puts the Configuration tab settings back, and restarts the add-on. The data is put back as it starts, before it reads anything.
- **Restore from a file** takes a backup `.zip` you downloaded, for example to move to another Home Assistant.
- A backup from a different add-on is refused. The page only works from the Home Assistant sidebar, never on the add-on's own ports, because backups include its settings.
- Backups also hold any passwords or API keys from the Configuration tab, so treat the backup folder like your secrets.

## AI help

**✨ Ask about the hours**: each person's card has a question box ("how much overtime this month?", "when do I usually leave?"). Leave it empty for a quick summary. Answered by your Home Assistant AI Task from the logged hours.

It uses a Home Assistant AI Task entity (`ai_task_entity` on the Configuration tab; empty uses the first one). The data shown is sent to your AI provider when you tap it.
