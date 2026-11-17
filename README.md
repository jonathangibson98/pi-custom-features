# pi-custom-features

Custom Home Assistant add-ons. Each folder is a self-contained add-on, and the ones marked
below can also run as a plain Docker container.

## Add-ons

| Add-on | What it does | Runs as |
|---|---|---|
| [Pi Health Monitor](pi_health_monitor/) | CPU, memory, temp, throttling and per-process-group usage dashboard | HA add-on or Docker |
| [Voice Chat](voice_chat/) | Hands-free voice conversation with any Home Assistant AI agent, answered out loud on the speaker you choose | HA add-on or Docker |
| [Personal AI Speech](personal_ai_speech/) | Natural text-to-speech with emotion tags (Kokoro) and local speech-to-text (faster-whisper), as an OpenAI-compatible server for the Personal AI integration | HA add-on |
| [Zone Creator](zone_creator/) | Search an address, drop a pin and create a Home Assistant zone, with optional AI name and icon suggestions | HA add-on |
| [Creator & AI Builder](ai_builder/) | Build automations, scenes, scripts, helpers and more from plain English with your `ai_task` entity, make AI voice announcements and dashboard facts, and back it all up | HA add-on |
| [SVG Maker](svg_maker/) | Turn photos into clean, scalable SVG icons from the sidebar, with a crop editor and color or black and white tracing | HA add-on |
| [File Reader](file_reader/) | Web UI and MQTT file manager for Home Assistant sensors, automations and text logging, with an optional REST API | HA add-on |
| [Photo Hub](photo_shuffle/) | Turn folders of photos and Unsplash collections into Home Assistant image entities over MQTT | HA add-on |
| [Release Tracker](release_tracker/) | Track anything with a release date: shows, movies, games, albums, tech launches and merch drops | HA add-on |
| [Team Tracker Lite](team_tracker_lite/) | One lightweight sports sensor, pick any team from a menu, with an optional calendar feed | HA add-on |
| [Work Hours Tracker](work_hours/) | Logs time spent in chosen zones, one file per person, with MQTT sensors | HA add-on |
| [Sleep Tracker](sleep_tracker/) | Tracks who is asleep from several signals at once (phone, Focus, lights, TV, motion), with MQTT sensors and sleep history | HA add-on |

## Install

**Settings → Add-ons → Add-on Store → ⋮ → Repositories**, add
`https://github.com/jonathangibson98/pi-custom-features`, then install the add-on you want.

Every add-on except Release Tracker and Sleep Tracker has an `image:` line in its `config.yaml`, so Home Assistant downloads a prebuilt image
from GitHub's container registry instead of building on your Pi (see [Prebuilt images](#prebuilt-images)).
Those two have no `image:` line, so Home Assistant builds them on your Pi.
Each add-on also has a **Documentation** tab with setup details (`DOCS.md` in its folder).

## Backups

Every add-on that keeps data or settings can back itself up. Creator & AI Builder and Release Tracker have their own backups. The rest share one module, [`.shared/addon_backup.py`](.shared/addon_backup.py), which adds:

- a **Backups** page in the add-on (back up now, download, restore, restore from an uploaded file)
- `backup_path`, `backup_every` and `backup_keep` options in the Configuration tab (default `/share/addon_backups/<slug>`, daily, keep 10)

### Back up all add-ons with one action

Every add-on with backups (Creator & AI Builder and Release Tracker included) listens for `backup` sent with Home Assistant's `hassio.addon_stdin` action. This script backs them all up at once. Add it under **Settings → Automations & scenes → Scripts → Create script → ⋮ → Edit in YAML**, then run it from a dashboard button or an automation:

```yaml
alias: Back up all add-ons
description: Tells each custom add-on to save a backup to the backup folder set in its Configuration tab.
icon: mdi:backup-restore
mode: single
sequence:
  - repeat:
      for_each:
        - ai_builder
        - release_tracker
        - sleep_tracker
        - work_hours
        - photo_shuffle
        - file_reader
        - voice_chat
        - team_tracker_lite
        - svg_maker
        - zone_creator
        - personal_ai_speech
      sequence:
        - action: hassio.addon_stdin
          continue_on_error: true
          data:
            addon: "e15fb2fe_{{ repeat.item }}"
            input: backup
  - action: persistent_notification.create
    data:
      title: Add-on backups
      message: Every add-on was asked to back up. Each saves to the backup folder in its Configuration tab.
```

`e15fb2fe` is this repository's prefix on your Home Assistant: open any of these add-ons and check the end of the page address (for example `.../e15fb2fe_sleep_tracker/info`). Add-ons that aren't installed or aren't running are skipped.

Each add-on builds from its own folder, so each has its own copy of the module. Edit `.shared/addon_backup.py`, then run `.shared/sync.sh` to copy it into every add-on. Pi Health Monitor keeps no data or settings, so it has no backups.

## Layout

