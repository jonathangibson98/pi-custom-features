# Creator & AI Builder

Builds Home Assistant things from plain English (automations, scenes, scripts, template sensors, helpers, AppDaemon apps, pyscripts, blueprints, whole add-ons), makes AI voice announcements, makes AI facts and AI-written dashboard cards, and backs up its own data. Use the tab bar at the top of the panel: **Build / Announcements / Facts / Cards / Backup**.

# Build

## How to use it

1. Open **Creator & AI Builder** from the sidebar.
2. Type what you want. Be specific about devices, times, and conditions.
3. Pick a type, or leave it on **Let AI decide**.
4. Tap **Build it**. Gemini-style backends can take a minute or two.
5. Read the result. Tap **See the config** to view it.
6. Tap **Create**. Use **Create all** if there are several items.

Not right? Type a change in the box under the results and tap **Revise**.

### Example requests

- "When the entry temperature is over 76 and someone is home, run the fans for 20 minutes, then stop. Add a switch to override it."
- "Template sensor that shows how many lights are on in the house."
- "Script that turns off all lights and locks the front door, called Goodnight."
- "Helper to hold a target temperature between 65 and 80."

### What each type does

| Type | What it makes | Where it goes |
|---|---|---|
| Automation | Automation | HA, Settings -> Automations |
| Scene | Scene | HA, Settings -> Scenes |
| Script | Script | HA, Settings -> Scripts |
| Template sensor | Sensor or binary sensor | The `template_file` path |
| Helper | input_boolean, input_number, input_select, input_text, input_datetime, counter, timer | HA, Settings -> Helpers |
| AppDaemon app | A Python app plus its config | `apps/ai_builder/<name>.py` and `.yaml` under `appdaemon_apps_dir` |
| Pyscript | A pyscript file | `/config/pyscript/<name>.py` |
| Blueprint | An automation or script blueprint | `/config/blueprints/<domain>/ai_builder/` |
| Add-on | A full local add-on (config, Dockerfile, run.sh, docs) | `/addons/<slug>/` |

**AppDaemon**: new apps go in an `ai_builder` subfolder with their own `.yaml`, so your existing `apps.yaml` is never touched. AppDaemon reloads on its own. Check the AppDaemon log afterward.

**Pyscript**: needs the Pyscript integration installed (the `/config/pyscript` folder must exist). The add-on calls `pyscript.reload` after writing.

**Add-ons**: after creating one, go to Settings -> Add-ons -> Add-on Store -> menu -> Check for updates, then open it under Local add-ons. The add-on checks that `config.yaml` is valid, Python files parse, and warns if `run.sh` uses `with-contenv` without `init: false`.

### Add-on auto-fixes

AI-written add-ons break in predictable ways, so the add-on knows what works on your system and repairs these before you create anything. Each fix is shown on the card as "Fixed automatically".

- Per-architecture base images like `amd64-base` (fail with "no match for platform") are replaced with `ghcr.io/home-assistant/base:latest`
- A leftover `build.yaml` is removed
- `run.sh` gets the `#!/usr/bin/with-contenv bashio` first line, and `config.yaml` gets `init: false`
- `pip install` gets `--break-system-packages`, and a missing `chmod` on `run.sh` is added
- Unquoted versions are quoted, old 32-bit architectures are dropped, and old folder-map names are corrected

It also blocks creation when `config.yaml` has bad schema types, options missing from the schema, invalid `map` entries, or a bad `startup`/`boot` value.

If an add-on you already have fails to build, pick it in the **Change something that already exists** dropdown, paste the build error from the Supervisor log into your request, and create the fix.

### Safety for files and code

AppDaemon apps, pyscripts and add-ons are real code that runs on your system. Read it before you tap Create. The add-on also:

- Checks Python for syntax errors and blocks creating broken code
- Refuses to write outside its allowed folders
- Never overwrites a file without asking. If it exists, you get an **Overwrite it** button
- Keeps a backup of every file it overwrites, in the add-on's own `/data/backups` folder

### Made so far, and how the tabs work together

