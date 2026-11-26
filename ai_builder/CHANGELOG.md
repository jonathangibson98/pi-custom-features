# Changelog

## 3.6.1 - 2026-11-25

- **Music keeps playing while the AI writes.** The script now asks the AI Task for the text first, and only pauses your music (and sets the talking flag and speaker volume) once the answer is ready, right before it speaks. No more silence while it thinks. If the AI answer is unusable, the music is never paused. Scripts you already pushed keep the old order until you push them again.

## 3.6.0 - 2026-11-25

- **Data sources can be shared or belong to one side.** Each source is now **Shared** (announcements and facts both use it), **Announcements only** or **Facts only**. Pick it when you add a source, or change it under **Used by** when you edit one. Facts has its own **Data sources** section in Settings now, so it no longer has to send you to the Announcements settings. Everything you already have stays shared.
- **A "Made by AI" section.** When the helper (Add something to talk about) or an import makes a data source for you, it goes in its own **Made by AI** section instead of mixing into your own list, and only for the kind of thing that made it. Tap **Keep** on one to move it into your own list. A source that reads the same thing as one you already have is reused instead of copied, so making a new announcement or fact no longer piles up near-duplicates.
- In the editor, sources the AI made show **(AI)** after their name.

## 3.5.0 - 2026-11-25

- **Many more schedule options.** On the When tab: extra times every day, sunrise or sunset with minutes before or after, and an entity trigger that can wait for a specific new state. On the Only if tab: a second time window (morning and evening), months of the year, and the extra entity checks can now be "is", "is not", "is above" or "is below" a number, on an attribute, and held for some minutes. Old schedules keep working as they were.
- **Fixes the "nothing works any more" case.** If any announcement or fact points at an AI Task that no longer exists in Home Assistant (for example after you renamed or removed one), a banner at the top of the library lists them and switches them all to an AI Task you pick, then updates Home Assistant. A missing default AI Task in Settings gets switched too.

## 3.4.1 - 2026-11-25

- **Check with AI and Fix selected with AI now know how this add-on works.** Before it reviewed your YAML like any Home Assistant script. Now the AI is first told how announcements and facts are built and run: the order of the steps, what each setting does and which values are allowed, how the schedule and its "only if" conditions are checked, what the add-on adds on purpose (delays, pausing music, the talking flag), and what you have set up (your data sources, speaker, text-to-speech, Alexa and phone targets, personalities). So it stops flagging the add-on's own steps as problems and its fixes use the right setting names and real values.
- The briefing lives in a new file, `knowledge.py`, so it can be kept in step with the editors.

## 3.4.0 - 2026-11-25

- **Tick what you want fixed and let the AI do it.** Every item in **Check with AI** now has a tick box (and a **Tick all** button). Tap **Fix selected with AI** and your AI Task changes the editor's settings (the instructions, length, schedule, who must be home and so on) to solve just those items. You see each change as "Was / Now" and nothing is saved or pushed until you press Save. **Undo these changes** puts everything back.
- It only uses entities that exist in your Home Assistant and data sources you already have, and it ignores any change to the name, id or the kind of a setting. For a pasted script it returns corrected YAML, which is checked before it is used.
- Some problems cannot be fixed this way, for example an entity that lives inside a data source in Settings. The AI says so next to that item instead of guessing.

## 3.3.0 - 2026-11-25

- **New "Check with AI" button in Announcements and Facts.** It sits above "Try it first". Tap **Check it** and two things happen: a quick check confirms the YAML parses, no placeholders like `SET_ME` are left, the schedule has a trigger, and every entity it uses really exists in your Home Assistant. Then your AI Task (the one picked for that announcement or fact, else your default) reads the whole thing and lists what is wrong (**Fix**) or could be better (**Tip**), with a plain-words fix for each. Nothing is changed or run.
- If no AI Task is set, the quick checks still run and the result says so.

## 3.2.2 - 2026-11-24

- **Pick the AI Task for each announcement or fact, or use your default.** Both editors now have an **AI Task that writes it** box with two buttons: **Use my default** (the one set in Announcements > Settings, shown by name) or **Pick one** (search and choose any AI Task). Facts had this hidden under "Use a different AI Task for this one"; it is now in section 2 where you can see it. Announcements could only use the default before.
- The setup warning now says a fact can also pick its own AI Task when no default is set.
- Fixed the word "null" showing under the who-is-home picker in 3.2.1.

## 3.2.1 - 2026-11-24

