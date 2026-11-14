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

## Install

**Settings → Add-ons → Add-on Store → ⋮ → Repositories**, add
`https://github.com/jonathangibson98/pi-custom-features`, then install the add-on you want.

Every add-on has an `image:` line in its `config.yaml`, so Home Assistant downloads a prebuilt image
from GitHub's container registry instead of building on your Pi (see [Prebuilt images](#prebuilt-images)).
Each add-on also has a **Documentation** tab with setup details (`DOCS.md` in its folder).

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
│   ├── config.yaml, Dockerfile, run.sh, app.py
│   ├── Dockerfile.standalone, docker-compose.yml
│   └── DOCS.md, CHANGELOG.md, icon.png, logo.png
├── voice_chat/                  add-on + standalone Docker
│   ├── config.yaml, build.yaml, Dockerfile, run.sh, app/
│   ├── Dockerfile.standalone, docker-compose.yml, .env.example
│   └── DOCS.md, CHANGELOG.md, translations/, icon.png, logo.png
├── personal_ai_speech/          add-on
│   ├── config.yaml, Dockerfile, requirements.txt, app/
│   └── README.md, DOCS.md, CHANGELOG.md, translations/, icon.png, logo.png
├── zone_creator/                add-on
│   ├── config.yaml, Dockerfile, server.py, index.html
│   └── README.md, DOCS.md, CHANGELOG.md, translations/, icon.png, logo.png
├── .hadolint.yaml
├── .yamllint
├── repository.yaml              makes this repo addable in the HA add-on store
├── LICENSE
└── README.md
```

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
