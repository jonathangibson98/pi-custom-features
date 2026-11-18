<img src="icon.png" alt="" width="96" align="right">

# Personal AI Speech

![Version](https://img.shields.io/badge/dynamic/yaml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fjonathangibson98%2Fpi-custom-features%2Fmain%2Fpersonal_ai_speech%2Fconfig.yaml&query=%24.version&label=version&color=41BDF5&logo=homeassistant) ![Architectures](https://img.shields.io/badge/arch-aarch64%20%7C%20amd64-informational) ![Sidebar](https://img.shields.io/badge/sidebar-ingress-success) ![Prebuilt image](https://img.shields.io/badge/image-GHCR-2ea44f?logo=docker)

Natural text-to-speech with emotion tags and local speech-to-text, as an OpenAI-compatible server for the Personal AI integration.

## Features

- Local **Kokoro** text-to-speech with `[happy]`, `[whisper]`, `[sad]`… emotion tags
- Local **faster-whisper** speech-to-text
- OpenAI-compatible `/v1/audio/speech` and `/v1/audio/transcriptions` on port 8880
- Optional proxy to OpenAI or another compatible server
- Test page in the sidebar

## What you need

- Home Assistant OS or Supervised (add-ons need the Supervisor)
- A 64-bit system, 4 GB RAM or more recommended
- About 120 MB download on first start
- The Personal AI integration (to use it from Home Assistant)

## Install

[![Add this repository to your Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fjonathangibson98%2Fpi-custom-features)

1. Click the button above, or go to **Settings → Add-ons → Add-on Store → ⋮ → Repositories** and add `https://github.com/jonathangibson98/pi-custom-features`.
2. Find **Personal AI Speech** in the store and click **Install**.
3. Check the **Configuration** tab, then **Start**. Turn on **Show in sidebar** to open it from the sidebar.

## Documentation

- [Full documentation](DOCS.md), also on the add-on's **Documentation** tab
- [Changelog](CHANGELOG.md)
- [All add-ons in this repository](../README.md)
