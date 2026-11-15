# Changelog

## 1.2.0 - 2026-11-15

- **Backups.** New options `backup_enabled`, `backup_path` (default `/share/svg_maker_backups`), `backup_keep` (default 20) and `backup_interval_hours` (default 24). The add-on saves every SVG in your save folder (`svg_output_path`) to a zip a minute after it starts and then on that schedule. No new file is made when nothing changed. The temp folder is not backed up.
- **Restore.** Put a backup's file name in the new `restore_backup` option and restart. A safety copy of the current save folder is made first, and the option clears itself afterwards. Files that are not in the backup are left alone.
- Each zip also holds `options_reference.json`, a copy of your settings with the Home Assistant token hidden.

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
