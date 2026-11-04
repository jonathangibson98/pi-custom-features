# ha-custom-features

Custom Home Assistant add-ons. Each folder is a self-contained add-on that can also run
as a plain Docker container where noted.

## Layout

```
ha-custom-features/
├── repository.yaml          # makes this repo addable in the HA add-on store
├── README.md
├── LICENSE
├── pi_health_monitor/       # add-on + standalone docker compose
│   ├── config.yaml          # HA add-on definition
│   ├── Dockerfile           # add-on image
│   ├── Dockerfile.standalone
│   ├── docker-compose.yml
│   ├── app.py, run.sh
│   └── icon.png, logo.png, CHANGELOG.md
└── sillytavern/             # add-on
    ├── config.yaml
    ├── Dockerfile
    ├── run.sh
    ├── DOCS.md, README.md, CHANGELOG.md
    └── icon.png, logo.png
```

Add-on folders have to stay at the top level of the repo for Home Assistant to find them.

## Add-ons

| Add-on | What it does | Runs as |
|---|---|---|
| [Pi Health Monitor](pi_health_monitor/) | CPU, memory, temp, throttling and per-process-group usage dashboard | HA add-on or Docker |
| [SillyTavern](sillytavern/) | LLM chat frontend built from the official release branch | HA add-on |

## Install

**Settings → Add-ons → Add-on Store → ⋮ → Repositories**, add
`https://github.com/jonathangibson98/ha-custom-features`, then install the add-on you want.

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

Open `http://<host>:8099`.

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

## SillyTavern

SillyTavern 1.19.0, built from the official `release` branch when the add-on is installed.

1. Install the add-on and set `admin_password` on the **Configuration** tab.
2. Start it and open `http://<HA-IP>:8000`, log in as `default-user`.

Chats, characters, extensions and `config.yaml` persist in the add-on config folder
(`/addon_configs/<id>_sillytavern/`). Full details in [sillytavern/DOCS.md](sillytavern/DOCS.md).
