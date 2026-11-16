# Creator & AI Builder

Type what you want in plain English. Your Home Assistant `ai_task` entity builds it. One add-on, five tools:

- **Build**: automations, scenes, scripts, template sensors, helpers, AppDaemon apps, pyscripts, blueprints and whole add-ons.
- **Announcements**: tap checkboxes to make AI-written voice announcements (weather, news, welcome home, roasts, whatever). It writes the Home Assistant script and pushes it in, and can run it on a schedule.
- **Facts**: AI-written facts for a dashboard. Pick random topics and angles, a format and a file, optionally run on a schedule. It writes the Home Assistant script (and automation) and pushes it in.
- **Cards**: describe a dashboard card in plain English and the AI writes the Lovelace YAML in your glass style. Pick the entities it reads, preview it with live data, tweak it with a sentence, and copy it into a Manual card.
- **Backup**: save this add-on's data to a path you choose in the options, and import it back.

Use the tab bar at the top of the sidebar panel to switch: **Build / Announcements / Facts / Cards / Backup**.

## Build

- Automations and scenes, new or edits to ones you already have
- Template sensors and binary sensors, test-rendered against your live data before you create them
- Scripts, and helpers (input_boolean, input_number, input_select, input_text, input_datetime, counter, timer)
- AppDaemon apps, pyscripts and blueprints, with syntax checks before anything is written
- Whole add-ons: config, Dockerfile, run.sh and docs, written to `/addons`, auto-repaired for this system
- Multi-part requests, such as helpers + a template sensor + an automation from one sentence
- Flags entities the AI used that don't exist, "Revise" box, "Ask AI to fix it" when HA rejects something
- Never overwrites a file without asking, and backs up what it replaces

## Announcements

- Info sources: household, who is where, weather, news, calendars, to-do, trash, any entity or attribute, or a custom template
- Personalities you can add, edit and remove (a no-personality Default plus Hype, Roast and Sweetie Pie to start), or follow a Home Assistant dropdown the add-on can create and keep in sync
- Speak on a main speaker (TTS), Alexa speakers, and phone notifications; pause and resume music
- **Test before saving**: preview the data, test text only, or test with sound, using a temporary script that is deleted afterward
- Helper tab: describe what you want and the AI writes the instructions and ticks the data it needs
- Settings with searchable entity pickers, Auto-fill, and Export/Import as JSON
- **Dashboard card switch**: pick an `input_boolean` and the announcement turns it on when it starts talking and off when it finishes, so your card only shows while it plays

## Facts

- Random lists (topic, angle, genre...) so every fact is different, plus a random seed
- Formats: just the fact, a title and the fact, or a short list, with an optional heading
- Rules: real and verifiable, go obscure, keep the household out, don't repeat the last fact
- Saved over MQTT (default `file_reader/overwrite/`), with an optional schedule and "someone is home" condition
- Edit imported automations and scripts as fields, and copy a ready-made dashboard card for any fact
- Import a whole automation (like a daily birthdays one) and edit its YAML and save path here
- Keep your own automations with a fact: load an existing automation, or import a script and its automation together
- Test before saving, Helper tab, import your own script, and everything is included in Backup

## Cards

- Describe the card, pick the sensors and helpers it reads (the AI is shown their live attributes, so it uses the real field names), and choose a look: Glass (your style), Plain, or let the AI choose
- Optional show / hide switch wraps the card in a conditional so it only shows while an `input_boolean` is on. **Create a switch for me** makes one
- **Revise with AI**: type a change in plain words and it updates the card you have
- **Preview with live data**: Home Assistant renders the card's template so errors show up before you paste it
- Tells you which custom cards it needs from HACS and flags entities that don't exist
- Saved cards are included in Backup

## Backup

- **Save backup now** writes a JSON file to the `backup_path` option (a folder, or one `.json` file)
- **Import** lists the backups found at that path and restores one. A safety copy of your current data is saved first
- Covers template sensors this add-on manages, "Made so far" history and announcement settings

## How the parts work together

- One AI task entity is shared. Announcements use it unless you pick a different one in Announcements > Settings
- Announcements you push show up in Build's **Made so far** history
- Announcement scripts are normal scripts, so you can pick one in Build's **Change something that already exists** and have the AI edit it
- One connection to Home Assistant, one entity list, one sidebar entry

## Install

1. Copy the `ai_builder` folder into `/addons/` on your Home Assistant (replace the old one if you are upgrading).
2. Settings -> Add-ons -> Add-on Store -> menu (three dots) -> **Check for updates**.
3. Open **Creator & AI Builder** under Local add-ons, then **Install** (or **Rebuild** if upgrading) and **Start**.
4. Turn on **Show in sidebar**.

Template sensors need a one-time `configuration.yaml` change. See [DOCS.md](DOCS.md).

## Requirements

- Home Assistant OS or Supervised (needs the add-on system)
- Home Assistant 2025.8 or newer (for `ai_task`)
- A working `ai_task` entity. The default is `ai_task.google_ai_task`
- For announcements: a text-to-speech engine and a speaker. Alexa speakers need the `alexa_media` custom integration

## Support

AI output can be wrong. Always read the config or script before you create or push it.

## SVG Maker moved

The SVG Maker tab was split out into its own add-on, **SVG Maker** (`svg_maker`), because the tracer crashed inside this add-on. Install it separately. The `svg_*` options were removed from this add-on.
