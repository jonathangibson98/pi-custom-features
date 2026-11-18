<img src="icon.png" alt="" width="96" align="right">

# Pi Health Monitor

![Version](https://img.shields.io/badge/dynamic/yaml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fjonathangibson98%2Fpi-custom-features%2Fmain%2Fpi_health_monitor%2Fconfig.yaml&query=%24.version&label=version&color=41BDF5&logo=homeassistant) ![Architectures](https://img.shields.io/badge/arch-aarch64%20%7C%20amd64-informational) ![Sidebar](https://img.shields.io/badge/sidebar-ingress-success) ![Prebuilt image](https://img.shields.io/badge/image-GHCR-2ea44f?logo=docker) ![AI Task](https://img.shields.io/badge/AI-ai__task-8A2BE2?logo=googlegemini) ![Docker](https://img.shields.io/badge/also%20runs%20in-Docker-2496ED?logo=docker)

A lightweight health check for the machine Home Assistant runs on, with plain-English fixes.

## Features

- CPU, temperature, memory, disk, load and uptime, refreshed every 5 seconds
- Raspberry Pi under-voltage and throttling, now and since boot
- Per add-on CPU and RAM (or per container when run in Docker)
- Health checks: storage wear, updates, backups, repairs, log errors and unavailable entities
- **Database**: which entities fill your recorder database the most
- AI fix tips through your `ai_task` entity
- Runs as an add-on or as a plain Docker container

## What you need

- Home Assistant OS or Supervised (add-ons need the Supervisor)
- Nothing extra
- An `ai_task` entity (optional, for fix tips)

## Install

[![Add this repository to your Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fjonathangibson98%2Fpi-custom-features)

1. Click the button above, or go to **Settings → Add-ons → Add-on Store → ⋮ → Repositories** and add `https://github.com/jonathangibson98/pi-custom-features`.
2. Find **Pi Health Monitor** in the store and click **Install**.
3. Check the **Configuration** tab, then **Start**. Turn on **Show in sidebar** to open it from the sidebar.

It also runs without Home Assistant as a plain Docker container: see **Running without Home Assistant** in the docs.

## Documentation

- [Full documentation](DOCS.md), also on the add-on's **Documentation** tab
- [Changelog](CHANGELOG.md)
- [All add-ons in this repository](../README.md)