```text
pi-custom-features/
├── .github/
│   ├── workflows/
│   │   ├── publish-ghcr.yml     (publish images to GHCR)
│   │   └── validate.yml         (lint, build and sanity checks)
│   ├── ISSUE_TEMPLATE/
│   ├── CODEOWNERS
│   ├── dependabot.yml
│   └── pull_request_template.md
├── pi_health_monitor/           add-on + standalone Docker
├── voice_chat/                  add-on + standalone Docker
├── personal_ai_speech/          add-on
├── zone_creator/                add-on
├── ai_builder/                  add-on (Creator & AI Builder)
├── svg_maker/                   add-on
├── file_reader/                 add-on
├── photo_shuffle/               add-on (Photo Hub)
├── release_tracker/             add-on
├── team_tracker_lite/           add-on
├── work_hours/                  add-on (Work Hours Tracker)
├── sleep_tracker/               add-on (Sleep Tracker)
├── .hadolint.yaml
├── .yamllint
├── repository.yaml              makes this repo addable in the HA add-on store
├── LICENSE
└── README.md
```

Every add-on folder holds at least `config.yaml`, `Dockerfile`, `DOCS.md`, `CHANGELOG.md`, `icon.png` and `logo.png`.
Add-on folders have to stay at the top level of the repo for Home Assistant to find them.

## Prebuilt images

The **Publish prebuilt images to GHCR** workflow ([`publish-ghcr.yml`](.github/workflows/publish-ghcr.yml)) runs on every
push to `main` (except Markdown-only changes), on `v*` tags and by hand from the **Actions** tab. It finds every add-on and builds:

| Image | For | Tags |
|---|---|---|
| `ghcr.io/jonathangibson98/<arch>-addon-<slug>` (`aarch64`, `amd64`) | the Home Assistant add-on | the add-on `version` and `latest` |
| `ghcr.io/jonathangibson98/pi-health-monitor` | standalone Docker | `latest`, the `version`, a short commit SHA |
| `ghcr.io/jonathangibson98/voice-chat` | standalone Docker | `latest`, the `version`, a short commit SHA |

To get Home Assistant to offer an update, bump `version` in the add-on's `config.yaml`, add a `CHANGELOG.md` entry and push.

The first time a package is published, open your GitHub profile, **Packages**, the new package, **Package settings**,
and set it to **Public**. Home Assistant (and `docker pull`) cannot use a private package.

If an image build fails with `Failed building wheel for ...`, a Python package has no prebuilt wheel for the Python version in
that add-on's `Dockerfile` (usually because the base image is a pre-release such as `python:3.15`). Pin the base image to a
released Python (for example `python:3.12-slim-bookworm`).

## Checks

The **Validate** workflow ([`validate.yml`](.github/workflows/validate.yml)) runs on every push and pull request, by hand, and nightly.
For every add-on it checks the file structure, runs the Home Assistant add-on linter, runs Hadolint on the Dockerfile
(and on `Dockerfile.standalone` where there is one) and builds the images (amd64, not pushed). It also runs yamllint and a Python
syntax check across the repo.

---

## Pi Health Monitor

Lightweight CPU, memory, temperature, throttling and per-process-group usage dashboard.
It runs in two ways from the same `app.py`:

| | Home Assistant add-on | Docker / docker compose |
|---|---|---|
| Detected by | `SUPERVISOR_TOKEN` is present | no `SUPERVISOR_TOKEN` |
| Table shows | HA Core, Supervisor, started add-ons | running Docker containers |
| Stats source | Supervisor API | Docker Engine API |
| Image built from | `pi_health_monitor/Dockerfile` | `pi_health_monitor/Dockerfile.standalone` |

### Docker compose

```bash
cd pi_health_monitor
docker compose up -d --build
```

Open `http://<host>:8099`. To use the prebuilt image instead of building, run `docker compose pull && docker compose up -d`.

Options (environment variables):

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8099` | Port the dashboard listens on inside the container |
| `DOCKER_HOST` | `unix:///var/run/docker.sock` | Docker API endpoint, also accepts `tcp://host:port` |
| `DISK_PATH` | `/` | Path inside the container used for the Disk card. Mount the host root at e.g. `/hostfs:ro` and set this to `/hostfs` to show the real host disk |

Notes:

- Host CPU, memory, load, uptime, temperature and Raspberry Pi throttling flags are read from `/proc` and `/sys`, which show the host's values inside a container. Temperature and throttling show as `n/a` on hardware that doesn't expose them.
- The dashboard has no authentication. Don't publish the port to the internet; put it behind a reverse proxy with auth or bind it to your LAN.
- Mounting `docker.sock` read-only still lets the container talk to the full Docker API. If that bothers you, use the commented `docker-socket-proxy` service in `pi_health_monitor/docker-compose.yml`, which only allows the read-only containers endpoints. If the socket isn't available, the host cards keep working and the table shows a "Docker API unavailable" message.
- Per-container CPU is shown as a share of the whole host CPU, so it's on the same scale as the CPU card.

---

## Voice Chat

