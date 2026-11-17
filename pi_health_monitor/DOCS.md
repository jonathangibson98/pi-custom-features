# Pi Health Monitor

Lightweight dashboard for the health of the machine Home Assistant runs on.

## What it shows

- **CPU** use, core count and clock speed, **temperature** (°C and °F), **memory**, **disk**, **load average** and **uptime**.
- **Throttling / power:** Raspberry Pi under-voltage, frequency capping, throttling and soft temperature limit, both right now and since boot. Shows "Not exposed on this hardware" where the board doesn't report it.
- A table of **Home Assistant Core, the Supervisor and every started add-on**, sorted by CPU, with RAM and RAM %.

The page refreshes every 5 seconds.

## Health checks

A score out of 100 and a list of checks, worst first, each with what to do. They run every 10 minutes in the background (**Check again** runs them now):

- **Home Assistant health**: anything in Repairs, and whether the Supervisor calls the system unhealthy or unsupported.
- **Updates** waiting for Core, OS, Supervisor and add-ons, and **how old your newest backup is**.
- **Storage**: how full the disk is, SD card / eMMC wear when the card reports it, and a small write test (a dying SD card often turns read only).
- **Temperature, power and load**: hot CPU, under-voltage or throttling, memory or CPU running out.
- **Entities** that are unavailable (the full list is under *More detail*).
- **Log**: errors and warnings in `home-assistant.log` since the last restart, and which integrations cause most of them.
- **Network**: how fast the internet and DNS answer.
- **Database** size.

**Ask AI what to fix** sends the report to your Home Assistant AI Task and shows a short, ordered fix list. Set `ai_task_entity`, or leave it empty to use the first AI Task entity.

## Database

Shows which entities fill Home Assistant's recorder database (the default SQLite `home-assistant_v2.db`): rows, share of all rows and about how much space each takes, plus the busiest statistics and events and how many days of history it keeps. Under the table is a ready-to-paste `recorder: exclude:` block for the worst offenders. Excluded entities stop showing in history graphs, so only exclude what you don't need history for.

The scan only reads the database, runs twice a day (turn off with `database_scan`) or with **Scan now**, and gives up after 2 minutes so it never bogs the Pi down. MariaDB / PostgreSQL databases aren't scanned.

## Last 24 hours

Small charts of CPU, temperature and memory, one point a minute, kept in memory (they start over when the add-on restarts).

## Use

1. Install and start the add-on.
2. Turn on **Show in sidebar** and open **Pi Health**.

Options: `database_scan` (scan the database twice a day, default on), `ai_task_entity` (AI for fix tips, optional) and `wallpaper`.

## Permissions

The add-on uses the Supervisor API with the `manager` role to read system and add-on statistics, updates, backups and repairs, and the Home Assistant API to list entities and ask the AI Task. It reads the config folder for the log and the database. The only thing it changes is the optional junk cleanup.

## Running without Home Assistant

The same `app.py` also runs as a plain Docker container and shows your Docker containers instead of add-ons. See the repository README for the `docker compose` setup and its environment variables (`PORT`, `DOCKER_HOST`, `DISK_PATH`).

## Junk cleanup

**Clean now** clears what piles up on a Pi: the Docker build cache from add-ons built on it, old add-on images left after updates, and Alexa voice clips (`/config/www/alexa_tts`) older than 30 days. It shows what it freed.

- For the Docker part, turn off **Protection mode** on this add-on's Info tab (Home Assistant only gives Docker access then).
- Run it monthly with an automation:

```yaml
triggers:
  - trigger: time
    at: "04:30:00"
conditions:
  - condition: template
    value_template: "{{ now().day == 1 }}"
actions:
  - action: hassio.addon_stdin
    data:
      addon: <your Pi Health Monitor add-on slug>
      input: cleanup
  - action: tts.clear_cache
```
