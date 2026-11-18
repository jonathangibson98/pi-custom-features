<!-- docs:header (generated, edit .github/docsgen) -->
# Sleep Tracker

![Version](https://img.shields.io/badge/dynamic/yaml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fjonathangibson98%2Fpi-custom-features%2Fmain%2Fsleep_tracker%2Fconfig.yaml&query=%24.version&label=version&color=41BDF5&logo=homeassistant) ![Architectures](https://img.shields.io/badge/arch-aarch64%20%7C%20amd64-informational) ![Sidebar](https://img.shields.io/badge/sidebar-ingress-success) ![Builds locally](https://img.shields.io/badge/image-builds%20on%20device-lightgrey?logo=docker) ![MQTT](https://img.shields.io/badge/MQTT-optional-660066?logo=mqtt) ![AI Task](https://img.shields.io/badge/AI-ai__task-8A2BE2?logo=googlegemini)

> Knows who's asleep by checking several signals at once (phone, Focus, lights, TV, motion), with MQTT sensors and sleep history.

## At a glance

| | |
|---|---|
| Version | `1.4.1` |
| Slug | `sleep_tracker` |
| Architectures | `aarch64`, `amd64` |
| Opens from | the sidebar (**Sleep Tracker**, ingress) |
| Extra ports | none |
| Folders it can reach | `share` |
| API access | Home Assistant API, Supervisor API |
| MQTT | optional (used when available) |
| Takes commands via `hassio.addon_stdin` | yes |
| Install | built on your device |

**You'll need:**

- The Home Assistant phone app (best signals)
- MQTT (Mosquitto add-on or your own broker)

## Contents

- [Setting someone up](#setting-someone-up)
- [How it decides](#how-it-decides)
- [Entities](#entities)
- [Configuration tab](#configuration-tab)
- [Backups](#backups)
- [AI help](#ai-help)
- [Configuration reference](#configuration-reference)
- [Help and feedback](#help-and-feedback)
<!-- /docs:header -->

Tracks whether the people you pick are asleep. One signal on its own lies: a phone on the charger doesn't mean someone's
asleep, and a light left on doesn't mean they're awake. So it checks several signals at once and only calls it when enough
of them agree, for long enough.

Open **Sleep Tracker** in the sidebar to set everything up. The **Configuration** tab only has the check interval, how long
history is kept and optional MQTT settings.

## Setting someone up

1. Under **Track someone**, pick a person and tap **Add and set up**.
2. Their phone signals are suggested straight away. Pick their bedroom under **Bedroom area** and tap **Suggest signals** to add
   the lights, TVs and speakers, and motion sensors in that room.
3. Check the signals, change anything you want, and tap **Save**.

### What gets suggested

| Signal | Sleepy when | Weight |
|---|---|---|
| Phone charging (`sensor.<phone>_battery_state`) | Charging or Full | 2 |
| Phone Focus (`binary_sensor.<phone>_focus`, iPhone) | on | 3 |
| Phone not moving (`sensor.<phone>_activity`) | Stationary | 1 |
| Phone sleep confidence (Android) | above 70 | 3 |
| Phone screen (`binary_sensor.<phone>_interactive`, Android) | off | 2 |
| Bedroom lights | all off. **Must be true** | 2 |
| Bedroom TV / speakers | not playing | 1 |
| Bedroom motion sensors | no motion for 10 minutes | 1 |

The phone sensors come from the Home Assistant Companion app. They're found through the phones attached to the person
(**Settings → People**). On iPhone, turn on the **Focus** sensor in the Companion app (**Settings → Companion App → Sensors**),
and give the app Focus permission, so Sleep Focus counts.

### Signals

Each signal looks at one or more entities and says **sleepy** or **awake**:

- **is one of / is not one of**: the state (or an attribute) matches one of the values you list. Not case sensitive.
- **is below / is above**: a number.
- **hasn't changed for**: nothing changed for that many minutes (a motion sensor that has been quiet).
- With several entities, pick **all of them** (every light off) or **any of them**.
- **Weight** 1–5: how much it counts.
- **Must be true**: they can't fall asleep while it's false, and they wake up **the moment** it turns false. Good for "bedroom
  lights off": turn a light on at 3am and they're awake right away.
- Entities that are unavailable or unknown are left out of the maths instead of counting as awake.

## How it decides

- **Sleep confidence** is the share of the weight that says sleepy right now (0–100%).
- **Falling asleep:** confidence stays at or above **Falls asleep at** (70%) for **Must stay sleepy for** (15 min), every
  must-be-true signal is true, and it's inside **night hours**. The time they fell asleep is dated back to when the signals
  first agreed, so the waiting time doesn't cut the night short.
- **Waking up:** confidence stays under **Wakes below** (40%) for **Must stay awake for** (5 min), or a must-be-true signal turns
  false (straight away).
- The gap between the two levels stops it flipping back and forth.
- **Bathroom trips:** back asleep within **Same night if back asleep within** (20 min) and it stays one night, with an
  interruption counted. Asleep shorter than **Ignore sleeps shorter than** (20 min) isn't saved.
- **Night hours** (default 8 PM to 12 PM) is a window, not a bedtime. Turn on **Count naps** to also catch daytime sleep.
  Naps are kept apart from nights.
- **Only when they're home:** leaving home means awake.

### Fixing it by hand

**Mark asleep now** starts their sleep right away, ignoring the signals until they agree. **Mark awake now** ends it, and the
signals are ignored for 30 minutes so it doesn't put them straight back to sleep. Both are also buttons in Home Assistant.
Tap **×** next to a night under **Recent** (twice) to delete a wrong one.

## Entities

Made over MQTT on a **Sleep Tracker** device (needs the Mosquitto broker add-on, or set your own broker in Configuration).
`<name>` is the person's id, for example `alex`.

| Entity | What |
|---|---|
| `binary_sensor.<name>_asleep` | on while asleep. Attributes: status, since, confidence, fell_asleep, asleep_minutes, interruptions_tonight, and each signal |
| `sensor.<name>_sleep_status` | Awake, Falling asleep, Asleep, Away or Not tracking |
| `sensor.<name>_sleep_confidence` | 0–100% |
| `sensor.<name>_last_sleep` | hours of the last night. Attributes: went_to_sleep(_time), woke_up(_time), minutes, in_bed_minutes, interruptions, awake_minutes, average_7_nights_hours, naps_today_minutes, history (last 14) |
| `button.<name>_mark_asleep` / `button.<name>_mark_awake` | the same as the buttons in the app |
| `binary_sensor.everyone_asleep` | on when everyone tracked who's home is asleep. Attributes: home, asleep, awake |

`last_sleep` changes as soon as they wake. Its `still_settling` attribute is true while the 20 minutes to lie back down
haven't passed yet.

### Example automations

Lock up and turn everything off once the house is asleep:

```yaml
triggers:
  - trigger: state
    entity_id: binary_sensor.everyone_asleep
    to: "on"
    for: "00:05:00"
actions:
  - action: script.turn_off_lights_and_lock_door
```

Good-morning announcement when Alex gets up:

```yaml
triggers:
  - trigger: state
    entity_id: binary_sensor.alex_asleep
    from: "on"
    to: "off"
conditions:
  - condition: time
    after: "05:00:00"
    before: "12:00:00"
actions:
  - action: notify.mobile_app_jons_iphone
    data:
      message: >
        Morning. You slept {{ states('sensor.alex_last_sleep') }} hours
        ({{ state_attr('sensor.alex_last_sleep', 'went_to_sleep_time') }} to
        {{ state_attr('sensor.alex_last_sleep', 'woke_up_time') }}).
```

## Configuration tab

Every option is listed with its default in the [Configuration reference](#configuration-reference) at the end of this page.

Settings, the current state and history are kept in the add-on's own storage, so they survive restarts and updates and are
part of Home Assistant backups.

## Backups

Tap **Backups** at the bottom of the add-on page to back up, download or restore. A backup is a `.zip` with your people, their signals and settings, the current sleep state and the sleep history, plus everything in the Configuration tab.

| Option | Default | What |
|---|---|---|
| `backup_path` | `/share/addon_backups/sleep_tracker` | Where backups go, inside `/share`, `/media` or `/homeassistant`. A folder keeps several dated backups. A path ending in `.zip` keeps one file that is replaced each time |
| `backup_every` | `daily` | `off`, `daily` or `weekly` automatic backups |
| `backup_keep` | `10` | How many backups to keep in the folder. Older ones are deleted |

- **Back up now** makes one straight away. **Download** saves one to your phone or computer.
- **Restore** (tap twice) first saves a safety copy (`..._pre-restore_...zip`, the newest 3 are kept), puts the Configuration tab settings back, and restarts the add-on. The data is put back as it starts, before it reads anything.
- **Restore from a file** takes a backup `.zip` you downloaded, for example to move to another Home Assistant.
- A backup from a different add-on is refused. The page only works from the Home Assistant sidebar, never on the add-on's own ports, because backups include its settings.
- Backups also hold any passwords or API keys from the Configuration tab, so treat the backup folder like your secrets.

## AI help

**✨ Sleep insights**: one tap on a person's card and your Home Assistant AI Task reads their recent nights and explains them in plain words (average sleep, how regular bed and wake times are, weekdays vs weekends, wake-ups) with a tip or two.

It uses a Home Assistant AI Task entity (`ai_task_entity` on the Configuration tab; empty uses the first one). The data shown is sent to your AI provider when you tap it.

<!-- docs:config (generated from config.yaml) -->
## Configuration reference

Every option on the add-on's **Configuration** tab, with its default. Change them there, then restart the add-on.

| Option | Default | Type | What it does |
|---|---|---|---|
| `ai_task_entity` | *(empty)* | text, optional | **AI Task entity (optional).** The Home Assistant AI Task entity behind the ✨ AI button. Leave empty to use the first one Home Assistant has. |
| `check_seconds` | `30` | whole number (10–300) | **Check every (seconds).** How often everyone's signals are checked. |
| `keep_days` | `90` | whole number (0–3650) | **Keep sleep history for (days).** Older sleeps are deleted. 0 keeps everything. |
| `backup_path` | `/share/addon_backups/sleep_tracker` | text | **Backup folder.** Where backups are saved, inside /share, /media or /homeassistant. A folder keeps several dated backups. A path ending in .zip keeps one file that is replaced each time. Open Backups in the add-on page to back up, download or restore. |
| `backup_every` | `daily` | one of: `off`, `daily`, `weekly` | **Automatic backups.** How often a backup is made by itself (off, daily or weekly). |
| `backup_keep` | `10` | whole number (1–100) | **Backups to keep.** The newest this many backups are kept in the folder, older ones are deleted. |
| `wallpaper` | *(empty)* | text, optional | **Wallpaper.** Background image for this add-on's web UI. Leave empty to use your Home Assistant theme's wallpaper, "none" for no wallpaper, or an image: put it in /config/www and enter its file name (pic.jpg) or /local/pic.jpg, or a full https:// link. |
| `mqtt_host` | *(empty)* | text, optional | **MQTT host (optional).** Leave empty to use the Mosquitto broker add-on automatically. |
| `mqtt_port` | *(empty)* | port, optional | **MQTT port (optional).** Only used with a custom MQTT host. Defaults to 1883. |
| `mqtt_username` | *(empty)* | text, optional | **MQTT username (optional).** Only used with a custom MQTT host. |
| `mqtt_password` | *(empty)* | secret, optional | **MQTT password (optional).** Only used with a custom MQTT host. |
<!-- /docs:config -->

<!-- docs:footer (generated) -->
## Help and feedback

- **Logs:** the add-on's **Log** tab shows what it's doing and most errors in plain words.
- **Changes:** see the [changelog](CHANGELOG.md) (also on the add-on's **Changelog** tab).
- **Problems or ideas:** [open an issue](https://github.com/jonathangibson98/pi-custom-features/issues) and include the add-on version and the log.
- **Pages follow your theme:** every page in this repository picks up your Home Assistant theme and wallpaper automatically.
<!-- /docs:footer -->
