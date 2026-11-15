# Changelog

## 1.1.0 - 2026-11-15

- **Backups.** New **Backups** page (link at the bottom of the add-on page) to back up now, download, restore, or restore from an uploaded file. Backups go to `backup_path` (a folder, or one `.zip` file) automatically on the `backup_every` schedule, and the newest `backup_keep` are kept
- A backup holds your people, their signals and settings, the current sleep state and the sleep history, plus the Configuration tab settings. Restoring saves a safety copy first, puts the settings back and restarts the add-on to put the data back
- The add-on now has Supervisor access (`hassio_api`, to restore its settings and restart itself) and `/share` access for the backup folder

## 1.0.0 - 2026-11-15

- First release. Track any `person`: weighted signals with a sleep confidence score, fall-asleep and wake levels, settle and
  wake times, must-be-true signals that wake instantly, night hours, optional naps and home-only tracking
- Signals suggested from the person's Companion app sensors (charging, Focus, activity, Android sleep confidence and screen)
  and a bedroom area's lights, TVs and motion sensors
- Bedtime is dated back to when the signals first agreed. Short wake-ups are interruptions of the same night
- MQTT entities: asleep, sleep status, confidence, last sleep (with history and a 7-night average), mark asleep / awake buttons,
  and Everyone asleep
- Web UI with live signals, recent nights, manual marking and deleting wrong nights
