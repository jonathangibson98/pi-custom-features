# Changelog

## [1.1.1] - 13-11-2026

- Now published as a prebuilt image (`ghcr.io/jonathangibson98/{arch}-addon-pi_health_monitor`), so it installs without building on the Pi.
- Fix: serving the stats no longer races with the background sampler, and an old error message clears once sampling works again.
- Added `DOCS.md` for the Documentation tab; `docker-compose.yml` names the prebuilt image; the standalone health check uses the exec form.

## [1.1.0] - 02-11-2026

- Run as a standalone Docker / docker compose container (per-container stats via the Docker API)
- New `PORT`, `DOCKER_HOST` and `DISK_PATH` environment variables

## [1.0.0] - 10-05-2026

### Initial Release
