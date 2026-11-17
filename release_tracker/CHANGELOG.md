# Changelog

## 1.8.0 - 2026-11-17

- **✨ Ideas from AI** on the Add tab: suggestions for new things to track based on what you already track (or a request like "horror games"). Tap **Find** and the normal search fills in the real date. Plus **What's coming (AI rundown)** on the Tracking tab: a short, read-out-loud summary of what's next. Set `ai_task_entity` to pick which AI (empty uses the first one).
- With `ai_task_entity` empty it uses your **default AI** (picked in Personalized Info, `select.default_ai_task`), then the first AI Task.

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

- **Track anything, not just shows and games.** The Add tab now has five choices: **TV & Movies**, **Games & DLC**, **Music**, **Celebrities**, and **Anything else**.
- **Music**: follow an artist to see their next announced album, EP, or single, or track one album. Data comes from MusicBrainz, which is free and needs no key.
- **Celebrities**: follow an actor, musician, or other public figure and see their upcoming movie and TV credits. Uses your existing TMDB key.
- **Anything else**: add tech launches, merch drops, events, sales and deals, or any other date by typing it in. Each item has a kind, name, date, optional time, note, link, and picture link. Leave the date empty if it is not announced yet, and edit it later from the card.
- The Tracking tab is now grouped by kind (TV & Movies, Games & DLC, Music, Celebrities, Tech releases, Merch drops, Events, Sales & deals, Other) with filter buttons at the top.
- Settings has a new **Music & custom items** card. Celebrities share the **Movies, TV & Celebrities** card with your TMDB key.
- The release sensor now has `by_type`, a count of upcoming releases for each kind. Each item in `items` also has `time` and `note`, and `type` can be any of the new kinds.
- Backups and restores include all the new kinds.

## 1.4.0

- **One sensor for everything**: `sensor.release_tracker_releases`. Shows, movies, games, and DLC are all in it.
- The state is the number of releases inside your window. `items`, `next_*`, `today`, `today_count`, and `by_person` are attributes.
- Removed the separate next release, upcoming, releasing today, upcoming games, and all per-person sensors. They are deleted from Home Assistant automatically on startup. **Automations and dashboard cards that used them need to point at the new sensor.** See the examples in the docs.

## 1.3.0

- **Games can be tagged to people** now, just like shows and movies. Pick who is tracking a game when you add it, or tap a name on its card.
- New per-person games sensor: `sensor.release_tracker_<name>_upcoming_games`. The main games sensor has a `by_person` attribute.
- New **People** card in Settings. Add one person at a time, rename them (their tags follow), or remove them (their tags and sensors go too).
- **Settings are organized into cards**: People, Movies & TV, Games, Updates, Home Assistant (MQTT), and Backup. Each has its own Save button and a status badge.
- New **Backup** card. Save your list, tags, and settings into a folder you choose in the share folder, on demand or daily or weekly. Restore from any saved backup. API keys are left out unless you turn them on.
- Saving one settings card no longer refreshes everything or reconnects MQTT unless it needs to.

## 1.2.0

- Added **video games and DLC**. Pick the **Games & DLC** switch on the Add tab and search by name.
- Track a game and its DLC and expansions show up automatically under it. Track a DLC directly if you only care about that.
- Games get **one** sensor: `sensor.release_tracker_upcoming_games`. No per-person game sensors, and games never touch the TV and movie sensors.
- Games data comes from IGDB (free). You need a free Twitch Client ID and Secret in Settings.
- Dates that are only a month or a year show as "expected" instead of a fake exact date.

## 1.1.0

- Added **people**. Tag each show or movie with who cares about it (you, Sam, anybody you add in Settings).
- Every person gets their own sensors: `sensor.release_tracker_<name>_upcoming` and `binary_sensor.release_tracker_<name>_releasing_today`.
- The main "Releasing Today" sensor now has a `by_person` attribute.
- Tap a name on any tracked card to change who it belongs to.
- Added icon, logo, and documentation.

## 1.0.0

- First release.
- Search TMDB and track any TV show or movie.
- TV: next episode or season premiere. Movies: theater, digital, and physical dates for your region.
- Publishes sensors to Home Assistant over MQTT with auto-discovery.
- Sidebar page for adding, removing, and refreshing.