The **Made so far** tab lists the template sensors the add-on manages, everything made in the Announcements, Facts and Cards tabs, and what the Builder created recently, with the names Home Assistant shows now. **Rename** works on all of them (scripts, automations, scenes, helpers and template sensors) and changes the name in Home Assistant and in the add-on at the same time.

The Builder's AI is also told about your announcements and facts, so you can ask for things like *"when MJ gets home, run my Birthdays announcement"* and it uses the right script.

When you rename, push or save in one tab, the other tabs refresh their lists by themselves.

## Changing something that exists

Use the **Change something that already exists** dropdown. It lists your UI-created automations, scenes, scripts, the template entities this add-on made, your AppDaemon `.py` files, your pyscript files, and your local add-ons. Pick one, describe the change, and the AI gets the current config to edit. The result overwrites the original when you tap **Save changes**.

Scripts, scenes and automations written directly in YAML can't be loaded this way. For AppDaemon and pyscript, only the code is changed. For add-ons, it only rewrites the files the AI changed and asks it to bump the version.

## Configuration (applies to the whole add-on)

| Option | Default | Description |
|---|---|---|
| `ai_task_entity` | `ai_task.gemini_pro_ai_task` | The AI task entity used to write configs |
| `request_timeout` | `180` | Seconds to wait for the AI before giving up (30 to 600) |
| `appdaemon_apps_dir` | `/addon_configs/a0d7b954_appdaemon/apps` | Your AppDaemon apps folder. Must be under `/addon_configs` or your HA config folder |
| `ha_token` | blank | Optional long-lived token. Leave blank unless the default Supervisor access fails (Profile -> Security in Home Assistant) |
| `ha_url` | `http://homeassistant:8123` | Only used when `ha_token` is set |
| `helper_ai_task_entity` | blank | Optional separate AI task entity for the Announcements helpers. Blank uses the Announcements AI Task |
| `template_file` | `ai_builder/package.yaml` | Where template sensors are written, relative to your Home Assistant config folder. Must end in `.yaml` |
| `log_level` | `info` | `debug`, `info`, `warning` or `error`. Applies to the whole add-on |
| `backup_path` | `/share/ai_builder_backups` | Where Backup saves and imports. A folder, or a single `.json` file. See Backup below |
| `backup_keep` | `20` | Folder mode: keep the newest this many backups, delete older ones |

Restart the add-on after changing options.

## One-time setup for template sensors

By default the file is `ai_builder/package.yaml`. You can change it with the `template_file` option. The add-on creates the folder if it doesn't exist.

Automations, scripts, and helpers work immediately. Template sensors are written to the `template_file` path, which Home Assistant has to be told to load. Add this to `configuration.yaml`:

```yaml
homeassistant:
  packages:
    ai_builder: !include ai_builder/package.yaml
```

If you already have a `homeassistant:` section with `packages:`, add only the `ai_builder:` line under it. Do not create a second `homeassistant:` key.

**If you load a whole packages folder** with `packages: !include_dir_named packages`, don't add the line above. Instead set `template_file` to a file inside that folder, for example `packages/ai_builder.yaml`. The add-on notices the folder include and stops showing the banner. Don't put both a folder include and an explicit `ai_builder:` entry under `packages:`, because that breaks the folder include.

If you change `template_file` later, move or delete the old file yourself, then restart Home Assistant once.

Restart Home Assistant once. After that, new or changed template sensors apply instantly with no restart.

The add-on shows a yellow banner until this is detected.

## Where things go

| Type | Where it is stored | Where you manage it later |
|---|---|---|
| Automation | Home Assistant's automations | Settings -> Automations |
| Script | Home Assistant's scripts | Settings -> Scripts |
| Helper | Home Assistant helpers | Settings -> Helpers |
| Template entity | The `template_file` path (default `/config/ai_builder/package.yaml`) | This add-on, "Made so far" tab |

Don't hand-edit the template file. The add-on rewrites it.

## Checks the add-on does for you

- **Unknown entities**: any entity ID in the config that Home Assistant doesn't have is flagged.
- **Template preview**: the state template is rendered against live data. Errors show in red.
- **Home Assistant validation**: if HA rejects the config when you create it, the error is shown with an **Ask AI to fix it** button.

