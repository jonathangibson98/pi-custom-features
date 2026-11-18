#!/usr/bin/env python3
"""Regenerate the repository README.md (catalog and feature lists come from each config.yaml and meta.py)."""
import os
import sys
from urllib.parse import quote

import yaml

sys.path.insert(0, os.path.dirname(__file__))
from meta import CATEGORY, META, ORDER, RAW, REPO  # noqa: E402

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GH = "https://github.com/" + REPO
ADD_REPO = "https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=" + quote(GH, safe="")
BACKUP_SLUGS = ["ai_builder", "release_tracker", "sleep_tracker", "work_hours", "photo_shuffle", "voice_chat",
                "team_tracker_lite", "svg_maker", "zone_creator", "personal_ai_speech"]


def cfg(slug):
    return yaml.safe_load(open(os.path.join(ROOT, slug, "config.yaml")))


def ver_badge(slug):
    u = quote(RAW + "/" + slug + "/config.yaml", safe="")
    return "![version](https://img.shields.io/badge/dynamic/yaml?url=%s&query=%%24.version&label=&color=41BDF5)" % u


def yes(b, text="✅"):
    return text if b else "—"


def main():
    C = {s: cfg(s) for s in ORDER}
    n = len(ORDER)
    out = []
    w = out.append
    w('<div align="center">')
    w("")
    w("# 🏠 Pi Custom Features")
    w("")
    w("**%d Home Assistant add-ons for building, partying, tracking and talking to your home, all with pages that match your theme.**" % n)
    w("")
    w("[![Validate](%s/actions/workflows/validate.yml/badge.svg?branch=main)](%s/actions/workflows/validate.yml)" % (GH, GH))
    w("[![Publish images](%s/actions/workflows/publish-ghcr.yml/badge.svg?branch=main)](%s/actions/workflows/publish-ghcr.yml)" % (GH, GH))
    w("[![License: MIT](https://img.shields.io/github/license/%s?color=blue)](LICENSE)" % REPO)
    w("![Add-ons](https://img.shields.io/badge/add--ons-%d-41BDF5?logo=homeassistant&logoColor=white)" % n)
    w("![Architectures](https://img.shields.io/badge/arch-aarch64%20%7C%20amd64-informational)")
    w("[![Images on GHCR](https://img.shields.io/badge/images-GHCR-2ea44f?logo=docker&logoColor=white)](https://github.com/%s?tab=packages)" % REPO.split("/")[0])
    w("[![Last commit](https://img.shields.io/github/last-commit/%s?logo=github)](%s/commits/main)" % (REPO, GH))
    w("[![Issues](https://img.shields.io/github/issues/%s?logo=github)](%s/issues)" % (REPO, GH))
    w("![Python](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)")
    w("")
    w("[![Add this repository to your Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](%s)" % ADD_REPO)
    w("")
    w("</div>")
    w("")
    w("---")
    w("")
    w("## Contents")
    w("")
    for t in ["Add-ons", "Install", "What each add-on needs", "Features in every add-on", "Back up every add-on at once",
              "Run without Home Assistant", "Troubleshooting", "Development", "License"]:
        w("- [%s](#%s)" % (t, t.lower().replace(" ", "-")))
    w("")
    w("## Add-ons")
    w("")
    cats = []
    for s in ORDER:
        if CATEGORY[s] not in cats:
            cats.append(CATEGORY[s])
    for cat in cats:
        w("### %s" % cat)
        w("")
        w("| | Add-on | Version | What it does |")
        w("|:---:|---|:---:|---|")
        for s in [x for x in ORDER if CATEGORY[x] == cat]:
            c = C[s]
            tag = META[s]["tagline"].replace("|", "\\|")
            w('| <img src="%s/icon.png" width="44" alt=""> | **[%s](%s/)**<br><sub>[docs](%s/DOCS.md) · [changelog](%s/CHANGELOG.md)</sub> | %s | %s |'
              % (s, c["name"], s, s, s, ver_badge(s), tag))
        w("")
    w("<details>")
    w("<summary><b>Feature lists for every add-on</b> (tap to open)</summary>")
    w("")
    for s in ORDER:
        w("#### %s" % C[s]["name"])
        w("")
        for f in META[s]["features"]:
            w("- " + f)
        w("")
    w("</details>")
    w("")
    w("## Install")
    w("")
    w("1. Click **Add this repository** above, or in Home Assistant go to **Settings → Add-ons → Add-on Store → ⋮ → Repositories** and add:")
    w("")
    w("   ```text")
    w("   " + GH)
    w("   ```")
    w("")
    w("2. Refresh the store (**⋮ → Check for updates**). The add-ons show up under **HA Custom Features**.")
    w("3. Open one, click **Install**, look over its **Configuration** tab, then **Start**. Turn on **Show in sidebar** to open its page from the sidebar.")
    w("4. Every add-on has a **Documentation** tab (its `DOCS.md`) with setup steps, examples and every option.")
    w("")
    w("> [!NOTE]")
    w("> Add-ons need Home Assistant OS or a Supervised install. Most download a prebuilt image from GitHub's container registry, so "
      "installs and updates are quick even on a Raspberry Pi. Release Tracker and Sleep Tracker build on your device the first time.")
    w("")
    w("## What each add-on needs")
    w("")
    w("| Add-on | MQTT | AI Task | Extra port | Prebuilt image | Also runs in Docker |")
    w("|---|:---:|:---:|:---:|:---:|:---:|")
    for s in ORDER:
        c = C[s]
        sv = c.get("services") or []
        mq = "required" if "mqtt:need" in sv else "optional" if "mqtt:want" in sv else "—"
        ai = "✨" if ("ai_task_entity" in (c.get("options") or {}) or s in ("ai_builder", "photo_shuffle")) else "—"
        ports = ", ".join(str(p).split("/")[0] for p in (c.get("ports") or {})) or "—"
        w("| [%s](%s/) | %s | %s | %s | %s | %s |" % (c["name"], s, mq, ai, ports, yes(c.get("image")), yes(META[s].get("docker"))))
    w("")
    w("- **MQTT**: the [Mosquitto broker](https://github.com/home-assistant/addons/tree/master/mosquitto) add-on is found automatically. "
      "Using your own broker? Fill in the `mqtt_*` options. \"Optional\" add-ons still work without it but don't make entities.")
    w("- **AI Task** ✨: any integration that offers an `ai_task` entity (Google Gemini, OpenAI, Anthropic, Ollama, Personal AI…). "
      "AI buttons use the add-on's `ai_task_entity` option; if that's empty they use the household default AI "
      "(`select.default_ai_task`, set in the Personalized Info add-on), then the first AI Task found.")
    w("")
    w("## Features in every add-on")
    w("")
    w("**Pages that match your theme.** Every page reads your active Home Assistant theme (colors, light or dark mode, wallpaper, glass blur, "
      "card corners) and follows it live. Over a wallpaper it checks how bright the picture is and tints behind text just enough to keep it readable. "
      "Outside Home Assistant the pages keep their own look.")
    w("")
    w("**One wallpaper for all of them.** Pick it in **Photo Hub → Wallpaper** (upload, choose a photo, or follow a shuffle or Unsplash collection). "
      "Each add-on's own `wallpaper` option wins over that: empty uses your theme's wallpaper, `none` turns it off, or give an image in "
      "`/config/www` (`pic.jpg` or `/local/pic.jpg`) or an `https://` link.")
    w("")
    w("**Backups built in.** Every add-on that keeps data has a **Backups** page (back up now, download, restore, restore from a file) and "
      "`backup_path`, `backup_every` and `backup_keep` options (default `/share/addon_backups/<slug>`, daily, keep 10). "
      "Creator & AI Builder and Release Tracker have their own backup pages. Backups include the Configuration tab, so keep the folder private.")
    w("")
    w("**Commands from automations.** Most add-ons take commands sent with Home Assistant's `hassio.addon_stdin` action, for example "
      "`backup` (every add-on with backups) or `disco`, `off`, `party on` and `game trivia on` (Party Lights).")
    w("")
    w("## Back up every add-on at once")
    w("")
    w("Every add-on with backups listens for `backup` on `hassio.addon_stdin`. Add this script under **Settings → Automations & scenes → Scripts → "
      "Create script → ⋮ → Edit in YAML**, then run it from a dashboard button or an automation:")
    w("")
    w("```yaml")
    w("alias: Back up all add-ons")
    w("description: Tells each custom add-on to save a backup to the folder set on its Configuration tab.")
    w("icon: mdi:backup-restore")
    w("mode: single")
    w("sequence:")
    w("  - repeat:")
    w("      for_each:")
    for s in BACKUP_SLUGS:
        w("        - " + s)
    w("      sequence:")
    w("        - action: hassio.addon_stdin")
    w("          continue_on_error: true")
    w("          data:")
    w('            addon: "e15fb2fe_{{ repeat.item }}"')
    w("            input: backup")
    w("  - action: persistent_notification.create")
    w("    data:")
    w("      title: Add-on backups")
    w("      message: Every add-on was asked to back up. Each saves to the backup folder on its Configuration tab.")
    w("```")
    w("")
    w("`e15fb2fe` is the prefix Home Assistant gives this repository. To check yours, open any of these add-ons and look at the end of the page "
      "address (for example `.../e15fb2fe_sleep_tracker/info`). Add-ons that aren't installed or running are skipped.")
    w("")
    w("## Run without Home Assistant")
    w("")
    w("Two add-ons also run as a plain Docker container from the same code.")
    w("")
    w("### Pi Health Monitor")
    w("")
    w("| | Home Assistant add-on | Docker / docker compose |")
    w("|---|---|---|")
    w("| Detected by | `SUPERVISOR_TOKEN` is present | no `SUPERVISOR_TOKEN` |")
    w("| Table shows | HA Core, Supervisor, started add-ons | running Docker containers |")
    w("| Stats from | the Supervisor API | the Docker Engine API |")
    w("| Built from | `pi_health_monitor/Dockerfile` | `pi_health_monitor/Dockerfile.standalone` |")
    w("")
    w("```bash")
    w("cd pi_health_monitor")
    w("docker compose up -d --build      # or: docker compose pull && docker compose up -d")
    w("```")
    w("")
    w("Open `http://<host>:8099`.")
    w("")
    w("| Variable | Default | Purpose |")
    w("|---|---|---|")
    w("| `PORT` | `8099` | Port the dashboard listens on inside the container |")
    w("| `DOCKER_HOST` | `unix:///var/run/docker.sock` | Docker API endpoint, also `tcp://host:port` |")
    w("| `DISK_PATH` | `/` | Path used for the Disk card. Mount the host root at `/hostfs:ro` and set this to `/hostfs` to show the real host disk |")
    w("")
    w("> [!WARNING]")
    w("> The standalone dashboard has no login. Keep the port on your LAN or put it behind a reverse proxy with authentication. "
      "Mounting `docker.sock` read-only still allows the full Docker API; the commented `docker-socket-proxy` service in "
      "`pi_health_monitor/docker-compose.yml` limits it to read-only container endpoints.")
    w("")
    w("Host CPU, memory, load, uptime, temperature and Raspberry Pi throttling come from `/proc` and `/sys`, so they show the host's values. "
      "Per-container CPU is a share of the whole host, on the same scale as the CPU card.")
    w("")
    w("### Voice Chat")
    w("")
    w("| | Home Assistant add-on | Docker / docker compose |")
    w("|---|---|---|")
    w("| Talks to Home Assistant with | the Supervisor token | `HA_URL` + a long-lived access token `HA_TOKEN` |")
    w("| Settings from | the Configuration tab | `VC_*` variables in `.env` |")
    w("| Password | optional (only for the direct HTTPS page) | always required (generated if you don't set one) |")
    w("| Built from | `voice_chat/Dockerfile` | `voice_chat/Dockerfile.standalone` |")
    w("")
    w("```bash")
    w("cd voice_chat")
    w("cp .env.example .env        # set HA_URL, HA_TOKEN and your entity IDs")
    w("docker compose up -d --build")
    w("```")
    w("")
    w("Open `https://<this-machine>:8443`, accept the certificate warning once and enter the password (from `VC_PASSWORD`, or the generated one in "
      "`docker compose logs voice-chat` and `./data/password.txt`). Browsers only allow the microphone on secure pages, which is why it uses HTTPS.")
    w("")
    w("## Troubleshooting")
    w("")
    w("| Problem | Fix |")
    w("|---|---|")
    w("| The add-ons don't show in the store | **⋮ → Check for updates** in the Add-on Store, then refresh the page. Check the repository URL has no trailing slash or `.git`. |")
    w("| Install fails with `pull access denied` or `manifest unknown` | The image for that version is still building (a few minutes after a release) or its package isn't public yet. Try again shortly. |")
    w("| An update isn't offered | Home Assistant checks the store a few times a day. **⋮ → Check for updates** forces it. |")
    w("| No MQTT entities | Install and start the Mosquitto broker add-on and the MQTT integration, or fill in the add-on's `mqtt_*` options. Then restart the add-on. |")
    w("| ✨ AI buttons say no AI is set up | Add an AI integration with an AI Task entity, or set `ai_task_entity` on the add-on's Configuration tab. |")
    w("| A page is blank or says \"ingress only\" | Open it from the sidebar or **Open Web UI**. Pages that change your setup only work through Home Assistant. |")
    w("| Something else | Check the add-on's **Log** tab, then [open an issue](%s/issues) with the add-on version and the log. |" % GH)
    w("")
    w("## Development")
    w("")
    w("```text")
    w("pi-custom-features/")
    w("├── .github/")
    w("│   ├── workflows/")
    w("│   │   ├── validate.yml        lint, build and sanity checks on every push and pull request")
    w("│   │   └── publish-ghcr.yml    builds and publishes the prebuilt images")
    w("│   ├── docsgen/                regenerates the READMEs and the generated parts of DOCS.md")
    w("│   └── dependabot.yml")
    w("├── .shared/                    code every add-on carries a copy of")
    w("│   ├── ha-theme.js             theme and wallpaper bridge for the pages")
    w("│   ├── ha_ai.py                AI Task helper (picks the default AI)")
    w("│   ├── addon_backup.py         the Backups page and scheduled backups")
    w("│   ├── sync.sh                 copies the shared files into every add-on")
    w("│   └── sync_theme.py           injects ha-theme.js into every page")
    for s in sorted(ORDER):
        extra = " + standalone Docker" if META[s].get("docker") else ""
        w("├── %-27s %s%s" % (s + "/", C[s]["name"], extra))
    w("├── repository.yaml             makes this repo addable in the Add-on Store")
    w("├── LICENSE")
    w("└── README.md")
    w("```")
    w("")
    w("Every add-on folder has at least `config.yaml`, `Dockerfile`, `DOCS.md`, `README.md`, `CHANGELOG.md`, `icon.png` and `logo.png`, and "
      "`translations/en.yaml` for the option names. Add-on folders have to stay at the top level for Home Assistant to find them.")
    w("")
    w("### Shared code")
    w("")
    w("Each add-on builds from its own folder, so each carries its own copy of the shared files. Edit the file in `.shared/`, then run "
      "`.shared/sync.sh` from the repository root to copy it everywhere. To add the theme bridge to a new page: "
      "`python3 .shared/sync_theme.py path/to/page.html`.")
    w("")
    w("### Docs")
    w("")
    w("`python3 .github/docsgen/gen.py` rewrites every add-on's `README.md` and the generated blocks of its `DOCS.md` (header, configuration "
      "reference, footer) from `config.yaml`, `translations/en.yaml` and `.github/docsgen/meta.py`. `python3 .github/docsgen/root.py` rewrites this README. "
      "Edit the hand-written parts of `DOCS.md` outside the `<!-- docs:... -->` markers.")
    w("")
    w("### Releasing")
    w("")
    w("1. Make the change, bump `version` in the add-on's `config.yaml` and add a `CHANGELOG.md` entry.")
    w("2. Run the docs generators if options or features changed.")
    w("3. Push to `main` (or merge a pull request). **Validate** checks the structure, runs the Home Assistant add-on linter, Hadolint, "
      "yamllint and a Python syntax check, and builds every image. **Publish images** then pushes:")
    w("")
    w("| Image | For | Tags |")
    w("|---|---|---|")
    w("| `ghcr.io/%s/<arch>-addon-<slug>` (`aarch64`, `amd64`) | the add-on | the add-on version, `latest` |" % REPO.split("/")[0])
    w("| `ghcr.io/%s/pi-health-monitor` | standalone Docker | `latest`, the version, a short commit SHA |" % REPO.split("/")[0])
    w("| `ghcr.io/%s/voice-chat` | standalone Docker | `latest`, the version, a short commit SHA |" % REPO.split("/")[0])
    w("")
    w("A new package is private on GHCR at first: open it under your GitHub profile's **Packages**, then **Package settings**, and make it **Public** "
      "so Home Assistant can pull it. If a build fails with `Failed building wheel for ...`, pin the Dockerfile's base image to a released Python "
      "(for example `python:3.12-slim-bookworm`).")
    w("")
    w("## License")
    w("")
    w("[MIT](LICENSE). Not affiliated with or endorsed by Home Assistant or Nabu Casa.")
    w("")
    open(os.path.join(ROOT, "README.md"), "w", encoding="utf-8").write("\n".join(out))
    print("README.md written")


if __name__ == "__main__":
    main()
