"""Hand-written summaries for each add-on. Everything else (versions, options, defaults) is read from config.yaml."""

REPO = "jonathangibson98/pi-custom-features"
RAW = "https://raw.githubusercontent.com/" + REPO + "/main"

ORDER = ["ai_builder", "photo_shuffle", "party_lights", "voice_chat", "personal_ai_speech", "pi_health_monitor",
         "release_tracker", "team_tracker_lite", "sleep_tracker", "work_hours", "zone_creator", "svg_maker"]

CATEGORY = {
    "ai_builder": "Build & create", "photo_shuffle": "Build & create", "svg_maker": "Build & create",
    "party_lights": "Fun & media", "voice_chat": "Voice & AI", "personal_ai_speech": "Voice & AI",
    "pi_health_monitor": "System", "release_tracker": "Tracking", "team_tracker_lite": "Tracking",
    "sleep_tracker": "Tracking", "work_hours": "Tracking", "zone_creator": "Build & create",
}

META = {
    "ai_builder": {
        "tagline": "Describe what you want in plain English and your Home Assistant AI builds it: automations, scripts, scenes, "
                   "helpers, template sensors, dashboards and cards. Also voice announcements, dashboard facts, text-file sensors and backups.",
        "features": [
            "**Build**: automations, scripts, scenes, helpers, template sensors, blueprints and more from a plain-English request, checked before anything is saved",
            "**Dashboards**: open any dashboard, ask for changes and see a live preview drawn with your real cards and theme at your screen's exact size (cast TV, Nest Hub, tablet, phone, or **My screens** read from Browser Mod sensors)",
            "**Does it fit?** measures the real page and **Make it fit** sends the overflow to the AI. Every save keeps the version before it",
            "**Cards**: make and edit single cards with a preview",
            "**Voice & facts**: AI announcements on a schedule or a dashboard switch, and rotating facts saved to sensors",
            "**Files** (formerly File Reader): text files as sensors over MQTT, updated from automations or the REST API",
            "**Backup**: one-click and scheduled backups of everything the add-on made",
        ],
        "needs": ["An `ai_task` entity (any AI integration that offers AI Task)", "MQTT (optional, for Files sensors)"],
    },
    "photo_shuffle": {
        "tagline": "Everything photos in one place: folder shuffles and Unsplash collections as image entities, one wallpaper for every "
                   "add-on page, a Photo Editor with AI tools, SVG Maker, and photo upload with AI analysis.",
        "features": [
            "**Folders** and **Unsplash** collections published as `image` entities over MQTT, shuffled on a timer",
            "**Wallpaper**: one background for every add-on page in this repository, with darken, lighten and blur",
            "**Photo Editor**: crop, adjust, filters and AI edits through your `ai_task` entity",
            "**SVG Maker**: trace photos into clean SVG icons, or have the AI draw a logo",
            "**Analyze**: upload one photo or a batch from your phone, let an AI describe each one (objects, scene, tags), and save it to a destination you tap",
            "Pictures move between tabs in one tap (edit a shuffle photo, set it as wallpaper, trace it as an icon)",
            "Resizes images for dashboards (default 1920 px, JPEG quality 85)",
        ],
        "needs": ["MQTT (Mosquitto add-on or your own broker)", "A free Unsplash access key (only for Unsplash)", "An `ai_task` entity (only for AI edits, logos and photo analysis)"],
    },
    "party_lights": {
        "tagline": "Music-synced lights, 25 light modes, color themes and 20+ party games, run from a phone-friendly page, a dashboard "
                   "dropdown, an automation or MQTT.",
        "features": [
            "**Music sync**: lights take their colors from the album art, plus an album-art brightness/color sensor for dashboards",
            "**25 light modes**: disco, chase, comet, ping pong, heartbeat, aurora, ocean, fireworks, lava lamp, shuffle and more",
            "**Color themes**: holidays, album art, team colors, your own, or AI colors from a description",
            "**20+ games**: freeze dance, red light green light, trivia, truth or dare, never have I ever, name that tune, power hour, shot caller, last call, light roulette, hot potato, dance battle…",
            "**Control it from anywhere**: a mode dropdown made for you, `hassio.addon_stdin`, or 8 simple MQTT entities (party, mode, colors, brightness, speed, game, quick hit, status)",
            "**Music sync checklist** shows exactly why the lights are or aren't following the music",
            "iPhone-first page with a bottom tab bar and pull-up settings sheets",
            "Lights are put back the way they were when the party ends",
        ],
        "needs": ["Color lights", "A TTS engine and speakers (optional, for announcements)", "MQTT (optional, for the Home Assistant entities)", "An `ai_task` entity (optional)"],
    },
    "voice_chat": {
        "tagline": "Hands-free voice conversation with any Home Assistant conversation agent, answered out loud on the speakers you choose.",
        "features": [
            "Talk from any phone or browser; the reply plays on one or several speakers, or in the browser",
            "Works with any conversation agent (Assist, OpenAI, Google, Ollama, Personal AI…), switchable on the page",
            "Hands-free mode with silence detection",
            "Household info and live entity values given to the AI as context",
            "Runs as an add-on or as a plain Docker container",
        ],
        "needs": ["A conversation agent, an STT and a TTS engine in Home Assistant", "HTTPS for the microphone (built-in self-signed port 8443, or Home Assistant's own HTTPS)"],
        "docker": True,
    },
    "personal_ai_speech": {
        "tagline": "Natural text-to-speech with emotion tags and local speech-to-text, as an OpenAI-compatible server for the Personal AI integration.",
        "features": [
            "Local **Kokoro** text-to-speech with `[happy]`, `[whisper]`, `[sad]`… emotion tags",
            "Local **faster-whisper** speech-to-text",
            "OpenAI-compatible `/v1/audio/speech` and `/v1/audio/transcriptions` on port 8880",
            "Optional proxy to OpenAI or another compatible server",
            "Test page in the sidebar",
        ],
        "needs": ["A 64-bit system, 4 GB RAM or more recommended", "About 120 MB download on first start", "The Personal AI integration (to use it from Home Assistant)"],
    },
    "pi_health_monitor": {
        "tagline": "A lightweight health check for the machine Home Assistant runs on, with plain-English fixes.",
        "features": [
            "CPU, temperature, memory, disk, load and uptime, refreshed every 5 seconds",
            "Raspberry Pi under-voltage and throttling, now and since boot",
            "Per add-on CPU and RAM (or per container when run in Docker)",
            "Health checks: storage wear, updates, backups, repairs, log errors and unavailable entities",
            "**Database**: which entities fill your recorder database the most",
            "AI fix tips through your `ai_task` entity",
            "Runs as an add-on or as a plain Docker container",
        ],
        "needs": ["Nothing extra", "An `ai_task` entity (optional, for fix tips)"],
        "docker": True,
    },
    "release_tracker": {
        "tagline": "Track anything with a release date and get told when it drops: shows, movies, games and DLC, albums, celebrities, tech, merch and events.",
        "features": [
            "TV and movies (TMDB), games and DLC (IGDB), music (MusicBrainz), celebrities, and anything else you type in",
            "Per-person lists, so each household member follows their own things",
            "One sensor (`sensor.release_tracker_releases`) with every upcoming release as attributes, for dashboards and automations",
            "Notifications when something drops, to everyone or one person",
            "AI help to fill in dates and details",
        ],
        "needs": ["Free TMDB key (TV, movies, celebrities)", "Free Twitch client ID and secret (games)", "MQTT (optional)"],
    },
    "team_tracker_lite": {
        "tagline": "One lightweight sports sensor: pick any team from a menu and switch whenever you like.",
        "features": [
            "Any team from ESPN's leagues, chosen in the sidebar panel",
            "One sensor (`sensor.team_tracker`) with game state, score, teams and colors",
            "Live game: follow any game that's on right now",
            "Optional calendar feed on port 8100 for your phone",
            "**Score lights**: flash lights in the team's colors when they score",
        ],
        "needs": ["MQTT (Mosquitto add-on or your own broker)"],
    },
    "sleep_tracker": {
        "tagline": "Knows who's asleep by checking several signals at once (phone, Focus, lights, TV, motion), with MQTT sensors and sleep history.",
        "features": [
            "Suggests signals for each person and their bedroom automatically",
            "Only calls it when enough signals agree for long enough",
            "Asleep sensors and sleep/wake times over MQTT",
            "Last night's sleep, a 7-night average, naps and interruptions as sensors, plus sleep history",
            "AI help to tune the signals",
        ],
        "needs": ["The Home Assistant phone app (best signals)", "MQTT (Mosquitto add-on or your own broker)"],
    },
    "work_hours": {
        "tagline": "Logs the time people spend in chosen zones, one file per person, with MQTT sensors and pay periods.",
        "features": [
            "Pick people and their work zones in the sidebar",
            "Each person gets their own pay period (one or two weeks, starting any day)",
            "Hours in the current pay period as sensors over MQTT",
            "One CSV per person (default `/homeassistant/work_hours`, kept 365 days)",
            "Grace time so a quick trip out doesn't split the day, and a minimum visit length",
        ],
        "needs": ["`person` entities with location", "MQTT (Mosquitto add-on or your own broker)"],
    },
    "zone_creator": {
        "tagline": "Search an address, drop a pin and create a Home Assistant zone, with optional AI name and icon suggestions.",
        "features": [
            "Searches three free geocoders at once (US Census, OpenStreetMap, Photon)",
            "Paste coordinates, drag the pin and set the radius on the map",
            "AI name and icon suggestions through your `ai_task` entity",
            "Zones appear immediately in Home Assistant",
        ],
        "needs": ["Nothing extra", "An `ai_task` entity (optional)"],
    },
    "svg_maker": {
        "tagline": "Turn photos into clean, scalable SVG icons. **Moved into Photo Hub**: this stand-alone add-on still works but gets no new features.",
        "features": [
            "Auto crop (circle, rounded, square or full) and auto-enhance",
            "Color or black-and-white tracing (vtracer)",
            "AI logos through your `ai_task` entity",
            "Icons saved to `/homeassistant/custom_icons` with icon-friendly names",
        ],
        "needs": ["Nothing extra", "An `ai_task` entity (optional)"],
        "deprecated": True,
    },
}
