"""What the AI needs to know about how this add-on builds and runs announcements and facts.

Used by the Check with AI button and by Fix selected with AI, so the AI judges and fixes things the way the add-on
really works instead of guessing. Keep it in step with www/announcements.js and www/facts.js (the builders)."""

COMMON = """HOW THE ADD-ON WORKS (read this first)
- The owner never edits YAML here. The editor keeps a set of SETTINGS (the JSON you may be shown) and rebuilds the Home Assistant YAML from them every time. So to fix something, change a SETTING. Editing the YAML text only makes sense for a "raw" item, a script the owner pasted in, which is kept exactly as written.
- DATA SOURCES are chosen in Settings (weather, calendar, news, household info, locations, entities...). Each ticked source becomes a variable named src_<id> that is put into the AI's instructions under the source's label. The setting "src" lists the ticked source ids. A source's own entities and templates live in Settings, not in the item, so problems inside a source cannot be fixed from the item.
- The AI Task is the entity that writes the text. Setting "ai" blank means use the default AI Task from Settings. The call is ai_task.generate_data and the answer is read from its response (".data").
- The instructions sent to the AI are built in this order: current time, each data source under its label, "YOUR TASK:" (the setting "task", the owner's plain-words instructions), then style and length rules, then the output-format rule. The owner only writes "task"; the rest is generated. So make "task" clear and specific: what to say, what to include, any condition ("only mention the calendar if something is on").
- Words like SET_ME in the YAML mean a required Settings choice (AI Task, text-to-speech engine, speaker) is empty. That is fixed in Settings, not in the item.
- Everything is a Home Assistant script or automation. Nothing is saved or pushed to Home Assistant until the owner presses Save and push, so fixes made in the editor are safe to review first.

THE SCHEDULE (setting "auto", same for announcements and facts)
- auto.on switches the schedule on. When it is off there are no triggers and the item only runs when started by hand or by another automation.
- Triggers (any of them starts a run): every (a number) with unit "minutes" (1-59) or "hours" (1-23); at (a clock time "HH:MM" every day); watch (an entity id; watchAttr an attribute to watch, blank = its state; watchFor seconds it must hold; watchTo a state it must change to, blank = any change); atMore (extra clock times "HH:MM" every day); sunEvent "sunrise" or "sunset" with sunOffset in minutes, negative = before. A schedule with none of these never runs.
- Conditions (ALL must be true when a trigger fires; they are checked only at that moment): win2 {from,to} a second time window used with from/to (either window may match); months a list of month numbers 1-12 (empty = all); each only[] row is {entity, op, state, attr, for}: op "is", "not", "above" or "below" (above/below compare a number, attr names an attribute instead of the state, for = minutes it must have held, only with "is"); home (a list of entity ids) with homeMode "any" (at least one is home), "all" (every one is home) or "none" (nobody in the list is home). person and device_tracker entities count when state is home; a zone counts when someone is in it; any other entity counts when on. from/to ("HH:MM") a time window that may cross midnight; days a list of mon,tue,wed,thu,fri,sat,sun (empty = every day); sun "" or "day" (sun above the horizon) or "night" (below); only a list of extra checks {entity, state, not} meaning the entity is (or with not true, is not) that exact state; gap the minimum minutes since this automation last ran (0 = no limit).
- Typical mistakes: conditions that can never all be true (for example homeMode "none" with a people list the owner is always in; a time window that does not include the trigger time; "at" 06:00 with a window starting 08:00); an "every" so small it runs constantly with no gap; a watch entity that changes constantly with no gap; people that do not exist.
"""

ANNOUNCEMENT = """HOW AN ANNOUNCEMENT RUNS
The script does these steps in order: set current_time; load each ticked data source into src_<id>; ask the AI Task to write the text; read the answer (music keeps playing until this point); if it will speak and "pause" is true, pause any music player that is playing; set the optional "talking" flag on; wait 3 seconds and set the speaker volume (setting "vol", 0 to 1); optionally save the text to an MQTT file for a dashboard card; optionally turn on a dashboard-card switch; deliver (speak with text-to-speech, send to Alexa devices, send phone notifications); wait for the speech to finish; turn the talking flag off and resume paused music; optionally hide the card.
ANNOUNCEMENT SETTINGS (use exactly these names)
- name: the script's name (never change it).
- src: list of data source ids that are ticked.
- task: the owner's instructions to the AI, plain words.
- len: maximum characters the AI is told to stay under (a spoken announcement of 1000 is about 1.5 minutes).
- outs: where it goes. "tts" = speak on the main speaker; "a:<name>" = an Alexa device; "n:<name>" = a phone notification. Outputs can only be switched off here, never added.
- usePers (true/false): choose the voice by a personality dropdown in Home Assistant. pers: an object of personality name -> style text, one = the personality used when usePers is false. The style text is how the AI should sound.
- json: true when a phone notification is ticked or fields are used; the AI then answers as JSON ({"speech": ..., "notification": ...}). Do not change this by hand.
- vol: speaker volume 0 to 1. pause: pause and resume music around the speech.
- cardSw: the input_boolean that shows a dashboard card while it runs (do not change). cardWhen "talk" (turn on as it speaks) or "start" (turn on first); cardOff true to hide it after; cardHold extra seconds to keep it up.
- txt: optional saving of the text/fields to an MQTT file. Leave alone unless a problem is about it.
- ai: the AI Task for this item; "" means the default.
- auto: the schedule (see above).
GOOD "task" TEXT: says what to cover, in what order, what to skip, and any condition. Avoid: instructions that contradict the length or the output (asking for bullet lists or markdown, which are read aloud badly; asking for more than "len" allows); asking for data that no ticked source provides; asking it to repeat the data back.
"""

