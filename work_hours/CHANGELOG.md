# Changelog

All notable changes to this add-on are documented here.

## 1.5.0

- **Backups.** New options `backup_enabled`, `backup_path` (default `/share/work_hours_backups`), `backup_keep` (default 20) and `backup_interval_hours` (default 24). The add-on saves your hours files (the CSV for each person) and your settings (people, zones and pay periods) to a zip a minute after it starts and then on that schedule. No new file is made when nothing changed.
- **Restore.** Put a backup's file name in the new `restore_backup` option and restart. A safety copy of the current files is saved first, and the option clears itself afterwards. Files that are not in the backup are left alone.
- Each zip also holds `options_reference.json`, a copy of your add-on options with the MQTT password hidden.

## 1.4.0

- Pay period is now set per person instead of one setting for everybody, so people on different pay schedules each get their own totals, resets and history
- The pay period fields moved into each person's Edit section
- A newly added person starts with the previous person's pay period to save typing
- Settings from 1.3.0 are migrated automatically: everyone gets a copy of the old shared pay period

## 1.3.0

- Pay period settings (start day, length, anchor date, history size) moved from the add-on options to the sidebar page, and apply as soon as you press Save
- People are now added one at a time from a drop-down instead of showing every person in a long list, with a short card for each person you track
- Zones are added to each person from a drop-down and shown as removable chips
- Settings from 1.2.0 are migrated automatically, including a pay period that was set in the options

## 1.2.0

- MQTT device "Work Hours Tracker" appears in Home Assistant automatically, with an hours sensor and an at-work sensor for each person
- Pick the pay period: start day (for example Thursday) and length in weeks
- The sensor state is the hours worked in the current pay period and resets when the next one starts
- Sensor attributes keep the history of totals for finished pay periods, even after old CSV rows are cleaned up
- The sidebar page now shows the pay period total next to today and this week
- Optional MQTT broker settings for people not using the Mosquitto add-on

## 1.1.0

- Each person now has their own list of work zones, so different people can be tracked at different locations
- Each person's file is named after them (from their person entity's name), for example `Jonathan_Gibson.csv`
- Settings from 1.0.0 are migrated automatically: everyone keeps their existing file and zones

## 1.0.0

- First release
- Sidebar page to pick which people and zones to track
- One CSV file per person
- Configurable save folder and data retention
- Grace period and minimum visit length
- Shifts crossing midnight are split into daily rows
