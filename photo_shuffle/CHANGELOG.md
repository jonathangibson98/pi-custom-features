# Changelog

## 5.1.0 - 2026-11-23

- **New Analyze tab.** Upload one photo or a whole batch from your phone, and Photo Hub saves each one to a destination you pick and (optionally) has an AI describe it: a caption, the scene, the objects, how many people there are and what they're doing (described, never named), readable text and search tags. Each photo is **renamed after what's in it** (`dog-on-couch.jpg`) and the results are listed, searchable, under **Recent**.
- **Pick the AI.** A dropdown lists every AI Task entity that can look at photos (Gemini, OpenAI, Anthropic ...), so you can switch or compare. If the AI fails the photo is still saved.
- **Destinations you can tap.** Add named shortcuts to any folder Photo Hub can see, browse to it, make new folders from the picker, and edit or remove shortcuts later.
- **iPhone HEIC photos** are accepted and saved as JPEG. Other formats are saved exactly as sent, and nothing is ever overwritten.
- **Wider file access.** Photo Hub can now also see `/backup`, `/addons`, `/addon_configs` (all read and write) and `/ssl` (read only), on top of `/media`, `/share` and `/homeassistant`. **Restart Photo Hub once after updating** so Home Assistant applies this.
- New dependency: `pillow-heif` (HEIC support).

## 5.0.2 - 2026-11-17

- **Better on phones** (built around the Home Assistant iPhone app): text fields no longer make iOS zoom in, buttons and switches are finger-sized, rows of tabs swipe sideways instead of getting cut off, and wide content or long error text no longer pushes the page sideways.
- The tab row (Folders, Unsplash, Wallpaper, Photo Editor, SVG Maker) swipes sideways on phones, so SVG Maker isn't cut off.

## 5.0.1 - 2026-11-17

- SVG Maker and the Photo Editor's AI use your **default AI** (picked in Personalized Info, `select.default_ai_task`) when `svg_ai_task_entity` points at an AI Task you don't have, so the AI works out of the box.

## 5.0.0 - 2026-11-17