FACT = """HOW A FACT RUNS
A fact is by default ONE automation (setting "asAuto" true): its triggers and conditions come from the schedule and its actions are the steps below. Otherwise it is a script plus a small automation that calls it. The steps, in order: load ticked data sources into src_<id>; pick one random value from each random list ("picks") and a random seed; ask the AI Task for ONE fact; clean up the answer (strip code fences, quotes, markdown); publish it with mqtt.publish to the topic made from the MQTT prefix in Settings plus the file name ("file"), but only if the cleaned answer is not empty. A dashboard card (for example file_reader) shows the file.
FACT SETTINGS (use exactly these names)
- name: never change. src: ticked data source ids. task: the owner's instructions for the fact.
- picks: list of {name, items}. name is lowercase letters and underscores; items is TEXT with one option per line (6 to 20 is good). Each run picks one line per list and tells the AI, for example "TOPIC FOR THIS RUN: ...". Mention a list by name in "task" for it to matter. seed (true/false) adds a random number so repeats are less likely.
- style: "plain" (just the fact), "titled" (a title and the fact; titleHint says what the title is; heading is fixed text added above), "list" (count lines, one item per line), "json" (a data list; see fields).
- len: maximum characters of the fact part (per line for list); ignored for json.
- count: how many lines (list) or items (json).
- json style: listKey (the name of the list in the output), fields: list of {key, type, hint} where type is "text", "number" or "yesno" and key is lowercase letters and underscores; sortBy (field names, comma separated), sortDir "asc" or "desc", keepIf (a simple condition on fields), useDate (tell the AI today's date).
- real (only verifiable facts), obscure (avoid famous facts; skip = examples to avoid), noPeople (never mention the household), swear "none", "mild" or "rated", extra (extra rules for this fact only).
- avoidLast (true/false): tell the AI the previous fact so it does not repeat; lastEntity and lastAttr say where the previous fact is read (blank lastEntity = the default from Settings). It does nothing without a sensor that reads the fact file.
- file: the file name (blank = made from the name); a value with a slash is used as the full MQTT topic.
- ai: the AI Task for this item; "" means the default.
- auto: the schedule (see above). With auto.on false it never runs by itself.
GOOD FACTS: a "task" that names the kind of fact, plus picks lists that change the angle each run, plus avoidLast with a working sensor. Avoid: a "plain" style with instructions that ask for a title or several lines; "list" or "json" with a count the "task" contradicts; a "len" too small for the topic; no data in picks and no seed, so every run gives the same fact; avoidLast on with no sensor.
"""


def briefing(kind):
    return COMMON + "\n" + (FACT if kind == "fact" else ANNOUNCEMENT)


def context_text(sources, opts):
    """What this owner has set up, so ids and choices named in a fix are ones that exist."""
    srcs = "; ".join("%s = %s (%s)" % (x.get("id"), x.get("label", ""), x.get("type", "")) for x in (sources or [])[:60] if isinstance(x, dict)) or "none"
    o = opts or {}
    bits = ["data sources available (id = label (kind)): " + srcs,
            "default AI Task: " + (o.get("ai_task_entity") or "not set"),
            "speaker: " + (o.get("speaker") or "not set") + ", text-to-speech: " + (o.get("tts_entity") or "not set"),
            "Alexa targets: " + (", ".join(o.get("alexa_targets") or []) or "none"),
            "phone notification targets: " + (", ".join(o.get("notify_targets") or []) or "none"),
            "personalities: " + (", ".join(p.get("name", "") for p in (o.get("personalities") or []) if isinstance(p, dict)) or "none")]
    return "THIS OWNER'S SETUP:\n- " + "\n- ".join(bits)