None of this guarantees the automation does what you meant. Read the config before creating anything that controls many devices, locks, or heating and cooling.

## Troubleshooting

**"I can't find ai_task.xxx"**: fix `ai_task_entity` in the Configuration tab to match your entity ID.

**"The AI answered, but not in a usable format"**: the model didn't return clean JSON. Tap Build again or reword. Unofficial or cookie-based AI backends do this more often.

**Request times out**: raise `request_timeout`.

**Template sensor doesn't appear**: check the one-time setup above, then restart Home Assistant.

**Create fails with a validation message**: tap **Ask AI to fix it**, or edit the request and revise.

**"AppDaemon folder not found"**: set `appdaemon_apps_dir` to your apps folder. If AppDaemon's files are in your config folder, use something like `/config/appdaemon/apps`.

**Long code gets cut off or isn't valid JSON**: add-ons are big outputs. Raise `request_timeout`, and consider asking for one add-on at a time.

**Add-on log**: Settings -> Add-ons -> Creator & AI Builder -> Log.

## Privacy

Your request, plus a trimmed list of entity IDs, names, and states relevant to it, is sent to your configured `ai_task` entity. If that entity uses a cloud model, that data goes to that provider. The add-on itself sends nothing anywhere else.

---

# Announcements

All announcement setup happens inside the app, on the **Settings** tab of Announcements, not in this Configuration tab.

- Each field is a search box limited to the right entity type. Tap one, pick an entity, it becomes a chip. Tap the chip to remove it.
- **Auto-fill empty** fills single-choice fields that only have one match.
- **Info sources** cover anything else: label, entity, optional attribute (concerts, sports, PS5...), or a custom template.
- **Export / Import** moves your settings as JSON. `examples/announcement-settings.json` is a filled-in example.
- Required to generate: AI Task, text-to-speech engine, main speaker. The AI Task defaults to this add-on's `ai_task_entity`.
- **Personalities** (Settings -> Personalities): a list of voices. Add, rename, edit or remove them. `Default` has no special personality, is always first and can't be removed. New announcements start on it.
- **Personality dropdown** (optional): an `input_select` that picks the personality from Home Assistant. Press **Create the dropdown for me** to have the add-on make one. Once one is set, saving settings keeps its options in step with your list. Only dropdowns made in Settings -> Helpers can be edited this way; for one in `configuration.yaml`, set its `options` by hand to match your list.
- After adding, renaming or removing a personality, push your announcements again. Each script carries its own copy of the list, and falls back to Default if the dropdown is on a name it doesn't know.

## My announcements

The **My announcements** tab lists every announcement you have made. It is stored in the add-on's own data (so it is included in Backup), not in the Configuration tab.

- **Edit** opens the editor. **Save** keeps your changes here; **Save and push** also updates the script in Home Assistant. The script id never changes after the first push.
- **Run now**, **Duplicate** and **Delete** (a second tap is needed; deleting one that is in Home Assistant also removes its script).
- **Update all in Home Assistant** pushes every announcement again using your current Settings.
- **Made earlier, in Home Assistant** lists scripts this add-on pushed before saving existed. Open one to rebuild the form from the script. Pushing rebuilds the script from the form, so hand edits made in Home Assistant are replaced.

### Import your own script

Already have an announcement script? Tap **Import my script** on **My announcements** and paste it (YAML). A pasted script can be just the script, the script with its id on top like in `scripts.yaml`, or only the steps. You can also pick a script that already exists in Home Assistant and press **Load**.

- Leave **Script id** blank to create a new script, or type the id of an existing script to take it over. Pushing then replaces it, and automations that call it keep working.
- The editor shows your YAML exactly as written. Change the name and the `alias:` line follows. **Check YAML** tests it, **Save** keeps it here, **Save and push** sends it to Home Assistant.
- **Switch to the form tools** (tap twice) reads the script into the form so you get the data-source picker, personalities, speakers, volume, helper and test panel. Your own prompt is kept word for word as the instructions. The form rebuilds the script when you push, so steps it does not cover are dropped. Leave without saving to keep your original.

