<img src="icon.png" alt="" width="96" align="right">

# Photo Hub

![Version](https://img.shields.io/badge/dynamic/yaml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fjonathangibson98%2Fpi-custom-features%2Fmain%2Fphoto_shuffle%2Fconfig.yaml&query=%24.version&label=version&color=41BDF5&logo=homeassistant) ![Architectures](https://img.shields.io/badge/arch-aarch64%20%7C%20amd64-informational) ![Sidebar](https://img.shields.io/badge/sidebar-ingress-success) ![Prebuilt image](https://img.shields.io/badge/image-GHCR-2ea44f?logo=docker) ![MQTT](https://img.shields.io/badge/MQTT-optional-660066?logo=mqtt) ![AI Task](https://img.shields.io/badge/AI-ai__task-8A2BE2?logo=googlegemini)

Everything photos in one place: folder shuffles and Unsplash collections as image entities, one wallpaper for every add-on page, a Photo Editor with AI tools, and SVG Maker.

## Features

- **Folders** and **Unsplash** collections published as `image` entities over MQTT, shuffled on a timer
- **Wallpaper**: one background for every add-on page in this repository, with darken, lighten and blur
- **Photo Editor**: crop, adjust, filters and AI edits through your `ai_task` entity
- **SVG Maker**: trace photos into clean SVG icons, or have the AI draw a logo
- Pictures move between tabs in one tap (edit a shuffle photo, set it as wallpaper, trace it as an icon)
- Resizes images for dashboards (default 1920 px, JPEG quality 85)

## What you need

- Home Assistant OS or Supervised (add-ons need the Supervisor)
- MQTT (Mosquitto add-on or your own broker)
- A free Unsplash access key (only for Unsplash)
- An `ai_task` entity (only for AI edits and logos)

## Install

[![Add this repository to your Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fjonathangibson98%2Fpi-custom-features)

1. Click the button above, or go to **Settings → Add-ons → Add-on Store → ⋮ → Repositories** and add `https://github.com/jonathangibson98/pi-custom-features`.
2. Find **Photo Hub** in the store and click **Install**.
3. Check the **Configuration** tab, then **Start**. Turn on **Show in sidebar** to open it from the sidebar.

## Documentation

- [Full documentation](DOCS.md), also on the add-on's **Documentation** tab
- [Changelog](CHANGELOG.md)
- [All add-ons in this repository](../README.md)