- **Facts -> Settings now uses the same people picker as a schedule.** The old "Someone is home" card is now **Who is home (default)**: tap the people, pick **Any of them**, **All of them** or **None of them**, and add zones or trackers underneath. The mode is saved with the list.
- **Use my defaults** on a schedule's **Only if** tab loads both the people and the mode (it shows while that schedule's list is empty). The button says what it will load.

## 3.2.0 - 2026-11-23

- **The schedule section is rebuilt, and it is the same in Announcements and Facts.** One summary at the top says in plain words what it does ("Runs every 2 h. Only if all of Jon, MJ home, 08:00 to 22:00, Mon Tue"), and three tabs hold the options: **When**, **Only if** and **Limits**. The number on a tab shows how many things are set in it.
- **Pick exactly who has to be home.** Tap the people you want, then choose **Any of them**, **All of them** or **None of them** (for example "only run when nobody is home"). Zones, device trackers and on/off entities can be added under the people. Your old "someone is home" lists keep working as **Any of them**.
- **More conditions:** a time window and the days of the week, daytime only or after dark only, and as many "this entity is / is not this state" checks as you want. All of them must be true.
- **Limits:** run at most once every N minutes, so a busy trigger can't spam you.

## 3.1.5 - 2026-11-22

- **The "Also change the entity ID" box is now on the Announcements and Facts editors too**, right under the name field, so you can tick it while editing instead of only under Rename. It applies to both **Save** and **Save and push**, and it also works with the name left unchanged (it just fixes the entity ID). It remembers your choice, and the first time it starts from the add-on option **Change the entity id when a name changes**. The result is shown in the message after saving.

## 3.1.4 - 2026-11-22

- **Change the entity ID when you rename.** Renaming used to leave the old entity ID (`script.old_name`). Now:
  - The **Rename** box has a checkbox, **Also change the entity ID to match**. Tick it and the entity ID follows the new name (`script.new_name`). If that ID is taken it adds `_2`, `_3`...
  - **Fix an old one:** tick the box and press Save without changing the name, and only the entity ID is updated.
  - New option **Change the entity id when a name changes** (Configuration tab) does the same automatically whenever a name changes here, including when you just press Save in the editor.
  - Anything in Home Assistant that used the old entity ID (dashboards, other automations) has to be updated by you; Home Assistant doesn't do that. The add-on itself keeps finding and running the item under its new ID.

## 3.1.3 - 2026-11-21

- **Fixed: Dashboards AI often failed to send back a dashboard.** It used to ask the AI to retype your whole dashboard, which on a big one gets cut off or runs out of time.
  - The AI now sends back **only the views it changed**, and they are merged into your dashboard. Much shorter replies, much less to go wrong.
  - If the reply is cut off or isn't readable, it **asks once more automatically** before giving up.
  - When it still fails, the message now says **why** (nothing came back, cut off, or the AI call itself failed) and suggests picking one view. The start and end of the bad reply are written to the add-on log.

## 3.1.2 - 2026-11-21

- **Names now stay in sync with Home Assistant, both ways.**
  - **Rename here, it changes in Home Assistant.** Changing the name of an announcement or fact and pressing **Save** (not just Push) now renames its script, or its automation, and its "(auto)" schedule in Home Assistant right away. Before, the new name only reached Home Assistant when you pushed.
  - **Rename in Home Assistant, it changes here.** The add-on checks every 30 seconds and the Announcements and Facts lists refresh by themselves, so you no longer have to reopen the list to see the new name.
  - A name you changed here but haven't saved yet is never overwritten. If Home Assistant can't be renamed (a script written in a YAML file, say), Save still works and tells you why.

## 3.1.1 - 2026-11-17

- **Better on phones** (built around the Home Assistant iPhone app): text fields no longer make iOS zoom in, buttons and switches are finger-sized, rows of tabs swipe sideways instead of getting cut off, and wide content or long error text no longer pushes the page sideways.

## 3.1.0 - 2026-11-17

