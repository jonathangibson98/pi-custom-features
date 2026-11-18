<img src="icon.png" alt="" width="96" align="right">

# SVG Maker

![Version](https://img.shields.io/badge/dynamic/yaml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fjonathangibson98%2Fpi-custom-features%2Fmain%2Fsvg_maker%2Fconfig.yaml&query=%24.version&label=version&color=41BDF5&logo=homeassistant) ![Architectures](https://img.shields.io/badge/arch-aarch64%20%7C%20amd64-informational) ![Sidebar](https://img.shields.io/badge/sidebar-ingress-success) ![Prebuilt image](https://img.shields.io/badge/image-GHCR-2ea44f?logo=docker) ![Deprecated](https://img.shields.io/badge/status-moved%20to%20Photo%20Hub-orange)

Turn photos into clean, scalable SVG icons. **Moved into Photo Hub**: this stand-alone add-on still works but gets no new features.

## Features

- Auto crop (circle, rounded, square or full) and auto-enhance
- Color or black-and-white tracing (vtracer)
- AI logos through your `ai_task` entity
- Icons saved to `/homeassistant/custom_icons` with icon-friendly names

## What you need

- Home Assistant OS or Supervised (add-ons need the Supervisor)
- Nothing extra
- An `ai_task` entity (optional)

## Install

[![Add this repository to your Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fjonathangibson98%2Fpi-custom-features)

1. Click the button above, or go to **Settings → Add-ons → Add-on Store → ⋮ → Repositories** and add `https://github.com/jonathangibson98/pi-custom-features`.
2. Find **SVG Maker** in the store and click **Install**.
3. Check the **Configuration** tab, then **Start**. Turn on **Show in sidebar** to open it from the sidebar.

## Documentation

- [Full documentation](DOCS.md), also on the add-on's **Documentation** tab
- [Changelog](CHANGELOG.md)
- [All add-ons in this repository](../README.md)
