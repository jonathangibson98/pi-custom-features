# SVG Maker

Turn photos into clean, scalable SVG icons and vector files from your Home Assistant sidebar. Runs fully local: your photos never leave your Home Assistant.

- Facebook-style crop window: auto-suggested crop, drag and pinch to adjust, circle, rounded, square or full photo
- Auto-enhance for cleaner shapes and smaller files; color or black and white tracing with adjustable detail
- Name your file, then Save locally, Download, or Both. Icon-friendly names (`my-dog`) and black and white icons that follow Home Assistant colors
- Default save folder `/homeassistant/custom_icons` (the Custom Icons integration folder); unsaved results auto-keep in a temp folder, with optional auto-delete

## Install

1. Copy the `svg_maker` folder into `/addons/` on your Home Assistant.
2. Settings -> Add-ons -> Add-on Store -> menu (three dots) -> **Check for updates**.
3. Open **SVG Maker** under Local add-ons, then **Install** and **Start**.
4. Turn on **Show in sidebar**.

The first install builds the image on your Home Assistant, which can take a few minutes. The build runs a tracer test, so if the tracer can't run on your hardware the install fails with a clear message instead of failing later.

## Coming from Creator & AI Builder

SVG Maker used to be a tab inside Creator & AI Builder. It is now this separate add-on with the same `svg_*` options and defaults. Copy over any options you changed (see [DOCS.md](DOCS.md)). Files you already saved are untouched.

## Requirements

- Home Assistant OS or Supervised (needs the add-on system)
- Nothing else. To use saved icons as `local:<name>`, install the Custom Icons integration (HACS)