## Announcement tabs

- **Editor:** pick data, personality, then type **What should it do?** in plain words. Every data source is loaded into a variable (`src_<name>`) in the script, and the AI Task reads those variables.
- **Test before saving:** runs a temporary copy of the script and deletes it afterward, so nothing lands in your Scripts list. *Preview data only* skips the AI and speaking, and shows what each source rendered. *Test (text only)* also runs the AI and shows what it would say. *Test with sound* speaks it too. If a step fails, the error from Home Assistant is shown.
- **Push to Home Assistant** writes the script (it then appears in Settings -> Scripts and in Build's history).
- **Helper:** (1) describe what you want and the AI writes the instructions and ticks the data it needs; (2) test an entity and add it as an info source.
- **Settings:** your entities and notify targets, plus info sources. Each source has a template you can edit to fix it, and a reset button to go back to the auto-generated one.

Phone notifications: entities (`notify.jon`) and services (`notify.mobile_app_*`, shown as "service") both work, and you can type an id that isn't listed.

Setups you saved in your browser with an older version can be moved into My announcements from that tab.

## Run an announcement on a schedule

Each announcement has an optional **Run it automatically** section (step 6, or step 3 for an imported script). Tick **Run on a schedule**, then choose any of:

- **Every** N minutes (up to 59) or hours (up to 23). `0` turns the repeat off.
- **At this time every day.**
- **When this entity changes**, optionally for one attribute and only after it has held for some seconds.
- **Only when someone is home**: runs only if any listed entity is on or home. A zone counts when it has someone in it. **Use my default presence list** fills it from Facts -> Settings -> Someone is home.

**Save and push** then makes a second Home Assistant automation, `<script id>_auto`, that calls the announcement's script. The script is not changed, so your own automations that call it keep working.

- If the announcement is still talking when the next trigger comes, the new trigger is skipped.
- Untick **Run on a schedule** and push to remove the automation. Only automations this add-on made are ever removed.
- **Show schedule YAML** beside the script shows what will be pushed.
- Deleting an announcement also removes its schedule. **Duplicate** copies the settings with the schedule off.
- The card in **My announcements** says whether the schedule is on, off in Home Assistant, or not pushed yet.

## Dashboard card switch

Each announcement has an optional **Dashboard card** section. Pick an `input_boolean` (or press **Create a switch for me**) and the announcement controls it:

- **Turn it on**: *When it starts talking* (default: right after the AI has written the text, just before it is spoken) or *Right away, before the AI writes it*. The second one shows the card sooner, but if the AI step fails the card stays on.
- **Turn it off again when it finishes**: waits for the speech to end (and the music to resume), then turns the switch off.
- **Keep the card up this many extra seconds**: delay before it turns off.
- If nothing speaks (a notification-only announcement) there is no finish to wait for, so it only turns off when you set extra seconds. Otherwise it stays on.
- Wrap your dashboard card in a conditional on the same `input_boolean`. The **Cards** and **Facts** tabs do that for you when you pick a show / hide switch.
- Preview and text-only tests never flip the switch. **Test with sound** does, so you can see the card.
- When you import a hand-written script and switch to the form tools, an `input_boolean` it turns on (other than your talking flag) is filled in as the card switch.

The steps are named *Show dashboard card*, *Keep dashboard card up* and *Hide dashboard card* in the script, so the editor can read them back.

## Save to a file and show it on a card

Optional. Turn on **Save it to a file** and the script also publishes the announcement over MQTT (same topic prefix as Facts), so a `file_reader` sensor and a dashboard card can show it. Pick **What goes in the file**:

- **Just what it says (plain text)**: the spoken text is saved as it is.
- **Separate fields (JSON), like a Facts data list**: the AI answers with a JSON object made of the fields you set up. Give each field a name, a short description of what the AI writes there, and where it goes on the card: **Title (top)**, **Text (middle)**, **Bottom line (small)** or **Don't show**. Then pick **Announce this field**: that one is spoken (and follows your instructions, the personality and the max length), the rest are only for the card.

**Use the birthday example** fills in `name` (title, whose birthday it is), `message` (text, the part that is spoken) and `detail` (bottom line, age and what they are known for).

In fields mode the script strips code fences from the AI's answer and reads it safely. If the answer is not usable JSON, nothing is spoken or saved (and a card switch turned on early is turned off again). **Test, text only** shows each field under *What goes on the card*.

The editor writes a glass card for the file (title, text, bottom line), with **Copy card YAML**, **Preview it**, and **Design a custom card in Cards**, which opens the Cards tab already set up from this announcement.

The file name is fixed the first time you save, so renaming the announcement later keeps the same file and sensor.

## Renaming

Press **Rename** on any saved announcement (or fact, or card). If it is in Home Assistant, its name there changes too, and so does its schedule automation (`<name> (auto)`). The script id never changes, so automations that call it keep working.

It works the other way as well: rename the script in Home Assistant and the add-on picks up the new name the next time you open the list (it says so at the top). A name you changed here but haven't pushed yet is never overwritten. A name typed in the entity's own settings in Home Assistant is cleared when you rename from here, so the new name shows.

## Announcement troubleshooting

**Push to Home Assistant fails**: check the Log tab. If Home Assistant refuses the default Supervisor access, set `ha_token`.

**No entities in the pickers**: you can still type an entity id into any field.

## Security

Only the Home Assistant ingress gateway can reach this add-on's web server, so other add-ons and devices on your network can't call it directly.

---

# Facts

AI-written facts for a dashboard. Each fact is one Home Assistant automation (triggers, then the steps) that asks your AI Task for one fact and saves it to a text file over MQTT (by default under `file_reader/overwrite/`). It works like Announcements: a library, an editor, a test panel and a helper. The AI Task, data sources and entity list are shared with Announcements.

## My facts

- **New fact** starts the editor. **Start from** has presets modeled on a random trivia fact, a dark history fact, a music fact (random artist, or titled "Artist ||| fact") and a city fact.
- Each saved fact shows its status, its file, and whether its schedule is on. **Edit, Run now, Duplicate, Delete** work like Announcements. **Save** keeps changes here only, **Save and push** creates or updates the automation in Home Assistant. Its id stays the same. Facts made before 2.10.0 are a script plus a schedule automation; open one and tap **Switch to a single automation**, then push.
- **Import my script** takes a script you wrote by hand and keeps it exactly as written.

## The editor

1. **Name**, plus presets.
2. **What it's about**: optional data sources (shared with Announcements), what the fact should be, and **random lists**. Each run picks one option from every list and tells the AI (for example `TOPIC FOR THIS RUN`). A random number is added so repeats are less likely.
3. **How it reads**: just the fact, a title and the fact, a short list, or a **data list (JSON)** (name the list, say how many items, add fields, optionally sort and drop items that fail a test, for example birthdays: `{"birthdays": [{"name": ..., "year": ...}]}`); a heading line saved above it (can use `{{ fact_title }}` and your list names); length; language (clean, light, profanity as needed); rules (real and verifiable, go obscure, keep the household out, don't repeat the last fact); extra rules.
4. **Where it goes**: the file name, added to the MQTT topic prefix from Settings. A name with a slash is used as the full topic.
5. **Run it automatically** (optional): every N minutes or hours, and/or when an entity or attribute changes, only when someone is home. These become the triggers and conditions of the fact's automation. With the schedule off the automation has no triggers and you start it with **Run now**.

**Try it first** runs a temporary copy of the script and deletes it: **Preview what it picks** (no AI call), **Test, don't publish**, **Test and publish**.

## Facts settings

MQTT topic prefix, the sensor that reads your fact file (so the AI can avoid repeating the last fact), the default "someone is home" entities, default length and rules added to every fact.

## Facts troubleshooting

- **Nothing shows on the dashboard**: use **Test and publish**, then check the topic under **Where it goes** against your file_reader setup.
- **Empty result**: open **Test, don't publish** and read "What the AI answered, raw". With the title format, the AI must answer as `Title ||| fact`.
- **Schedule says "not pushed"**: press **Save and push**.

---

# Cards

An AI dashboard card creator. It sits beside Facts and uses the same AI Task as Announcements.

## Making a card

1. **New card**, then give it a name.
2. **What should it show?** Describe it in plain words: rotating or scrolling, sizes, emoji, what goes big and what goes small.
3. **Data the card reads**: pick the sensors, helpers or entities. The AI is shown their live state and attributes, so it uses the real field names. For a fact or list saved with Facts, pick its file_reader sensor (for example `sensor.read_new_songs`).
4. **Show / hide switch** (optional): the card is wrapped in a conditional that only shows it while this `input_boolean` is on. **Create a switch for me** makes one. Pick the same switch in an announcement's Dashboard card section and the announcement turns the card on and off.
5. **Look**: Glass matches your other cards (the blurred, rounded style), Plain is normal Home Assistant, or let the AI choose.
6. **Build the card**, read the YAML, and use **Copy card YAML**. In your dashboard add a **Manual** card and paste.

## Changing it

- Edit the YAML by hand and press **Check my edits**, or type a change under **Change something** and press **Revise with AI**. It gets your current YAML and returns the whole card.
- **Build it again from scratch** replaces the card in the box (it asks you to tap twice).
- Picking a show / hide switch after the card is built wraps the YAML for you, or points an existing wrapper at the new switch.

## Preview

**Preview it** asks Home Assistant to render the card's templates (`custom:html-template-card` and markdown) with your live entities, so a template error shows up here instead of on your dashboard. The preview is sandboxed and approximate: your theme, card height and animations can look a little different. Cards made only from built-in card settings have no template to preview.

## Notes

- Custom cards the YAML uses (for example `custom:html-template-card`, `card_mod`) come from HACS. The card shows what it needs.
- Entity ids in the YAML that Home Assistant doesn't have are listed as a warning. The AI is told to use only the entities you picked or typed.
- AI output can be wrong. Read the card, and preview it, before you paste it into a dashboard.
- Saved cards live in the add-on and are included in Backup. The add-on does not edit your dashboards: you paste the card yourself.

## Start from an announcement or fact

**Start from something made here** lists every announcement and fact that saves to a file. Picking one fills in its sensor and its show / hide switch, writes a starting description, and tells the AI exactly what is in the file (each field and what it is for), so it can build the card before the file has anything in it. The **Design a custom card in Cards** buttons in Announcements and Facts do the same thing from there.

When you open a saved card later and the announcement or fact it came from now writes a different sensor, uses a different switch, or has different fields, the card tells you and offers **Update this card's setup**.

# Backup

The **Backup** tab saves and restores this add-on's own data:

- the template sensors it manages (and so the template file it writes)
- the "Made so far" history
- your Announcements settings
- your saved announcements, facts and dashboard cards

It does not back up your Home Assistant automations, scripts or helpers (use Home Assistant's own backups for those), or the `/data/backups` copies of files the Builder overwrote.

## Choosing where backups go
Set `backup_path` in the Configuration tab and restart the add-on.

- **A folder** (default `/share/ai_builder_backups`): each **Save backup now** creates `ai_builder_backup_YYYYMMDD-HHMMSS.json`. The newest `backup_keep` of those are kept. The Import list shows every valid backup file in the folder, so you can also copy a backup in from elsewhere.
- **A single file** ending in `.json`, for example `/share/creator_backup.json`: each save overwrites that file, and Import reads it.

Use a path under `/share`, `/media`, `/backup` or `/homeassistant`. Anything stored only inside the add-on is deleted if you uninstall it. Protected system paths are refused and the default is used instead.

## Importing
Tap **Import** next to a backup, then tap again to confirm. Import **replaces** the current template sensors, history and announcement settings with the backup's. Before it changes anything it saves a safety copy named `ai_builder_backup_pre-import_...json` in the same place, so you can import that one to undo. Damaged or non-backup files are rejected without changing anything. Template sensors are rewritten to the template file and reloaded straight away.

Moving to a new Home Assistant: install the add-on, set the same `backup_path` (or copy the file there), and import. Announcement Maker settings from the old standalone add-on are a different format; use its Export and the Announcements Import for those.