- **SVG Maker is now part of Photo Hub.** It has its own **SVG Maker** tab with everything the stand-alone add-on had: photo-to-SVG tracing with the crop editor, and AI logos (with or without a reference photo). Its options (`svg_*`, `ha_url`, `ha_token`) moved to Photo Hub's Configuration tab with the same names and defaults, so copy over anything you'd changed. The old SVG Maker add-on still works but won't get new features.
- **New Photo Editor tab.** Open any photo (upload, your photo folders, the current wallpaper, a shuffle's current photo, an Unsplash photo, or an SVG from SVG Maker) and:
  - **Adjust**: brightness, contrast, saturation, warmth, tint, shadows, highlights, fade, vintage, sharpen, blur, vignette and grain. Double-tap a slider to zero it.
  - **Filters**: Vivid, Warm, Cool, Golden, Mono, Noir, Vintage, Faded, Dramatic, Dreamy and Wallpaper, with live previews.
  - **Crop**: free, original, square, 16:9, 9:16 (phone), 4:3 and 3:2; rotate, flip and resize.
  - **AI**: describe a change ("make it golden hour", "remove the people in the back") or tap a preset (enhance, remove background, sky swap, watercolor, cartoon, restore an old photo, phone wallpaper). Uses your Home Assistant AI Task entities that can make images (Google Gemini or OpenAI). **AI auto-adjust** looks at the photo and sets the sliders for you.
  - Undo / redo, and hold **Before** to compare with the original.
  - **Save** to the edits folder (or any of your photo folders), **Download**, **Set as add-on wallpaper**, or send it to SVG Maker to trace or to use for an AI logo.
- **Wallpaper look.** The wallpaper tab has **Lighten / Darken**, **Blur**, **Saturation**, **Contrast** and **Warmth** sliders plus presets (Soft dark, Very dark, Soft light, Frosted, Mono). The look is kept every time the wallpaper changes and is always made from the untouched picture, so changes never stack up. **More edits in the Photo Editor** opens it for anything else.
- Add-on pages get an automatic tint behind their text when the wallpaper is bright, so text stays readable.
- New options: `edit_output_path` (default `/media/photo_hub/edited`, added to your photo paths automatically), `photo_ai_image_entity` and `photo_ai_data_entity` (both optional; empty picks one for you).
- Photo Hub now has **read and write** access to `/media` (the Photo Editor saves there) and Home Assistant API access (for the AI tools). Restart it once after updating.
- Runs on a Debian Python image now (SVG Maker's tracer doesn't work on Alpine).

## 4.4.1 - 2026-11-17

- **Fixed:** picking an Unsplash collection for the add-on wallpaper failed ("Exception on /api/wallpaper"), and the 4.4.0 change could also stop Unsplash photos from refreshing. The wallpaper code reused a name the Unsplash code already used for its refresh timer.

## 4.4.0 - 2026-11-17

- **New "Add-on wallpaper" tab.** Pick one wallpaper for every add-on's page: upload a picture, pick one from your photo folders, or follow a folder shuffle or Unsplash collection so it changes with every new photo. Turn it off to go back to your theme's wallpaper. Each add-on's own Wallpaper option still wins when set.
- Needs write access to Home Assistant's `www` folder (it saves the wallpaper to `/config/www/addon-wallpaper/`). Restart Photo Hub once after updating.

## 4.3.0 - 2026-11-16

- **Pick the web UI wallpaper.** New **Wallpaper** option on the Configuration tab. Leave it empty to use your Home Assistant theme's wallpaper, enter `none` for no wallpaper, or point it at your own image: drop it in `/config/www` and enter the file name (e.g. `wallpaper.jpg`), `/local/wallpaper.jpg`, or a full `https://` link.

## 4.2.0 - 2026-11-16

- **Follows your Home Assistant theme.** The web UI now uses the colors of whatever theme Home Assistant is showing, light or dark, and changes live when you switch. Themes with a dashboard wallpaper and frosted-glass cards (like Apple / Liquid Glass themes) carry over too: wallpaper behind, see-through blurred cards, matching corners. Opened outside Home Assistant it keeps its own look.

## 4.1.1

- **Back up from Home Assistant.** The add-on now listens on stdin, so the `hassio.addon_stdin` action with `input: backup` makes a backup right away. One script can back up every add-on at once (see the repository README, "Back up all add-ons with one action")

## 4.1.0

- **Backups.** New **Backups** page (link at the bottom of the add-on page) to back up now, download, restore, or restore from an uploaded file. Backups go to `backup_path` (a folder, or one `.zip` file) automatically on the `backup_every` schedule, and the newest `backup_keep` are kept
- A backup holds your shuffles and Unsplash collections (thumbnails are left out, they're rebuilt by themselves), plus the Configuration tab settings. Restoring saves a safety copy first, puts the settings back and restarts the add-on to put the data back
- The add-on now has Supervisor access (`hassio_api`, to restore its settings and restart itself) and `/share` access for the backup folder

## 4.0.3

- Fix: Photo Hub could lose its MQTT connection and never get it back, leaving every image entity unavailable until the add-on was restarted by hand. It now watches its own connection and, if it is down for more than a minute or stops answering, throws the connection away and rebuilds it with freshly fetched broker settings (this also covers a changed Mosquitto login).
- An error while announcing entities can no longer kill the MQTT network loop.
- Each connection uses a unique client id, so two copies of the add-on can no longer kick each other off the broker.
- Photos are no longer downloaded from Unsplash while MQTT is down (that wasted your hourly request limit). They are fetched again as soon as MQTT is back.
- A folder shuffle photo that could not be delivered is retried within 10 seconds instead of waiting a full interval.

## 4.0.2

- Now published as a prebuilt image (`ghcr.io/jonathangibson98/{arch}-addon-photo_shuffle`), so it installs without building on the Pi.
- The add-on page link now points at this repository.

## 4.0.1
- Fix: the image build failed for armv7. The Home Assistant base image no longer supports armv7, so Photo Hub now supports aarch64 and amd64 only.

## 2.0.0
- Photo Shuffle and Photo Puller merged into one add-on, Photo Hub
- Folder shuffles and Unsplash collections both publish over MQTT
- Single web UI with live previews and an activity log