Hands-free voice conversation with any Home Assistant conversation agent. Your voice is captured in the browser,
the agent you pick answers, and the reply is spoken on the speakers you pick (several at once) or in the browser itself.
It also gives the AI your household info and live entity values. Full options and troubleshooting: [voice_chat/DOCS.md](voice_chat/DOCS.md).

| | Home Assistant add-on | Docker / docker compose |
|---|---|---|
| Talks to Home Assistant with | the Supervisor token | `HA_URL` + a long-lived access token `HA_TOKEN` |
| Settings from | the Configuration tab | `VC_*` environment variables in `.env` |
| Password | optional (only for the direct HTTPS page) | always required (one is generated if you don't set it) |
| Image built from | `voice_chat/Dockerfile` | `voice_chat/Dockerfile.standalone` |

### Docker compose

```bash
cd voice_chat
cp .env.example .env        # set HA_URL, HA_TOKEN and your entity IDs
docker compose up -d --build
```

Open `https://<this-machine>:8443`, accept the certificate warning once and enter the password
(from `VC_PASSWORD`, or the generated one in `docker compose logs voice-chat` and `./data/password.txt`).
Browsers only allow the microphone on secure pages, which is why the HTTPS port is used. Plain HTTP on port 8099 only works for `http://localhost`.

---

## Personal AI Speech

An OpenAI-compatible speech server (`/v1/audio/speech`, `/v1/audio/transcriptions`) for the
[Personal AI](https://github.com/jonathangibson98/ha-personal-ai) integration: local Kokoro text-to-speech with `[happy]`
`[whisper]` `[sad]`... emotion tags, an optional proxy to OpenAI or another server, and local faster-whisper speech-to-text.
It needs a 64-bit Pi, 4 GB RAM or more recommended. First start downloads about 120 MB of voice model.
Setup: [personal_ai_speech/DOCS.md](personal_ai_speech/DOCS.md).

## Zone Creator

Create Home Assistant zones by searching an address instead of typing coordinates. Searches three free geocoders at once
(US Census, OpenStreetMap, Photon), lets you drag the pin and radius, and can ask your `ai_task` entity for a zone name and icon.
Setup: [zone_creator/DOCS.md](zone_creator/DOCS.md).

## Creator & AI Builder

Describe what you want in plain English and your `ai_task` entity builds Home Assistant automations, scenes, scripts, helpers and more.
It also makes AI voice announcements and dashboard facts, and backs everything up (default `/share/ai_builder_backups`, newest 20 kept).
It needs Home Assistant API access and an `ai_task` entity. Setup: [ai_builder/DOCS.md](ai_builder/DOCS.md).

## SVG Maker

Turn photos into clean, scalable SVG icons from the sidebar. Auto-suggested crop (circle, rounded, square or full), auto-enhance,
color or black and white tracing, and icon-friendly file names. Everything runs locally. Icons save to `/homeassistant/custom_icons` by default.
It runs on a Debian (glibc) Python image because the tracer (vtracer) crashes on Alpine. Setup: [svg_maker/DOCS.md](svg_maker/DOCS.md).

## File Reader

A web UI and MQTT file manager: expose text files as Home Assistant sensors, edit them from the sidebar and log text from automations.
Files live in `/data/files` by default, and you can point it at `/share`, `/media` or your Home Assistant config folder.
An optional REST API on port 8100 is protected by `api_token`. It needs the MQTT service. Setup: [file_reader/DOCS.md](file_reader/DOCS.md).

## Photo Hub

Turns folders of photos (default `/media`) and Unsplash collections into Home Assistant image entities over MQTT.
Images are resized (default 1920 px, JPEG quality 85) and Unsplash needs your own access key. Folders are mounted read-only.
Setup: [photo_shuffle/DOCS.md](photo_shuffle/DOCS.md).

## Release Tracker

Track anything with a release date (shows, movies, games, albums, celebrities, tech launches and merch drops) from the sidebar,
with MQTT sensors if you have the MQTT service. Setup: [release_tracker/DOCS.md](release_tracker/DOCS.md).

## Team Tracker Lite

One lightweight sports sensor where you pick any team from a menu. An optional calendar feed on port 8100 lets you subscribe
from a phone or another app. It uses MQTT if available and Home Assistant API access. Setup: [team_tracker_lite/DOCS.md](team_tracker_lite/DOCS.md).

## Work Hours Tracker

Logs the time you spend in chosen zones, one file per person (default `/homeassistant/work_hours`, kept 365 days), with MQTT sensors.
Setup: [work_hours/DOCS.md](work_hours/DOCS.md).

## Web UIs follow your Home Assistant theme

Every add-on page carries [`.shared/ha-theme.js`](.shared/ha-theme.js). Inside Home Assistant it reads the active theme (colors, light/dark, dashboard wallpaper, glass blur, card corners) and remaps the page to it, live. Outside Home Assistant it does nothing. Edit `.shared/ha-theme.js`, then run `.shared/sync.sh` (or `python3 .shared/sync_theme.py`) to copy it into every page. To add it to a new page: `python3 .shared/sync_theme.py path/to/page.html`.
