# Changelog

## 0.4.0
- **Backups.** New options `backup_enabled`, `backup_path` (default `/share/team_tracker_lite_backups`), `backup_keep` (default 20) and `backup_interval_hours` (default 24). Your saved teams and settings are saved to a zip a minute after the add-on starts and then on that schedule. No new file is made when nothing changed.
- **Restore.** Put a backup's file name in the new `restore_backup` option and restart. A safety copy of the current settings is saved first, and the option clears itself afterwards.
- Each zip also holds `options_reference.json`, a copy of your settings with the MQTT password hidden.
- The `share` folder is now mounted so backups can be saved there.

## 0.3.2
- Real fix: the live game's select state was published as "FSU vs CLEM (NCAAF)" instead of "Live game: FSU vs CLEM (NCAAF)", so Home Assistant rejected it and the dropdown snapped back.
- Fix: picking a live game could snap the Home Assistant team dropdown back to the previously tracked team. The add-on now re-sends the dropdown's current choice a couple of seconds after any change, and on every refresh.

## 0.3.0
- Calendar: every game for every saved team as an `.ics` feed on port 8100, for Home Assistant's Remote Calendar integration. Rebuilt daily at a time you choose, rebuilt when you add or remove a team, with an "Update now" button. Refreshes the HA calendar entity after each rebuild.
- Live game slot: pick a sport, pick a game in progress, track its score. Not included in the calendar.
- The select entity (if enabled) now includes the live game.
- Needs `homeassistant_api` access (to refresh the calendar entity and read your time zone).

## 0.2.0
- Settings now saved in the add-on config folder (`addon_configs/.../data/settings.json`).
- Refresh speeds (idle and live) moved from the Configuration tab into the panel.
- New `log_level` option (debug, info, warning, error) and much more useful logging.
- Added icon, logo, README and docs.

## 0.1.0
- First version: one MQTT sensor, team menus in the panel, saved teams, optional team selector entity.
