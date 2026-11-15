# SVG Maker

Turn photos into clean, scalable SVG icons and vector files from your Home Assistant sidebar. Runs fully local: your photos never leave your Home Assistant.

- Facebook-style crop window: auto-suggested crop, drag and pinch to adjust, circle, rounded, square or full photo
- Auto-enhance for cleaner shapes and smaller files; color or black and white tracing with adjustable detail
- Name your file, then Save locally, Download, or Both. Icon-friendly names (`my-dog`) and black and white icons that follow Home Assistant colors
- Default save folder `/homeassistant/custom_icons` (the Custom Icons integration folder); unsaved results auto-keep in a temp folder, with optional auto-delete

## Install

1. Settings -> Add-ons -> Add-on Store -> menu (three dots) -> **Repositories**, and add `https://github.com/jonathangibson98/pi-custom-features` if you haven't already.
2. Open **SVG Maker**, then **Install** and **Start**.
3. Turn on **Show in sidebar**.

Home Assistant downloads a prebuilt image from GitHub's container registry (`ghcr.io/jonathangibson98/{arch}-addon-svg_maker`), so nothing is built on your Pi. If the install says the image can't be found, open your GitHub profile, **Packages**, `aarch64-addon-svg_maker` / `amd64-addon-svg_maker`, **Package settings**, and set it to **Public**.

The image build runs a tracer test, so if the tracer can't run the build fails with a clear message instead of failing on your first conversion.

## Coming from Creator & AI Builder

SVG Maker used to be a tab inside Creator & AI Builder. It is now this separate add-on with the same `svg_*` options and defaults. Copy over any options you changed (see [DOCS.md](DOCS.md)). Files you already saved are untouched.

## Requirements

- Home Assistant OS or Supervised (needs the add-on system), on a 64-bit Pi (aarch64) or an amd64 machine
- Nothing else. To use saved icons as `local:<name>`, install the Custom Icons integration (HACS)
