# ha-custom-features

## Pi Health Monitor

Lightweight CPU, memory, temperature, throttling and per-process-group usage dashboard.
It runs in two ways from the same `app.py`:

| | Home Assistant add-on | Docker / docker compose |
|---|---|---|
| Detected by | `SUPERVISOR_TOKEN` is present | no `SUPERVISOR_TOKEN` |
| Table shows | HA Core, Supervisor, started add-ons | running Docker containers |
| Stats source | Supervisor API | Docker Engine API |
| Image built from | `pi_health_monitor/Dockerfile` | `pi_health_monitor/Dockerfile.standalone` |

### Home Assistant add-on

Add this repository URL in **Settings → Add-ons → Add-on Store → Repositories**, then install *Pi Health Monitor*.

### Docker compose

```bash
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
- Mounting `docker.sock` read-only still lets the container talk to the full Docker API. If that bothers you, use the commented `docker-socket-proxy` service in `docker-compose.yml`, which only allows the read-only containers endpoints. If the socket isn't available, the host cards keep working and the table shows a "Docker API unavailable" message.
- Per-container CPU is shown as a share of the whole host CPU, so it's on the same scale as the CPU card.
