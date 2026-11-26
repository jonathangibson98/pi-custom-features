# Changelog

## 1.12.0 - 2026-11-26

- **Add common US holidays in one tap.** In **Days off**, the new **Add common US holidays** button fills the list with New Year's Day, Martin Luther King Jr. Day, Presidents' Day, Memorial Day, Juneteenth, Independence Day, Labor Day, Columbus Day, Veterans Day, Thanksgiving, the day after Thanksgiving, Christmas Eve, Christmas Day and New Year's Eve. Fixed-date ones repeat every year; the "third Monday" kind are added for this year and the next two with the right dates. Holidays already in the list are skipped. Remove the ones your job does not give you, then Save. (Holidays that land on a weekend are not moved to the nearest weekday: edit the date if yours is.)

## 1.11.0 - 2026-11-26

- **Build your work schedule in the add-on.** A new **Work schedule** section: for each person, tick the days you work and set the start and end time (an end earlier than the start is a night shift). **Copy Monday to Tue to Fri** fills a normal week.
- **The Work Hours Summary sensor knows the schedule.** Each person in `people` now has `schedule_text` (for example "Mon to Fri 6:30 AM to 5:00 PM; Sat, Sun off"), `schedule`, `working_today`, `scheduled_today`, `next_shift`, `next_7_days` (work, off or day off with the reason), `scheduled_hours_this_week`, `scheduled_hours_so_far_this_week`, `scheduled_hours_left_this_week`, `hours_vs_schedule_this_week` and `scheduled_hours_this_period`. Days off cancel that day's shift. The summary's `text` mentions the schedule and the next shift too.

## 1.10.0 - 2026-11-26

- **One entity with everything: `sensor.work_hours_summary`** (needs MQTT). Its state is how many people are clocked in. All the statistics are in its attributes, so you only need to point a dashboard card, automation or AI at this one entity: `people` has an entry per person (today, this week, this pay period, last period, days left, overtime over 40 h, days worked and average per day, the last 30 days, longest day, typical start and end time, last worked date, clocked in and where, days off today and next, the previous pay periods), plus `clocked_in_now`, `off_today`, `total_hours_today`, `total_hours_this_week`, and `text`: one plain sentence per person that an AI can read as is.

## 1.9.0 - 2026-11-26

- **Days off.** A new **Days off** section: add holidays, vacation (a first and last day) and sick days, mark ones that repeat every year, and choose who each applies to (empty = everybody). Optionally also count all-day events from a Home Assistant calendar (timed events are ignored).
- **A "day off" sensor for each person** (`binary_sensor.<name>_day_off`, needs MQTT): on during a day off, with attributes `reason`, `next_date`, `next_name`, `days_until_next` and `upcoming` (consecutive days are one entry). The hours sensor also gets `day_off_today` and `next_day_off`. Use it as a condition in automations (skip the "you're late" alert on holidays) or hand it to an AI Task.
- **"Ask about the hours" knows your days off,** so a missing day in the log is not mistaken for a skipped shift.

## 1.8.2 - 2026-11-17

- **Better on phones** (built around the Home Assistant iPhone app): text fields no longer make iOS zoom in, buttons and switches are finger-sized, rows of tabs swipe sideways instead of getting cut off, and wide content or long error text no longer pushes the page sideways.

## 1.8.1 - 2026-11-17

- With `ai_task_entity` empty, the AI uses your **default AI**, picked at the top of Personalized Info (`select.default_ai_task`), then the first AI Task.

All notable changes to this add-on are documented here.

## 1.8.0 - 2026-11-17

- **✨ Ask about the hours**: each person's card has a question box ("how much overtime this month?", "when do I usually leave?"). Leave it empty for a quick summary. Answered by your Home Assistant AI Task from the logged hours. Set `ai_task_entity` to pick which AI (empty uses the first one).

## 1.7.2 - 2026-11-17

- **Easier to read over wallpapers.** When the page shows a wallpaper (your theme's, the shared one from Photo Hub, or your own), it now checks how bright the picture is and lays down just enough of a tint for the text to stay readable: bright wallpapers get more, dark ones barely any. Text also gets a soft shadow.

## 1.7.1 - 2026-11-17

- Uses the shared **add-on wallpaper** you pick in Photo Hub (new *Add-on wallpaper* tab). This add-on's own Wallpaper option still wins when set.

## 1.7.0 - 2026-11-16

- **Pick the web UI wallpaper.** New **Wallpaper** option on the Configuration tab. Leave it empty to use your Home Assistant theme's wallpaper, enter `none` for no wallpaper, or point it at your own image: drop it in `/config/www` and enter the file name (e.g. `wallpaper.jpg`), `/local/wallpaper.jpg`, or a full `https://` link.

## 1.6.0 - 2026-11-16

- **Follows your Home Assistant theme.** The web UI now uses the colors of whatever theme Home Assistant is showing, light or dark, and changes live when you switch. Themes with a dashboard wallpaper and frosted-glass cards (like Apple / Liquid Glass themes) carry over too: wallpaper behind, see-through blurred cards, matching corners. Opened outside Home Assistant it keeps its own look.

## 1.5.2

- Removed personal names, places and home-specific entity IDs from the defaults, examples and docs, so new installs start clean.

## 1.5.1

- **Back up from Home Assistant.** The add-on now listens on stdin, so the `hassio.addon_stdin` action with `input: backup` makes a backup right away. One script can back up every add-on at once (see the repository README, "Back up all add-ons with one action")

## 1.5.0

- **Backups.** New **Backups** page (link at the bottom of the add-on page) to back up now, download, restore, or restore from an uploaded file. Backups go to `backup_path` (a folder, or one `.zip` file) automatically on the `backup_every` schedule, and the newest `backup_keep` are kept
- A backup holds your people, zones and pay periods, open sessions and history, plus the hours CSV files in your save folder, plus the Configuration tab settings. Restoring saves a safety copy first, puts the settings back and restarts the add-on to put the data back
- The add-on now has Supervisor access (`hassio_api`, to restore its settings and restart itself) and `/share` access for the backup folder

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
- Each person's file is named after them (from their person entity's name), for example `Alex_Smith.csv`
- Settings from 1.0.0 are migrated automatically: everyone keeps their existing file and zones

## 1.0.0

- First release
- Sidebar page to pick which people and zones to track
- One CSV file per person
- Configurable save folder and data retention
- Grace period and minimum visit length
- Shifts crossing midnight are split into daily rows
