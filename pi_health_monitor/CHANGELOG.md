# Changelog

## 1.3.1 - 2026-11-17

- Uses the shared **add-on wallpaper** you pick in Photo Hub (new *Add-on wallpaper* tab). This add-on's own Wallpaper option still wins when set.

## 1.3.0 - 2026-11-16

- **Pick the web UI wallpaper.** New **Wallpaper** option on the Configuration tab. Leave it empty to use your Home Assistant theme's wallpaper, enter `none` for no wallpaper, or point it at your own image: drop it in `/config/www` and enter the file name (e.g. `wallpaper.jpg`), `/local/wallpaper.jpg`, or a full `https://` link.

## 1.2.0 - 2026-11-16

- **Follows your Home Assistant theme.** The web UI now uses the colors of whatever theme Home Assistant is showing, light or dark, and changes live when you switch. Themes with a dashboard wallpaper and frosted-glass cards (like Apple / Liquid Glass themes) carry over too: wallpaper behind, see-through blurred cards, matching corners. Opened outside Home Assistant it keeps its own look.

## [1.1.1] - 13-11-2026

- Now published as a prebuilt image (`ghcr.io/jonathangibson98/{arch}-addon-pi_health_monitor`), so it installs without building on the Pi.
- Fix: serving the stats no longer races with the background sampler, and an old error message clears once sampling works again.
- Added `DOCS.md` for the Documentation tab; `docker-compose.yml` names the prebuilt image; the standalone health check uses the exec form.

## [1.1.0] - 02-11-2026

- Run as a standalone Docker / docker compose container (per-container stats via the Docker API)
- New `PORT`, `DOCKER_HOST` and `DISK_PATH` environment variables

## [1.0.0] - 10-05-2026

### Initial Release
