<img src="icon.png" alt="" width="96" align="right">

# Voice Chat

![Version](https://img.shields.io/badge/dynamic/yaml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fjonathangibson98%2Fpi-custom-features%2Fmain%2Fvoice_chat%2Fconfig.yaml&query=%24.version&label=version&color=41BDF5&logo=homeassistant) ![Architectures](https://img.shields.io/badge/arch-aarch64%20%7C%20amd64-informational) ![Sidebar](https://img.shields.io/badge/sidebar-ingress-success) ![Prebuilt image](https://img.shields.io/badge/image-GHCR-2ea44f?logo=docker) ![Docker](https://img.shields.io/badge/also%20runs%20in-Docker-2496ED?logo=docker)

Hands-free voice conversation with any Home Assistant conversation agent, answered out loud on the speakers you choose.

## Features

- Talk from any phone or browser; the reply plays on one or several speakers, or in the browser
- Works with any conversation agent (Assist, OpenAI, Google, Ollama, Personal AI…), switchable on the page
- Hands-free mode with silence detection
- Household info and live entity values given to the AI as context
- Runs as an add-on or as a plain Docker container

## What you need

- Home Assistant OS or Supervised (add-ons need the Supervisor)
- A conversation agent, an STT and a TTS engine in Home Assistant
- HTTPS for the microphone (built-in self-signed port 8443, or Home Assistant's own HTTPS)

## Install

[![Add this repository to your Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fjonathangibson98%2Fpi-custom-features)

1. Click the button above, or go to **Settings → Add-ons → Add-on Store → ⋮ → Repositories** and add `https://github.com/jonathangibson98/pi-custom-features`.
2. Find **Voice Chat** in the store and click **Install**.
3. Check the **Configuration** tab, then **Start**. Turn on **Show in sidebar** to open it from the sidebar.

It also runs without Home Assistant as a plain Docker container: see **Running without Home Assistant** in the docs.

## Documentation

- [Full documentation](DOCS.md), also on the add-on's **Documentation** tab
- [Changelog](CHANGELOG.md)
- [All add-ons in this repository](../README.md)
