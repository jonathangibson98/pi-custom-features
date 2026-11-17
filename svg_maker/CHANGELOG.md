# Changelog

## 1.6.0 - 2026-11-17

- **SVG Maker now lives inside Photo Hub** as its own tab, next to a new Photo Editor and the shared add-on wallpaper. Everything it does is there, and pictures move between them with one tap (edit a photo, then trace it; turn an SVG back into a picture). Install or update Photo Hub 5.0.0 and copy any SVG settings you changed over to its Configuration tab. This stand-alone add-on keeps working but won't get new features.
- **Easier to read over wallpapers.** When the page shows a wallpaper (your theme's, the shared one from Photo Hub, or your own), it now checks how bright the picture is and lays down just enough of a tint for the text to stay readable: bright wallpapers get more, dark ones barely any. Text also gets a soft shadow.

## 1.5.1 - 2026-11-17

- Uses the shared **add-on wallpaper** you pick in Photo Hub (new *Add-on wallpaper* tab). This add-on's own Wallpaper option still wins when set.

## 1.5.0 - 2026-11-16

- **Pick the web UI wallpaper.** New **Wallpaper** option on the Configuration tab. Leave it empty to use your Home Assistant theme's wallpaper, enter `none` for no wallpaper, or point it at your own image: drop it in `/config/www` and enter the file name (e.g. `wallpaper.jpg`), `/local/wallpaper.jpg`, or a full `https://` link.

## 1.4.0 - 2026-11-16

- **Follows your Home Assistant theme.** The web UI now uses the colors of whatever theme Home Assistant is showing, light or dark, and changes live when you switch. Themes with a dashboard wallpaper and frosted-glass cards (like Apple / Liquid Glass themes) carry over too: wallpaper behind, see-through blurred cards, matching corners. Opened outside Home Assistant it keeps its own look.

## 1.3.2

- Removed personal names, places and home-specific entity IDs from the defaults, examples and docs, so new installs start clean.

## 1.3.1 - 2026-11-15

- **Back up from Home Assistant.** The add-on now listens on stdin, so the `hassio.addon_stdin` action with `input: backup` makes a backup right away. One script can back up every add-on at once (see the repository README, "Back up all add-ons with one action")

## 1.3.0 - 2026-11-15

- **Backups.** New **Backups** page (link at the bottom of the add-on page) to back up now, download, restore, or restore from an uploaded file. Backups go to `backup_path` (a folder, or one `.zip` file) automatically on the `backup_every` schedule, and the newest `backup_keep` are kept
- A backup holds the icons in your save folder (svg_output_path), plus the Configuration tab settings. Restoring saves a safety copy first, puts the settings back and restarts the add-on to put the data back
- The add-on now has Supervisor access (`hassio_api`, to restore its settings and restart itself) and `/share` access for the backup folder

## 1.2.1 - 2026-11-15

- Fixed **"Unknown source directory"** when drawing from a photo. The add-on assumed Home Assistant's media folder is called `local`, but a `media_dirs` setting in `configuration.yaml` replaces it with your own names. It now asks Home Assistant which media folder holds its photos. If none of your media folders point at `/media`, the message says what to add

## 1.2.0 - 2026-11-15

- **AI logo can work from a photo.** Add a photo under **Base it on a photo** and your AI Task looks at it while drawing. Choose **Turn it into a logo**, **Stay close to the photo** or **Just inspiration**. The description becomes optional
- The photo's main colors are shown, and **Use its colors** fills in the color box
- **Update logo** keeps sending the same photo, so changes stay true to it
- Photos are shrunk to 1024 px, saved in `/media/svg_maker/ai_photos/` (where Home Assistant reads AI attachments from) and deleted after a day. A clear message explains what to check if your AI Task can't read images

## 1.1.0 - 2026-11-14

- New **AI logo** tab. Describe the logo you want, pick a style, colors and shape, and your `ai_task` entity draws it as a real SVG. Draw 1 to 3 ideas at once, pick the best, then type a change ("make it rounder, use green") and update it.
- Results use the same name, Save locally, Download and Both buttons as photo conversions, and auto-save to the temp folder.
- AI output is cleaned before you see it: scripts, external links, bitmaps and animation are removed, gradient ids are made unique and the size is normalized. Black and white logos use `currentColor` so Home Assistant can recolor them.
- New options: `svg_ai_task_entity`, `svg_ai_timeout`, `svg_ai_default_style`, `svg_ai_default_count`, plus optional `ha_url` and `ha_token`. The add-on now has Home Assistant API access (`homeassistant_api`).
- Photo conversion is unchanged.

## 1.0.3 - 2026-11-14

- Fixed the image build failing with "Failed building wheel for vtracer". The base image is now pinned to Python 3.12 (a released version with prebuilt tracer wheels) instead of the 3.15 pre-release, and the build only accepts a prebuilt tracer wheel so it can't fall into a Rust compile.
- The add-on page link now really points at this repository.

## 1.0.1 - 2026-11-13

- Now published as a prebuilt image (`ghcr.io/jonathangibson98/{arch}-addon-svg_maker`), so it installs without building on the Pi.
- The add-on page link now points at this repository.

## 1.0.0 - 2026-11-05

SVG Maker is now its own add-on, split out of Creator & AI Builder, where it failed to convert photos.

- Runs on a Debian (glibc) base instead of Alpine, which fixes the tracer crash ("killed by signal 11") seen in the combined add-on
- Tracer gets a larger stack and, if it still crashes, the conversion is retried automatically at smaller sizes before an error is shown
- The install build runs a tracer test, and the add-on logs a tracer self-test at every start
- Same crop editor, auto-crop, auto-enhance, color / black and white tracing, naming, Save locally / Download / Both, and the same `svg_*` options and defaults as before