- **My screens** (Dashboards): save your real screens and pick them under **Shown on**. The preview, **Does it fit?** and the AI then use their exact size.
  - **Type the size in**, with quick picks for common sizes, or **💾 Save as my screen** from Custom size.
  - **Or link entities that report the size**: a width and a height sensor (Browser Mod's browser width/height, Fully Kiosk…), or one entity with both (a `1280x720` state or width/height attributes).
  - **🔎 Find screens that report their size** pairs them up for you.
  - Linked screens follow the live size, and use a fallback size while the screen is off.
  - Each screen says what it is (TV, touch screen, or scrolling is fine), so the AI builds for it.

## 3.0.3 - 2026-11-17

- **Fixed: the Dashboards preview didn't match the real screen** for layout-card views. `custom:vertical-layout`, `masonry-layout`, `horizontal-layout` and `grid-layout` are now laid out like layout-card does it: `width`, `max_cols`, `min_cols`, `max_width`, `margin`, `padding` and `card_margin`, cards pinned with `view_layout: column`, and `layout-break`. A cast view with `max_cols: 2` now shows 2 columns with every card in its own column, not 3.
- **Fixed: the view's background** is used in the preview. That includes an image entity picked in the editor (`media-source://image/image.…`), plus its opacity, size and position, instead of the theme's wallpaper.
- Home Assistant's own masonry view now uses Home Assistant's column breakpoints, so the column count matches it.

## 3.0.2 - 2026-11-17

- **Fixed: the Dashboards preview was blank** (in the phone app it can't sign in to a dashboard shown inside the page). The preview is now drawn by the Home Assistant page itself, with your real cards, custom cards, card-mod, theme and live states, sized to the screen you picked. It follows the view's layout (sections, masonry or panel) closely but not pixel-perfect; **open the real thing** shows the exact dashboard in a new tab. **Does it fit?** now also says how much room is left.

## 3.0.1 - 2026-11-17

- The AI uses your **default AI**, picked at the top of Personalized Info (`select.default_ai_task`), when `ai_task_entity` points at an AI Task you don't have. Before, the built-in default (`ai_task.google_ai_task`) failed if you didn't have that one.

## 3.0.0 - 2026-11-17

- **New: Dashboards.** Open any of your dashboards, tell the AI what to change, and preview the draft live at the real screen size before saving: TV 1080p / 720p (cast), Nest Hub, Hub Max, wall tablet, phone, desktop or a custom size. **Does it fit?** measures the real page and **Make it fit** fixes overflow. Quick ideas (fit the screen, TV friendly, tidy up, group by room, sections layout, fix broken, clock & weather header, mobile friendly, dark glass), a health check (missing entities, custom cards that aren't installed), undo/redo, a YAML editor, **Save as a new dashboard**, building a new dashboard from a description, and the last 25 versions kept for every dashboard you save.
- **File Reader is now built in** as the **Files** section, with the same MQTT topics, sensors and entity IDs, plus AI help (summarize, ask, write, make an automation). Files from File Reader's private folder are copied from its newest backup on first start. New options: `files_path`, `files_scan_interval`, `files_api_token` and optional `mqtt_*`. After updating, uninstall the File Reader add-on.
- **New menu.** Sections are grouped: **Build** (Automations & more, Dashboards, Cards), **Voice & facts** (Announcements, Facts), **Files** and **Backup**. It remembers the last page in each group.
- New icon and logo, because it's a lot more than AI now.
- Needs MQTT (the Mosquitto add-on) for Files sensors and Supervisor access to find it. Restart once after updating.

## 2.19.2 - 2026-11-17

- **Easier to read over wallpapers.** When the page shows a wallpaper (your theme's, the shared one from Photo Hub, or your own), it now checks how bright the picture is and lays down just enough of a tint for the text to stay readable: bright wallpapers get more, dark ones barely any. Text also gets a soft shadow.

## 2.19.1 - 2026-11-17

- Uses the shared **add-on wallpaper** you pick in Photo Hub (new *Add-on wallpaper* tab). This add-on's own Wallpaper option still wins when set.

## 2.19.0 - 2026-11-16

- **Pick the web UI wallpaper.** New **Wallpaper** option on the Configuration tab. Leave it empty to use your Home Assistant theme's wallpaper, enter `none` for no wallpaper, or point it at your own image: drop it in `/config/www` and enter the file name (e.g. `wallpaper.jpg`), `/local/wallpaper.jpg`, or a full `https://` link.

## 2.18.0 - 2026-11-16

- **Follows your Home Assistant theme.** The web UI now uses the colors of whatever theme Home Assistant is showing, light or dark, and changes live when you switch. Themes with a dashboard wallpaper and frosted-glass cards (like Apple / Liquid Glass themes) carry over too: wallpaper behind, see-through blurred cards, matching corners. Opened outside Home Assistant it keeps its own look.

## 2.17.1

- Removed personal names, places and home-specific entity IDs from the defaults, examples and docs, so new installs start clean.

## 2.17.0 - 2026-11-15

- **Convert what's already here.** Facts and announcements you imported before converting existed (the "kept exactly as you wrote it" step editor) now have a **Convert to the normal form** button at the top of the editor. It runs the same converter as a new import: data sources, format and rules, fields, random picks, the file, speakers and the schedule are filled in, and your AI Task splits the prompt. The id stays the same, so pushing updates the same automation or script in Home Assistant (a copy of an automation it replaces is saved first). **Use my original instead** goes back until you push
- Announcements' old **Switch to the form tools** now uses the full converter too, and falls back to the old way if your AI Task can't help
- **Facts can run at a time of day.** **When it runs** has **And at this time every day**, so converted facts keep a daily time trigger (like Daily Birthdays at 6:00) instead of dropping it

## 2.16.1 - 2026-11-15

- **Back up from Home Assistant.** The add-on now listens on stdin, so the `hassio.addon_stdin` action with `input: backup` makes a backup right away. One script can back up every add-on at once (see the repository README, "Back up all add-ons with one action")

## 2.16.0 - 2026-11-15

- **Importing converts into the form.** **Import my script or automation** on Announcements and Facts now turns a hand-made script or automation into a normal announcement or fact you edit with the form, instead of raw YAML. Data the prompt reads becomes data sources (added to Settings, reusing ones you already have), speakers, Alexa and phones become outputs, volume, pause, card switch and MQTT file are filled in, and triggers and "is home" conditions become the schedule. Your AI Task splits the prompt into the instructions and the voice (per personality too), and for facts fills in the format and rules. Random lists become Random picks and the last-fact sensor becomes Avoid the last fact
- What couldn't be converted is listed in the editor. **Use my original instead** goes back to the YAML exactly as written, and **Keep it exactly as written** is still a choice in the import box
- An automation that only runs a script is read through to the script. When the converted announcement takes over its schedule, pushing turns the old automation off (a copy is backed up) so it doesn't run twice. A converted fact automation keeps its id and is replaced in place, with a backup

## 2.15.0 - 2026-11-15

- **Announcements can answer in JSON fields, like a Facts data list.** In **Save to a file and show it on a card**, pick **Separate fields (JSON)**. Set up the fields (name, what the AI writes there, and whether it is the card's title, text or small bottom line) and pick **Announce this field**: that one is spoken, the others are saved for the card. **Use the birthday example** sets up `name` as the title, `message` as the spoken text and `detail` at the bottom
- The script reads the answer safely (code fences stripped). If it is not usable JSON nothing is spoken or saved. **Test, text only** shows each field. The card the editor writes now has a title, the text and a bottom line, and still shows an older plain-text file
- The file name is now fixed when you first save, so renaming an announcement or fact keeps the same file and sensor
- **The tabs work together.** Cards has **Start from something made here**: pick an announcement or fact and its sensor, switch and file layout are filled in and told to the AI. Announcements and Facts have a **Design a custom card in Cards** button that does the same. A saved card notices when its announcement or fact changed and offers to update. The Builder's AI knows your announcements and facts, so you can ask it to run one. Saving, pushing or renaming in one tab refreshes the others
- **Rename from the web UI, kept in step with Home Assistant.** **Rename** on saved announcements, facts and cards, and in Build -> Made so far for scripts, automations, scenes, helpers and template sensors. It changes the name in Home Assistant (and the schedule automation) and in the add-on together. Rename something in Home Assistant and the add-on picks it up when you open the list. Ids never change, so nothing that calls them breaks
- Scripts whose entity id you changed in Home Assistant are still found (the add-on looks them up in the entity registry)

## 2.14.0 - 2026-11-15

- **Facts now have a card preview, like the Cards tab.** The **Dashboard card** section in the fact editor has a new **Preview with live data** button. Home Assistant renders the card's template with your real entities and shows it right there, so you can see the text card or rotating list before you paste it into a Manual card
- The preview ignores the show / hide switch, so you always see the card. It reads the sensor you picked, so if it looks empty, push the fact and run it once first
- **Announcements can now save their text to a file and make a card for it (optional).** New **Save the text to a file** section in the announcement editor. Turn it on and the script also publishes what it says over MQTT (same topic prefix as Facts, file name and sensor are yours to change). The editor then writes a glass-style dashboard card for that file, with **Copy card YAML** and **Preview it**. If you picked a show / hide switch in the Dashboard card section, the copied card is wrapped in it
- It is off by default. Existing announcements are unchanged until you turn it on and push. Tests without sound never write the file, and scripts you imported as your own are left exactly as written

## 2.13.0 - 2026-11-14

- **Announcements can now run on their own, the same way Facts can.** New **Run it automatically** section in the announcement editor: run every N minutes or hours, at a time of day, and/or when an entity (or one of its attributes) changes, and only when someone is home. Pushing makes a Home Assistant automation (`<script id>_auto`) that calls the announcement's script. The script itself is unchanged, so automations of your own that call it keep working
- Works for announcements built with the form and for ones you imported as your own script. A **Show schedule YAML** box beside the script shows exactly what will be pushed
- If the announcement is still talking when the next trigger arrives, that trigger is skipped instead of cutting it off
- Turning the schedule off and pushing removes the automation, but only one this add-on made. Deleting an announcement removes its schedule too. **Update all in Home Assistant** pushes schedules as well
- Each saved announcement shows whether its schedule is on, off in Home Assistant, or not pushed yet. **Duplicate** copies the schedule settings with the schedule switched off, so you don't get two copies firing at once
- "Only when someone is home" can start from the default list you set in Facts -> Settings
- Existing announcements have no schedule until you turn one on and push

## 2.12.0 - 2026-11-13

- **Announcements can now turn a dashboard card on and off.** New **Dashboard card** section in the announcement editor: pick an `input_boolean` (or press **Create a switch for me**) and the script turns it on when the announcement starts talking, then off when it finishes. Choose to turn it on right away (before the AI writes) instead, keep the card up for some extra seconds, or leave it on afterwards. Test runs without sound never flip the switch
- Importing a hand-written script (like a New Music Friday one) and switching to the form tools now picks up the card switch: an `input_boolean` it turns on that isn't your talking flag is filled in for you
- **New Cards tab, beside Facts: an AI dashboard card creator.** Describe a card in plain English, pick the entities it reads (the AI sees their live attributes), and get Lovelace YAML in your glass style. Optional show / hide switch wrapper, **Revise with AI**, hand-editing with **Check my edits**, and **Preview with live data**, where Home Assistant renders the template so errors show before you paste. Flags missing entities and says which HACS cards it needs. Copy into a Manual card
- Saved cards are included in Backup and restored with Import (older backups leave your cards alone)
- Push your announcements again to use the new switch steps. Existing scripts are unchanged until you do

## 2.11.1 - 2026-11-12

- **No more "it was written in configuration.yaml so I can't edit it" error.** The Personality dropdown now fixes itself. If the dropdown you picked is written in `configuration.yaml` (or was deleted), the add-on makes its own editable dropdown (`input_select.ai_builder_personality`) through Home Assistant, switches your settings to it and keeps its options matched from then on. If that one already exists it is reused instead of making a copy
- After it switches, push your announcements again so their scripts use the new dropdown, and point any dashboard card that used the old one at the new one

## 2.11.0 - 2026-11-12

- **Personalities are now a list you control.** In Announcements -> Settings -> Personalities you can add your own, edit the wording of any of them, and remove the ones you don't want. Hype, Roast and Sweetie Pie are still there to start with, and any wording you had already changed is kept
- **New "Default" personality with no special voice.** It is always first in the list, can't be removed or renamed (you can still edit its wording), and is what new announcements start with
- **The Home Assistant dropdown is made and kept up to date for you.** Press **Create the dropdown for me** and the add-on makes an `input_select` with your personalities and picks it. After that, saving settings keeps its options matched to your list. Only dropdowns made in Settings -> Helpers can be edited this way. One written in `configuration.yaml` shows you the options to type in by hand
- Generated scripts now have a fallback: if the dropdown is ever on something the script doesn't know (a renamed or removed personality), it uses Default instead of saying nothing
- A saved announcement that used a personality you later removed opens on Default instead of breaking
- Push your announcements again after changing the list. Each script carries its own copy of the personalities

## 2.10.3 - 2026-11-07

- **Scrolling is now a checkbox, not a style.** Style is back to Text or Rotating list, with **Scroll when it doesn't fit the box** underneath. On a rotating list, each item still fades in and out, and an item taller than the card scrolls while it is showing. On a text card, long text scrolls instead of shrinking. A "characters that fit on one line" setting tunes when it kicks in
- The separate Scrolling style from 2.10.2 is removed; a card saved with it becomes a rotating list with scrolling on. The show / hide switch is unchanged

## 2.10.2 - 2026-11-07

- **Scrolling dashboard card.** A new card style that scrolls a long list (or plain text) upward, like a news roundup. It uses the same field picker as the rotating list (title, text, small), plus scroll speed, card height and item height. It only scrolls when the content is taller than the card
- **Show / hide switch for any card.** Pick an `input_boolean` and the card (text, rotating or scrolling) is wrapped in a conditional card so it only shows while that switch is on. Works with Copy card and Copy all cards

## 2.10.1 - 2026-11-07

- **Rotating list dashboard card: pick what it shows.** Each field of your items can be shown as a Title (bold), Text, Small (dim) or not at all, with seconds per item and card height. It starts from the fact's own fields (for example name and info) instead of the old birthdays-only layout
- Fixed the list card reading nothing when the list was named `items` (it clashed with a built-in name). It now reads the list by key and survives a bad file

## 2.10.0 - 2026-11-07

- **Facts are now ONE automation, not a script plus an automation.** A new fact is pushed as a single Home Assistant automation: its triggers (every N minutes or hours, when an entity changes, only when someone is home), then the steps that ask the AI and publish to MQTT. No script is created. With no schedule it has no triggers, and **Run now** starts it
- **New format: A data list (JSON).** For lists like notable birthdays. Name the list (for example `birthdays`), say how many items, and add the fields each item has (text, number or yes / no). The automation reads the AI's JSON safely (code fences are stripped, a bad answer publishes nothing), drops items that fail an optional **Only keep items where** test, sorts them, trims to your count and publishes `{"birthdays": [...]}`
- New presets **Daily birthdays (JSON list)** and **Blank list (JSON)**. The Helper can also suggest the JSON format and its fields
- **Test** shows how many items came back and the JSON that would be published
- Older facts made as a script plus a schedule keep working. Open one and tap **Switch to a single automation**, then push: the old script and its `_auto` schedule are removed (only ones this add-on made)
- Deleting a single-automation fact removes its automation from Home Assistant (only if this add-on made it). Pushing over an automation this add-on made no longer saves a backup copy each time
- Announcements are unchanged

## 2.9.0 - 2026-11-07

- **Edit imported automations and scripts with fields, no YAML needed.** An imported automation now opens as cards: Settings, When it runs (every so often, at a time, when something changes and more), Only if, and What it does. The steps have their own fields: Ask the AI (task name, AI entity, instructions, answer name), Save to a file (path and what to save, with a Use my folder button) and Set variables. Add, remove and reorder anything. Imported scripts get the same editor
- Anything without a field (for example `to: null` on a trigger, or an `if` step) stays in a **More settings** YAML box on that item, so nothing is lost
- A **Full YAML (advanced)** box stays below, and the fields and the YAML always match. Editing with the fields tidies the YAML layout, and what it does stays the same
- **Copy dashboard card.** Every fact has a Dashboard card section and a **Copy card** button in the list, and **Copy all cards** makes one vertical stack. It writes the glass-style card (title from the first `#` line, font size by length) for the sensor that reads the fact's file. A Rotating list style fades through a JSON list, like birthdays. The sensor defaults to `sensor.read_<file name>` and you can change it
- Ships its own copy of js-yaml (MIT licence) so the fields work without internet

## 2.8.0 - 2026-11-07

- **Import a whole automation as a fact.** Import my script now also takes an automation that does everything itself (asks the AI, then saves the result), like a daily birthdays automation. Paste the YAML (a single automation, a `- id:` item from `automations.yaml`, or one under `automation:`), or leave the box empty and pick one from the **Automation** dropdown. It is kept exactly as written and you edit the YAML in the editor
- If a pasted automation has the same name as one already in Home Assistant, it takes that one over, so pushing updates it instead of making a duplicate. A copy of the old one is saved first
- **Choose where the text file goes.** The editor lists every `topic:` in your automation as a field you can change, with a **Use my folder** button
- **New add-on option: Facts file path** (Configuration tab). Sets the MQTT folder for all facts, for example `file_reader/overwrite/`. When set, it wins over Facts > Settings, which then shows it as locked. Blank keeps the old behavior
- Automation-only facts have **Run now** (triggers the automation, skipping its conditions) and show whether the automation is on. Deleting one only forgets it here and never deletes it from Home Assistant

## 2.7.0 - 2026-11-07

- **Facts can keep your own automations.** Each fact now has a **Your own automation** card. Load an automation you already have from a dropdown (or paste YAML) and it is kept exactly as written and pushed with the fact's script. It works for generated facts and for imported scripts
- **Import my script** has a new **Automation that runs it** dropdown, so a script and its automation come in together
- Pushing over an automation that already exists saves a copy of the old one first, in `/data/automation_backups` inside the add-on
- Your own automations are never deleted by this add-on. Only the generated `<script id>_auto` schedule is removed when you turn the schedule off
- Library cards show whether your automation is in Home Assistant and on or off. Automations defined only in YAML files (no UI id) cannot be loaded, because Home Assistant cannot edit them from here

## 2.6.0 - 2026-11-07

- **New Facts tab**, next to Announcements. Make AI-written facts that are saved to a text file over MQTT (default topic prefix `file_reader/overwrite/`), such as a random trivia fact, a dark history fact, a music fact about an artist, or a fact about a city
- Same workflow as Announcements: **My facts** library (Edit, Run now, Duplicate, Delete, Update all), an editor with a test panel, a Helper tab that writes the instructions and random lists for you, Settings, and Import my script
- **Random lists** (topic, angle, genre, decade, anything you name) are picked on every run and told to the AI, with an optional random seed. Formats: just the fact, a title and the fact (`Title ||| fact`, split by the script), or a short list. Optional heading above the fact
- Rules you can switch on or off: real and verifiable, go obscure, keep the household out, don't repeat the last fact (reads your file sensor)
- **Optional schedule**: every N minutes or hours, and/or when an entity or attribute changes, only when someone is home. It is a separate automation (`<script id>_auto`) that this add-on creates, updates and removes
- Facts share the AI Task and data sources with Announcements, and are included in Backup and Restore
- Shared data-source code moved into `sources.js`; Announcements behaves the same

## 2.5.0 - 2026-11-06

- **Import your own script.** On **My announcements**, tap **Import my script** and paste any Home Assistant script (YAML). It works with just the script, the script with its id on top (as in `scripts.yaml`), or only the list of steps. You can also load a script that already exists in Home Assistant from a dropdown
- Imported scripts are kept **exactly as you wrote them** and get their own editor with the YAML, a name field (it keeps the `alias:` line in step), **Check YAML**, Save, **Save and push**, Run saved script and Copy YAML. They also work with Duplicate, Delete, Update all and Backup
- Type the id of a script you already have to **take it over**: pushing replaces it and automations that call it keep working
- **Switch to the form tools** reads an imported script into the form (instructions, speakers, volume, personalities) so you can use the helper and the test panel. Your own prompt is kept word for word. Anything the form does not cover is dropped when you push, so leave without saving to keep the original

## 2.4.0 - 2026-11-06

- **Announcements are now a library.** Every announcement you make is saved inside the add-on (not in the Configuration tab, which is for options like paths and entities) and listed under **My announcements** with status, Edit, Run now, Duplicate and Delete
- Edit any announcement and push it again. The script id stays the same, so automations that call it keep working. **Save** keeps changes here only, **Save and push** updates Home Assistant
- Scripts this tool made before this version show under **Made earlier, in Home Assistant**. Open one and the form is rebuilt from the script
- **Update all in Home Assistant** re-pushes every announcement with your current Settings (for example after you change the speaker)
- Setups saved in your browser can be moved into the library with one tap
- Saved announcements are included in Backup and Restore
- Web UI redesigned: one look across Build, Announcements and Backup (light and dark), an editor with four clear steps and a test panel beside it, Settings grouped into cards with a save bar, and consistent buttons, status pills and messages
- Delete buttons now need a second tap, and a delete from Announcements can also remove the script in Home Assistant (only scripts made by this add-on)

## 2.2.1 - 2026-11-06

- Fix: updating from 2.1.1 failed with "unauthorized" because Home Assistant tried to download a prebuilt image that is not available. The add-on now builds on your Home Assistant instead, like SVG Maker

## 2.2.0 - 2026-11-05

- **SVG Maker is now its own add-on** (`svg_maker`) and its tab and `svg_*` options are removed here. Photo-to-SVG conversion crashed the tracer inside this add-on, so it now runs on its own Debian-based image
- This add-on no longer installs Pillow or vtracer, so it builds faster and is smaller
- Everything else (Build, Announcements, Backup) is unchanged

## 2.1.1 - 2026-11-03

- Fix: converting a photo to SVG could crash the whole add-on (the panel then showed 503 Bad Gateway). Tracing now runs in a separate process, so a crash only fails that one conversion and shows a clear error

## 2.1.0 - 2026-11-03

The add-on is now **Creator & AI Builder** (same slug, so upgrading in place keeps everything).

- New **SVG Maker** tab with everything from SVG Maker 1.4.0: crop editor (drag, pinch, zoom; circle, rounded, square, full), auto-crop suggestion, auto-enhance, color or black and white tracing, detail slider, Save locally / Download / Both, icon-friendly names, black and white icons that follow Home Assistant colors, unique clip ids, temp-folder auto-save with optional auto-delete, name-conflict handling and HA `/local/` URLs
- SVG Maker options are now `svg_*` options (`svg_output_path`, `svg_temp_path`, `svg_auto_delete_temp`, `svg_auto_delete_after_days`, `svg_filename_style`, `svg_on_name_conflict`, `svg_default_mode`, `svg_default_detail`, `svg_path_style`, `svg_max_image_dimension`, `svg_max_upload_mb`, `svg_icon_names`, `svg_bw_follow_theme`, `svg_crop_editor`, `svg_auto_crop`, `svg_crop_shape`, `svg_crop_padding`, `svg_output_size`, `svg_auto_enhance`) with the same defaults. Copy over any you changed in the old add-on
- New **Backup** tab: save a backup to, and import a backup from, the new `backup_path` option (a folder or a single `.json` file). Imports save a safety copy first. New `backup_keep` option
- New `log_level` option (from SVG Maker) now applies to the whole add-on
- The add-on now maps `/share`, `/media`, `/backup`, `/ssl` and its own config folder as well, so SVG and backup paths can point there
- Option names and descriptions now show in the Configuration tab (new `translations/en.yaml`)
- Tab bar scrolls sideways on narrow screens

## 2.0.0 - 2026-11-03

AI Builder and Announcement Maker are now one add-on.

- New **Announcements** section with everything from Announcement Maker 0.4.0: info sources, personalities, TTS / Alexa / phone output, test before saving, helper tab, settings with entity pickers, export/import
- New Build / Announcements switch at the top of the panel; each page stays loaded while you switch
- One shared AI task entity, one Home Assistant connection, one sidebar entry
- Pushed announcements show in "Made so far"
- New options `ha_token`, `ha_url` and `helper_ai_task_entity` (all optional, from Announcement Maker)
- Only the Home Assistant ingress gateway can reach the web server (Builder previously accepted any caller on the add-on network)
- Same slug (`ai_builder`), so upgrading in place keeps your template entities and history. Announcement Maker settings do not carry over; use Export in the old add-on and Import here

## 1.1.1 - 2026-11-01

- Fix: generated add-ons failed to build on aarch64 ("no match for platform in manifest") because the AI used an amd64 base image
- The AI is now told what works on this system (base image, run.sh, config.yaml rules, valid folder maps, template and code gotchas)
- Add-ons are auto-repaired before creation, with each fix shown; stricter config.yaml checks
- Fix: the add-on's own config used an invalid map name; it is now `all_addon_configs`

## 1.1.0 - 2026-11-01

- New types: scenes, AppDaemon apps, pyscripts, blueprints and full add-ons
- Edit existing scenes, AppDaemon `.py` files, pyscript files and local add-ons
- Python syntax checks and add-on `config.yaml` checks before anything is written; warns about the missing `init: false` crash
- Existing files are never overwritten without confirmation, and overwritten files are backed up to `/data/backups`
- New `appdaemon_apps_dir` option
- The add-on now maps `/addon_configs` and `/addons`

## 1.0.2 - 2026-10-20

- New `template_file` option: choose where template sensors are written (default stays `ai_builder/package.yaml`)
- Setup banner now recognizes `!include_dir_named`-style folder includes and shows your configured path

## 1.0.1 - 2026-10-20

- Fix: add-on failed to start with "s6-overlay-suexec: fatal: can only run as pid 1" (set `init: false`)

## 1.0.0 - 2026-10-20

First release.

- Sidebar web UI: describe what you want, review it, create it
- Builds automations, scripts, template sensors and binary sensors, and helpers
- Multiple items from a single request, with a "Create everything" button
- Edit existing automations, scripts, and the template entities it manages
- Live preview of template sensor values
- Flags entity IDs that don't exist in your Home Assistant
- Revise box and "Ask AI to fix it" after a failed create
- "Made so far" tab with history and template entity deletion
- Options for the AI task entity and request timeout
