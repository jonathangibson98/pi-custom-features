# Release Tracker

Track anything with a release date and get told when it drops: TV shows, movies, games and DLC, albums and artists, celebrities, tech launches, merch drops, events, sales, or anything else you type in.

## What you can track

The **Add** tab has five choices.

| Choice | What it tracks | Where the dates come from | Needs |
|---|---|---|---|
| **TV & Movies** | Next episode or season premiere, and theater, digital, and physical movie dates | TMDB | Free TMDB key |
| **Games & DLC** | Games, plus their DLC and expansions | IGDB (Twitch) | Free Twitch Client ID and Secret |
| **Music** | An artist's next announced album, EP, or single, or one specific album | MusicBrainz | Nothing |
| **Celebrities** | An actor's or other public figure's upcoming movie and TV credits | TMDB | Free TMDB key |
| **Anything else** | Tech launches, merch drops, events, sales and deals, or anything with a date | You type it in | Nothing |

## Setup

1. Make a free account at [themoviedb.org](https://www.themoviedb.org), then go to Settings, then API, and request a key. Either the **API Key** or the long **API Read Access Token** works.
2. Start this add-on and open **Releases** in the sidebar.
3. In **Settings**, paste the key and save.
4. Go to **Add**, pick a kind, search for something, pick who cares about it, and tap **Track**.

Music and Anything else work without any key. Games need the extra keys described below.

## People

Manage everyone in **Settings, People**. Type a name and tap **Add**. Each person has **Rename** and **Remove** next to their name, and changes save right away.

- **Rename** moves all of that person's tags to the new name.
- **Remove** takes their tag off every tracked item.

When you add something, pick who is tracking it, or nobody. Tap a name on a card in the Tracking tab to change it later. This works for every kind of item.

Who tracks what shows up in the `by_person` attribute of the release sensor (see below). Renaming or removing someone updates it right away.

## The Tracking tab

Everything you track is grouped by kind: TV & Movies, Games & DLC, Music, Celebrities, Tech releases, Merch drops, Events, Sales & deals, and Other. Once you track more than one kind, filter buttons appear at the top so you can look at just one group. Each group is sorted soonest first.

Items with no date yet show **TBA** (custom items) or their kind instead of a countdown.

## Music

On the **Add** tab choose **Music** and search an artist or album.

- **Follow an artist** and the card shows their next announced album, EP, or single. When something new is announced it appears on its own.
- **Track an album** to follow just that one release.

Music data comes from [MusicBrainz](https://musicbrainz.org), a free community database. It only lists a release once someone has added it, so a brand new announcement can take a while to show up. For those, add it under **Anything else** with the date you know.

If only a month or a year is known, the card says "expected" and has no countdown until an exact date is added.

## Celebrities

Choose **Celebrities** and search a name. The card shows that person's next upcoming movie or TV credit, and the sensor keeps their next several dates. This uses the same TMDB key as shows and movies.

## Anything else (tech, merch, events, sales)

Choose **Anything else** for anything that does not come from a search. Fill in:

- **What kind of thing is it?** Tech release, Merch drop, Music, Celebrity, Event, Sale / deal, or Other.
- **Name**, like "Pixel 11 launch".
- **Date** (leave empty if it has not been announced) and an optional **Time**, like "10 AM ET".
- **Note**, like where to buy or a drop code.
- **Link** and **Picture link** (both optional, and must start with `http://` or `https://`).

Tap **Edit** on the card to change any of it later, for example to add the date once it is announced. A custom item whose date has passed shows "Date passed" and stays in your list until you remove it.

## The release sensor

Everything comes through **one** sensor: `sensor.release_tracker_releases`. All kinds are in it.

The state is how many releases land inside your window (Settings, Updates). The details are attributes:

| Attribute | What it is |
|---|---|
| `items` | The list of releases inside the window, soonest first (up to 30). Each has `title`, `type`, `date`, `days_until`, `label`, `time`, `note`, and `people`. |
| `next_title`, `next_date`, `next_days_until`, `next_label`, `next_type` | The very next thing coming out, even if it is past the window. |
| `today_count`, `today` | How many things drop today, and their titles. |
| `by_type` | How many releases inside the window there are for each `type`. |
| `by_person` | For each person, the titles of their releases inside the window. |
| `window_days`, `tracked_count` | Your window setting, and how many items you track. |

`type` is one of `TV`, `Movie`, `Game`, `Album`, `Artist`, or `Celebrity` for searched items. For items you typed in, it is the kind you picked: `Tech release`, `Merch drop`, `Music`, `Celebrity`, `Event`, `Sale / deal`, or `Other`.

If you updated from an older version, the old sensors (`next_release`, `upcoming`, `releasing_today`, `upcoming_games`, and the per-person ones) are removed from Home Assistant on startup. They may linger as greyed-out entries in the entity list until you delete them there.

## Games and DLC

Games use a different free service (IGDB, run by Twitch), so it needs its own keys.

1. Go to [dev.twitch.tv/console](https://dev.twitch.tv/console) and log in. Twitch makes you turn on two-factor login first if you have not.
2. Tap **Register Your Application**. Name it anything, set OAuth Redirect URL to `http://localhost`, pick **Application Integration** as the category, and create it.
3. Open **Manage** on the new app. Copy the **Client ID**, then tap **New Secret** and copy that too.
4. In this add-on go to **Settings**, paste both under **Games (IGDB)**, and save.
5. On the **Add** tab choose **Games & DLC**, search, and tap **Track**.

Track the main game and any DLC or expansion IGDB knows about shows up on its own. The card shows whichever thing drops next, like `DLC: Skin Pack`. You can also search a DLC by name and track it alone.

## Automations

Notify when something drops today:

```yaml
alias: Release drops today
trigger:
  - platform: time
    at: "08:00:00"
condition:
  - condition: template
    value_template: >
      {{ state_attr('sensor.release_tracker_releases','today_count') | int > 0 }}
action:
  - service: notify.notify
    data:
      title: Dropping today
      message: "{{ state_attr('sensor.release_tracker_releases','today') | join(', ') }}"
```

Notify about merch drops only, one day ahead:

```yaml
alias: Merch drop tomorrow
trigger:
  - platform: time
    at: "09:00:00"
condition:
  - condition: template
    value_template: >
      {{ state_attr('sensor.release_tracker_releases','items')
         | selectattr('type','eq','Merch drop') | selectattr('days_until','eq',1) | list | count > 0 }}
action:
  - service: notify.notify
    data:
      title: Merch drop tomorrow
      message: >
        {{ state_attr('sensor.release_tracker_releases','items')
           | selectattr('type','eq','Merch drop') | selectattr('days_until','eq',1)
           | map(attribute='title') | join(', ') }}
```

Change `'Merch drop'` to `'Tech release'`, `'Album'`, `'Event'`, or any other `type` above.

## Settings

Settings are split into cards. Tap a card to open it. Each card with a Save button saves on its own, and a badge on the card shows whether it is ready.

- **People**: add, rename, and remove who tracks things. Saves right away.
- **Movies, TV & Celebrities**: your TMDB key, and the two-letter region used for movie dates (US, GB, CA...).
- **Games (IGDB)**: your Twitch Client ID and Secret.
- **Music & custom items**: nothing to set up. Explains where music dates come from.
- **Updates**: how often it checks for changes (6 hours is plenty), and the window for the "upcoming" counts.
- **Home Assistant (MQTT)**: leave blank to use the Mosquitto add-on. Fill it in if your broker lives somewhere else, like another Pi.
- **Backup**: see below.

## Backup

Backups are saved as files in the Home Assistant **share** folder, so you can grab them from Samba, SSH, or the File editor.

- **Save to folder**: any folder under `/share/`. The default is `/share/release_tracker`. It is created for you.
- **Automatic backups**: Off, Daily, or Weekly. **Back up now** saves one right away.
- **Keep the newest**: older automatic backups are deleted past this number.
- **Include API keys and passwords**: off by default. Turn it on only if you want a backup that restores your keys too.
- **Saved backups**: lists what is in the folder. Tap **Restore** on one to replace your tracked list, tags, and settings with it. A safety copy of what you had is saved first and is never deleted automatically.

A backup holds your tracked list (including music, celebrities, and anything you typed in), who tags what, and your settings. If it was saved without keys, restoring leaves your current keys alone.

Backups need the share folder to be available to the add-on. After updating from an older version, restart the add-on. If the Backup card says the share folder is not available, reinstall or rebuild the add-on so the new access takes effect.

## Dashboard card

```yaml
type: markdown
title: Coming Soon
content: |
  {% for i in state_attr('sensor.release_tracker_releases','items') %}
  **{{ i.title }}** ({{ i.type }}): {{ i.label }}, {{ i.date }} ({{ i.days_until }}d)
  {% endfor %}
```

Show only one person's releases:

```yaml
type: markdown
title: MJ's releases
content: |
  {% for i in state_attr('sensor.release_tracker_releases','items') if 'MJ' in i.people %}
  **{{ i.title }}**: {{ i.label }}, {{ i.date }}
  {% endfor %}
```

## Notify one person

```yaml
alias: MJ release day
trigger:
  - platform: time
    at: "08:00:00"
condition:
  - condition: template
    value_template: >
      {{ state_attr('sensor.release_tracker_releases','items')
         | selectattr('days_until','eq',0) | selectattr('people','contains','MJ') | list | count > 0 }}
action:
  - service: notify.notify
    data:
      title: Dropping today
      message: >
        {{ state_attr('sensor.release_tracker_releases','items')
           | selectattr('days_until','eq',0) | selectattr('people','contains','MJ')
           | map(attribute='title') | join(', ') }}
```

Swap `notify.notify` for the notify service of whoever should get it.

## Things to know

- Game dates come from IGDB, also crowd-sourced. Dates are the earliest across all platforms. If only a month or year is known it says "expected" and gets no date.
- Movie and TV dates come from TMDB, which is crowd-sourced. TV air dates can be wrong or late, and streaming shows often have no date until shortly before release.
- Music dates come from MusicBrainz, also crowd-sourced, and only appear once someone has added the release there.
- Celebrity dates are their upcoming credits in TMDB, so a tour, a product, or an appearance will not show up. Add those under **Anything else**.
- Shows with no announced next episode say "No date announced yet" and get no date.
- A movie that is already out stays in your list, but it will not show up as upcoming.
- Everything is stored in the add-on's own data folder and is included in Home Assistant backups. The Backup card makes extra copies you can reach in the share folder.

## Troubleshooting

- **No entities show up**: check that MQTT is set up in Home Assistant. On the add-on's Settings tab, it should say "Connected to a broker."
- **Search says add your key**: paste the TMDB key in Settings and save. This covers TV, movies, and celebrities.
- **Games search says add your Twitch keys**: paste both the Client ID and Secret in Settings and save.
- **Music search says MusicBrainz is busy**: it allows about one request per second. Wait a minute and try again.
- **A new album or product is missing**: it may not be in the database yet. Add it under **Anything else** with the date.
- **Wrong or missing date**: hit **Refresh now**. If the source itself is wrong, there is nothing to fix on this end.
