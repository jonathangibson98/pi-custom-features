# Pi Health Monitor

Lightweight dashboard for the health of the machine Home Assistant runs on.

## What it shows

- **CPU** use, core count and clock speed, **temperature** (°C and °F), **memory**, **disk**, **load average** and **uptime**.
- **Throttling / power:** Raspberry Pi under-voltage, frequency capping, throttling and soft temperature limit, both right now and since boot. Shows "Not exposed on this hardware" where the board doesn't report it.
- A table of **Home Assistant Core, the Supervisor and every started add-on**, sorted by CPU, with RAM and RAM %.

The page refreshes every 5 seconds.

## Use

1. Install and start the add-on.
2. Turn on **Show in sidebar** and open **Pi Health**.

There are no options to configure.

## Permissions

The add-on uses the Supervisor API with the `manager` role to read system and add-on statistics. It only reads; it never changes anything.

## Running without Home Assistant

The same `app.py` also runs as a plain Docker container and shows your Docker containers instead of add-ons. See the repository README for the `docker compose` setup and its environment variables (`PORT`, `DOCKER_HOST`, `DISK_PATH`).
