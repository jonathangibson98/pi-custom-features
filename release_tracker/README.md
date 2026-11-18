<img src="icon.png" alt="" width="96" align="right">

# Release Tracker

![Version](https://img.shields.io/badge/dynamic/yaml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fjonathangibson98%2Fpi-custom-features%2Fmain%2Frelease_tracker%2Fconfig.yaml&query=%24.version&label=version&color=41BDF5&logo=homeassistant) ![Architectures](https://img.shields.io/badge/arch-aarch64%20%7C%20amd64-informational) ![Sidebar](https://img.shields.io/badge/sidebar-ingress-success) ![Builds locally](https://img.shields.io/badge/image-builds%20on%20device-lightgrey?logo=docker) ![MQTT](https://img.shields.io/badge/MQTT-optional-660066?logo=mqtt) ![AI Task](https://img.shields.io/badge/AI-ai__task-8A2BE2?logo=googlegemini)

Track anything with a release date and get told when it drops: shows, movies, games and DLC, albums, celebrities, tech, merch and events.

## Features

- TV and movies (TMDB), games and DLC (IGDB), music (MusicBrainz), celebrities, and anything else you type in
- Per-person lists, so each household member follows their own things
- One sensor (`sensor.release_tracker_releases`) with every upcoming release as attributes, for dashboards and automations
- Notifications when something drops, to everyone or one person
- AI help to fill in dates and details

## What you need

- Home Assistant OS or Supervised (add-ons need the Supervisor)
- Free TMDB key (TV, movies, celebrities)
- Free Twitch client ID and secret (games)
- MQTT (optional)

## Install

[![Add this repository to your Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fjonathangibson98%2Fpi-custom-features)

1. Click the button above, or go to **Settings → Add-ons → Add-on Store → ⋮ → Repositories** and add `https://github.com/jonathangibson98/pi-custom-features`.
2. Find **Release Tracker** in the store and click **Install**.
3. Check the **Configuration** tab, then **Start**. Turn on **Show in sidebar** to open it from the sidebar.

## Documentation

- [Full documentation](DOCS.md), also on the add-on's **Documentation** tab
- [Changelog](CHANGELOG.md)
- [All add-ons in this repository](../README.md)
