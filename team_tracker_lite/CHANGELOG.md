# Changelog

## 0.8.0 - 2026-11-17

- **Score lights** (replaces the `sports_score_lights` AppDaemon app): two groups of color lights show the teams' colors and swap every 30 seconds (adjustable). When someone scores they flash that team's colors: field goals and touchdowns in football (not the extra point on its own), threes in basketball, any score in other sports, or every score if you prefer. Celebrates when your team wins. Optional "only when" helper (for example a mode select set to Sports), only on game day, brightness, **Test flash**. Remembers the score across restarts so nothing is missed.
- Team colors are now filled in from ESPN's team page when the schedule leaves them out, so `team_colors` and `opponent_colors` aren't empty (Party Lights' team colors theme uses them too).

## 0.7.1 - 2026-11-17

- With `ai_task_entity` empty, the AI uses your **default AI**, picked at the top of Personalized Info (`select.default_ai_task`), then the first AI Task.

## 0.7.0 - 2026-11-17

- **✨ Preview / recap**: your Home Assistant AI Task writes a short preview before the game, a live update during it, or a recap after, from the live sensor (no made-up stats). Styles: plain, hype, trash talk or radio voice. Set `ai_task_entity` to pick which AI (empty uses the first one).

## 0.6.2 - 2026-11-17

- **Easier to read over wallpapers.** When the page shows a wallpaper (your theme's, the shared one from Photo Hub, or your own), it now checks how bright the picture is and lays down just enough of a tint for the text to stay readable: bright wallpapers get more, dark ones barely any. Text also gets a soft shadow.

## 0.6.1 - 2026-11-17

- Uses the shared **add-on wallpaper** you pick in Photo Hub (new *Add-on wallpaper* tab). This add-on's own Wallpaper option still wins when set.

## 0.6.0 - 2026-11-16

- **Pick the web UI wallpaper.** New **Wallpaper** option on the Configuration tab. Leave it empty to use your Home Assistant theme's wallpaper, enter `none` for no wallpaper, or point it at your own image: drop it in `/config/www` and enter the file name (e.g. `wallpaper.jpg`), `/local/wallpaper.jpg`, or a full `https://` link.

## 0.5.0 - 2026-11-16

- **Follows your Home Assistant theme.** The web UI now uses the colors of whatever theme Home Assistant is showing, light or dark, and changes live when you switch. Themes with a dashboard wallpaper and frosted-glass cards (like Apple / Liquid Glass themes) carry over too: wallpaper behind, see-through blurred cards, matching corners. Opened outside Home Assistant it keeps its own look.

## 0.4.1

- **Back up from Home Assistant.** The add-on now listens on stdin, so the `hassio.addon_stdin` action with `input: backup` makes a backup right away. One script can back up every add-on at once (see the repository README, "Back up all add-ons with one action")

## 0.4.0

- **Backups.** New **Backups** page (link at the bottom of the add-on page) to back up now, download, restore, or restore from an uploaded file. Backups go to `backup_path` (a folder, or one `.zip` file) automatically on the `backup_every` schedule, and the newest `backup_keep` are kept
- A backup holds your saved teams, the tracked team and the calendar settings, plus the Configuration tab settings. Restoring saves a safety copy first, puts the settings back and restarts the add-on to put the data back
- The add-on now has Supervisor access (`hassio_api`, to restore its settings and restart itself) and `/share` access for the backup folder

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
