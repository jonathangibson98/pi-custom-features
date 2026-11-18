<img src="icon.png" alt="" width="96" align="right">

# Creator & AI Builder

![Version](https://img.shields.io/badge/dynamic/yaml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fjonathangibson98%2Fpi-custom-features%2Fmain%2Fai_builder%2Fconfig.yaml&query=%24.version&label=version&color=41BDF5&logo=homeassistant) ![Architectures](https://img.shields.io/badge/arch-aarch64%20%7C%20amd64-informational) ![Sidebar](https://img.shields.io/badge/sidebar-ingress-success) ![Prebuilt image](https://img.shields.io/badge/image-GHCR-2ea44f?logo=docker) ![MQTT](https://img.shields.io/badge/MQTT-optional-660066?logo=mqtt) ![AI Task](https://img.shields.io/badge/AI-ai__task-8A2BE2?logo=googlegemini)

Describe what you want in plain English and your Home Assistant AI builds it: automations, scripts, scenes, helpers, template sensors, dashboards and cards. Also voice announcements, dashboard facts, text-file sensors and backups.

## Features

- **Build**: automations, scripts, scenes, helpers, template sensors, blueprints and more from a plain-English request, checked before anything is saved
- **Dashboards**: open any dashboard, ask for changes and see a live preview drawn with your real cards and theme at your screen's exact size (cast TV, Nest Hub, tablet, phone, or **My screens** read from Browser Mod sensors)
- **Does it fit?** measures the real page and **Make it fit** sends the overflow to the AI. Every save keeps the version before it
- **Cards**: make and edit single cards with a preview
- **Voice & facts**: AI announcements on a schedule or a dashboard switch, and rotating facts saved to sensors
- **Files** (formerly File Reader): text files as sensors over MQTT, updated from automations or the REST API
- **Backup**: one-click and scheduled backups of everything the add-on made

## What you need

- Home Assistant OS or Supervised (add-ons need the Supervisor)
- An `ai_task` entity (any AI integration that offers AI Task)
- MQTT (optional, for Files sensors)

## Install

[![Add this repository to your Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fjonathangibson98%2Fpi-custom-features)

1. Click the button above, or go to **Settings → Add-ons → Add-on Store → ⋮ → Repositories** and add `https://github.com/jonathangibson98/pi-custom-features`.
2. Find **Creator & AI Builder** in the store and click **Install**.
3. Check the **Configuration** tab, then **Start**. Turn on **Show in sidebar** to open it from the sidebar.

## Documentation

- [Full documentation](DOCS.md), also on the add-on's **Documentation** tab
- [Changelog](CHANGELOG.md)
- [All add-ons in this repository](../README.md)
