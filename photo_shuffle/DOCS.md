<!-- docs:header (generated, edit .github/docsgen) -->
# Photo Hub

![Version](https://img.shields.io/badge/dynamic/yaml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fjonathangibson98%2Fpi-custom-features%2Fmain%2Fphoto_shuffle%2Fconfig.yaml&query=%24.version&label=version&color=41BDF5&logo=homeassistant) ![Architectures](https://img.shields.io/badge/arch-aarch64%20%7C%20amd64-informational) ![Sidebar](https://img.shields.io/badge/sidebar-ingress-success) ![Prebuilt image](https://img.shields.io/badge/image-GHCR-2ea44f?logo=docker) ![MQTT](https://img.shields.io/badge/MQTT-optional-660066?logo=mqtt) ![AI Task](https://img.shields.io/badge/AI-ai__task-8A2BE2?logo=googlegemini)

> Everything photos in one place: folder shuffles and Unsplash collections as image entities, one wallpaper for every add-on page, a Photo Editor with AI tools, SVG Maker, and photo upload with AI analysis.

## At a glance

| | |
|---|---|
| Version | `5.1.0` |
| Slug | `photo_shuffle` |
| Architectures | `aarch64`, `amd64` |
| Opens from | the sidebar (**Photo Hub**, ingress) |
| Extra ports | none |
| Folders it can reach | `media`, `share`, `homeassistant_config`, `addon_config` (read only), `backup`, `all_addon_configs`, `addons`, `ssl` (read only) |
| API access | Home Assistant API, Supervisor API |
| MQTT | optional (used when available) |
| Takes commands via `hassio.addon_stdin` | yes |
| Install | prebuilt image from GHCR |

**You'll need:**

- MQTT (Mosquitto add-on or your own broker)
- A free Unsplash access key (only for Unsplash)
- An `ai_task` entity (only for AI edits, logos and photo analysis)

## Contents

- [Setup](#setup)
- [Options](#options)
- [Folders](#folders)
- [Backups](#backups)
- [Wallpaper](#wallpaper)
- [Photo Editor](#photo-editor)
- [Upload & Analyze](#upload--analyze)
- [SVG Maker](#svg-maker)
    - [How to use](#how-to-use)
    - [AI logo](#ai-logo)
    - [Base it on a photo](#base-it-on-a-photo)
    - [File access](#file-access)
    - [SVG options](#svg-options)
    - [AI logo options](#ai-logo-options)
    - [SVG tips](#svg-tips)
    - [Using your icons in Home Assistant](#using-your-icons-in-home-assistant)
    - [If the AI logo tab fails](#if-the-ai-logo-tab-fails)
    - [If a conversion fails](#if-a-conversion-fails)
- [Configuration reference](#configuration-reference)
- [Help and feedback](#help-and-feedback)
<!-- /docs:header -->

Everything photos in one add-on (sidebar: Photo Hub). The top bar has four sections: **Upload**, **Edit** (Photo Editor and SVG Maker), **Shuffle** (Folders and Unsplash) and **Wallpaper**. Sections with two screens have a small switcher under the bar, and Photo Hub remembers where you were.

What's inside:

- **Folders** and **Unsplash**: publish photos to Home Assistant as **image entities** over MQTT.
- **Wallpaper**: one background for every add-on's page, with darken / lighten / blur controls.
- **Photo Editor**: manual and AI photo editing.
- **Analyze**: upload photos (one or a batch), let an AI describe them, and save them where you choose.
- **SVG Maker**: turn photos into SVG icons, or have AI draw a logo.

Pictures move between the tabs with one tap: edit a shuffle's photo, set the result as the wallpaper, trace it as an SVG, or open an SVG back in the editor.

## Setup

1. Install and start the **Mosquitto broker** add-on with the MQTT integration, or set the `mqtt_*` options below to use your own broker.
2. Start Photo Hub and open it from the sidebar.
3. Add a **folder shuffle** or an **Unsplash collection**. Entities appear in Home Assistant automatically.

## Options

Every option is listed with its default in the [Configuration reference](#configuration-reference) at the end of this page.

## Folders

Each folder shuffle is an image entity that moves to a random photo on a timer, with no repeats until the folder has been used up. Each also gets a "next" button.

## Backups

Tap **Backups** at the bottom of the add-on page to back up, download or restore. A backup is a `.zip` with your shuffles and Unsplash collections (thumbnails are left out, they're rebuilt by themselves), plus everything in the Configuration tab.

| Option | Default | What |
|---|---|---|
| `backup_path` | `/share/addon_backups/photo_shuffle` | Where backups go, inside `/share`, `/media` or `/homeassistant`. A folder keeps several dated backups. A path ending in `.zip` keeps one file that is replaced each time |
| `backup_every` | `daily` | `off`, `daily` or `weekly` automatic backups |
| `backup_keep` | `10` | How many backups to keep in the folder. Older ones are deleted |

- **Back up now** makes one straight away. **Download** saves one to your phone or computer.
- **Restore** (tap twice) first saves a safety copy (`..._pre-restore_...zip`, the newest 3 are kept), puts the Configuration tab settings back, and restarts the add-on. The data is put back as it starts, before it reads anything.
- **Restore from a file** takes a backup `.zip` you downloaded, for example to move to another Home Assistant.
- A backup from a different add-on is refused. The page only works from the Home Assistant sidebar, never on the add-on's own ports, because backups include its settings.
- Backups also hold any passwords or API keys from the Configuration tab, so treat the backup folder like your secrets.

## Wallpaper

The **Wallpaper** tab sets one background for the web page of every add-on (Photo Hub, Sleep Tracker, AI Builder, Travel Times, Personal AI Gateway…):

- **Upload a picture** from your phone or computer.
- **Pick from your photo folders** (the paths in *photo_paths*).
- **Follow a folder shuffle or Unsplash collection**: the wallpaper changes every time it shows a new photo.
- **Off**: add-ons use your Home Assistant theme's wallpaper again.

Photo Hub saves it to `/config/www/addon-wallpaper/` (served by Home Assistant at `/local/addon-wallpaper/`). An add-on's own **Wallpaper** option on its Configuration tab still wins, if you set one.

**Look & readability** (on the same tab): *Lighten / Darken*, *Blur*, *Saturation*, *Contrast* and *Warmth*, plus presets. Tap **Save look**. The look is applied every time the wallpaper changes (for example when it follows a shuffle), and it's always made from the untouched picture. On top of that, every add-on page checks how bright the wallpaper is and adds just enough tint behind its text to keep it readable.

## Photo Editor

Open a photo from your device, your photo folders, the current wallpaper, **Edit photo** on a folder shuffle, or **Edit** under an Unsplash photo. Then:

- **Adjust**: brightness, contrast, saturation, warmth, tint, shadows, highlights, fade, vintage, sharpen, blur, vignette, grain. Double-tap (or double-click) a slider to reset it.
- **Filters**: one-tap looks. They just move the sliders, so you can fine-tune them.
- **Crop**: pick a shape, drag the box and its round handle, **Apply crop**. Rotate, flip and resize are there too.
- **✨ AI**: type what to change, or tap a preset, and tap **Make it**. Your Home Assistant AI Task makes a new version (this needs an AI Task that can make images, like Google Gemini or OpenAI). **AI auto-adjust** (Adjust tab) has the AI look at the photo and set the sliders. The photo is sent to your AI provider; the copy Photo Hub puts in `/media/svg_maker/ai_photos` for it is deleted right after.
- **Save**: save to the edits folder or any of your photo folders (JPG or PNG), **Download**, **Set as add-on wallpaper**, or **Trace as SVG** / **Use for AI logo** to hand it to SVG Maker.

**Undo**/**Redo** cover every step, and holding **Before** shows the original. The editor works at up to 3000 px; very large photos are scaled to that.

## Upload & Analyze

The **Upload** section (first icon at the top) is for getting photos from your phone into a folder, with an AI describing each one on the way.

1. **Pick photos.** Tap the box and choose one photo or many. iPhone HEIC photos work (they're saved as JPEG). JPEG, PNG, WebP and GIF are saved exactly as they were sent.
2. **Save to.** Tap one of your **destinations**. A destination is a named shortcut to a folder, so the folder you use all the time is one tap away. Tap **+ Add destination**, name it, then browse to a folder (or make a new one with **Create**) and **Save**. **Edit this one** renames it, points it at another folder, or removes it. Removing a destination only removes the shortcut; the folder and its pictures are never touched.
3. **AI.** Pick which AI Task entity to use from the list. It shows every `ai_task` entity Home Assistant has that can look at photos (Google Gemini, OpenAI, Anthropic and so on), so you can switch between them. Add a hint like "tools and equipment" if you want the AI to focus on something. Turn **Look at each photo with AI** off to just upload.
4. Tap **Upload**. Photos go one at a time, so a Raspberry Pi and your AI provider's rate limits aren't flooded. **Stop after this one** pauses a long batch.

For each photo the AI returns a one-sentence caption, the scene, the main objects, how many people are visible with a short description of each (what they're doing and wearing), any readable text, and search tags. People are **described, never named**: the AI is told not to work out who anyone is. With **Rename each photo after what's in it** on (the default), the AI also picks a short file name, so `IMG_0042.HEIC` is saved as something like `dog-on-couch.jpg`. If the name is taken you get `dog-on-couch-2.jpg`, and if the AI can't suggest one the photo keeps its original name. The **Recent** list under the buttons shows the last results and can be searched by caption, object or tag; tap a tag to search for it. **Clear list** only clears that list.

If the AI fails (wrong entity, rate limit, timeout), the photo is **still saved**. The error shows next to it and you can upload it again with another AI. Files are never overwritten: a name that's taken becomes `name-2.jpg`. Photos named just `image.jpg` (what some phones send) are named by date and time unless the AI renames them.

**Where can I save?** Anywhere Photo Hub can see, which is the folders Home Assistant gives add-ons: `/media`, `/share`, `/homeassistant` (your config folder), `/backup`, `/addons`, `/addon_configs` and `/ssl` (read only). It can't see the rest of the Pi or other add-ons' private data. A folder marked ⚠ is read-only for Photo Hub. After updating from an older version, **restart** Photo Hub once so Home Assistant applies the extra folders.

**Privacy.** With AI on, each photo is sent to the AI provider behind the entity you picked. Photo Hub puts a temporary copy in `/media/svg_maker/ai_photos` so Home Assistant can hand it to the AI, and deletes it right after.

**If it doesn't work**

- *"No AI Task found"*: add an AI integration that offers AI Task under **Settings → Devices & services**.
- *"... can't look at photos"*: that AI Task doesn't accept attachments. Pick another.
- *"The AI answered, but not in a form I could read"*: try again, or pick another AI.
- A destination with ⚠ or *"Photo Hub can't write to ..."*: pick a folder under `/media` or `/share`.

## SVG Maker

The **SVG Maker** tab. Results have an **Open in Photo Editor** button that turns the SVG into a picture you can edit or use as a wallpaper.

Turn photos into scalable SVG vector files, or have AI draw a logo, from the add-on panel. The page has two tabs: **From photo** and **AI logo**.

### How to use
1. Pick a photo. A crop window appears with the suggested crop already in place.
2. Drag the photo to move it, pinch or use the Zoom slider to resize. Choose **Circle**, **Rounded**, **Square** or **Full** (whole photo). **Auto-fit** re-runs the suggestion and **Reset** starts over.
3. Choose **Color** or **Black & white**, set the detail, and tap **Convert to SVG**.
4. Preview the result, type the file name you want, then tap **Save locally** (to your save folder), **Download** (to your device) or **Both**.

**Auto-crop** finds whatever stands out most and centers the crop on it. It is not face detection, so check it and nudge if needed. **Auto-enhance** boosts contrast, smooths texture and simplifies colors so photos trace into clean shapes and smaller files. The crop is made in your browser, so phone photos in formats like HEIC also work if your browser can open them.

Every conversion is also auto-saved to the temp folder (`svg_temp_path`). Save locally or Both moves that copy into your save folder, so only unsaved results stay in temp. Files under `/homeassistant/www` are available in Home Assistant at `/local/...`, for example `/local/svg_maker/temp_icons/name.svg`. If `www` did not exist before, restart Home Assistant once so it starts serving `/local`.

### AI logo
1. Open the **AI logo** tab and describe what should be in the logo. Or add a photo (below) and describe it, or leave the description blank.
2. Pick a **Style**, **Color** (full color, or black and white that follows Home Assistant colors), optional color words like "navy and gold", and a **Shape** (as designed, circle, rounded, square).
3. Choose how many **ideas** to draw (1 to 3, each is a separate AI call) and tap **Draw my logo**.
4. Tap an idea to pick it. To tweak it, type a change under **Want a change?** (for example "make the ears bigger") and tap **Update logo**. Older versions stay in the grid.
5. Name it and use **Save locally**, **Download** or **Both**, same as photos.

The AI draws real vector shapes, so results vary. Several ideas and a couple of edits usually beats one try. Lettering uses the viewer's fonts, so icon-only designs look the same everywhere. Logos are cleaned before you see them: scripts, external links, bitmaps and animation are stripped and gradient ids are made unique so many icons can share a dashboard.

AI logos are auto-saved to the temp folder like photo results, and the auto-delete options cover them too.

### Base it on a photo
Under **Base it on a photo**, pick a picture (your dog, your truck, an old logo, a sketch). Your AI Task gets the photo along with your description, and actually looks at it while drawing. Choose how it uses the photo:

- **Turn it into a logo**: keeps what makes the subject recognizable (shape, pose, markings, colors) and simplifies it into bold shapes. Leaves out the background.
- **Stay close to the photo**: a cleaner vector redraw that stays as close to the photo as it can, with more detail.
- **Just inspiration**: borrows the subject, colors and mood. The design can be quite different.

The photo's main colors show as dots. **Use its colors** puts them in **Colors**. The description is optional with a photo: leave it blank for a logo of the subject, or say what you want ("my dog as a mascot, no background, navy circle"). **Update logo** keeps using the same photo. **Remove photo** goes back to text only.

This needs an AI Task that can read images (Google Gemini, OpenAI and Anthropic can). The photo is shrunk to 1024 px and saved in `/media/svg_maker/ai_photos/` because Home Assistant passes attachments to the AI from its media folder (**Media > My media**). Photos there are deleted after a day.

This is different from the **From photo** tab: that one traces the pixels with no AI. This one has the AI draw a new design from what it sees.

### File access
The add-on can see `/homeassistant`, `/share` and `/media`. SVG Maker only writes to the save and temp folders you set. Protected system paths are refused.

### SVG options

| Option | Default | What it does |
|---|---|---|
| `svg_output_path` | `/homeassistant/custom_icons` | Where Save locally and Both put files. The default is the folder the Custom Icons integration reads. Created automatically |
| `svg_temp_path` | `/homeassistant/www/svg_maker/temp_icons` | Auto-save location for results you did not save |
| `svg_auto_delete_temp` | `false` | Delete old files the tool made from the temp folder. Never touches the save folder |
| `svg_auto_delete_after_days` | `7` | Age limit when auto-delete is on |
| `svg_filename_style` | `original_timestamp` | Naming for temp files (`original`, `timestamp`, `original_timestamp`) |
| `svg_on_name_conflict` | `rename` | `rename` adds -1, -2. `overwrite` replaces |
| `svg_default_mode` | `color` | Starting color mode on the page |
| `svg_default_detail` | `5` | Starting detail (1 to 10) |
| `svg_path_style` | `spline` | `spline`, `polygon` or `none` |
| `svg_max_image_dimension` | `1600` | Longest side in pixels before tracing |
| `svg_max_upload_mb` | `25` | Largest upload allowed |
| `svg_icon_names` | `true` | Saves names as lowercase-with-hyphens so they work as icon names |
| `svg_bw_follow_theme` | `true` | Black and white results use currentColor so Home Assistant can recolor them |
| `svg_crop_editor` | `true` | Show the drag and zoom crop window after you pick a photo |
| `svg_auto_crop` | `true` | Auto-suggest the crop. With the editor off, the auto crop is applied without asking |
| `svg_crop_shape` | `circle` | `circle`, `rounded`, `square` or `none` (whole photo). Changeable on the page |
| `svg_crop_padding` | `15` | Extra space around the detected subject, in percent |
| `svg_output_size` | `512` | Cropped photo is shrunk to this many pixels before tracing |
| `svg_auto_enhance` | `true` | Contrast, noise smoothing and color simplifying before tracing. Changeable on the page |

### AI logo options

| Option | Default | What it does |
|---|---|---|
| `svg_ai_task_entity` | `ai_task.google_ai_task` | The `ai_task` entity that draws logos |
| `svg_ai_timeout` | `180` | Seconds to wait for one logo before giving up |
| `svg_ai_default_style` | `flat` | Starting style (`auto`, `flat`, `line`, `gradient`, `badge`, `mascot`, `geometric`, `sketch`) |
| `svg_ai_default_count` | `1` | Starting number of ideas (1 to 3) |
| `ha_url` | `http://homeassistant:8123` | Optional. Only used together with `ha_token` |
| `ha_token` | empty | Optional long-lived token. Leave empty to use the add-on's built-in access |

Restart the add-on after changing options.

### SVG tips
- Works best on logos, drawings, signatures and images with clear shapes.
- iPhone photo failing? Settings, Camera, Formats, **Most Compatible** (HEIC is not supported).
- Slow on a Raspberry Pi? Lower `svg_max_image_dimension` or the detail slider. Conversions run one at a time.

### Using your icons in Home Assistant
Install the **Custom Icons** integration (HACS), enable the **Local** collection in its configuration, and press **RELOAD** after saving new icons. Icons are then available as `local:<file-name>`. Full-color icons keep their colors. Black and white icons follow the entity color when `svg_bw_follow_theme` is on.

### If the AI logo tab fails
- "The AI Task entity ... was not found": fix `svg_ai_task_entity` to match an entity under Developer tools, States (search `ai_task.`).
- "Home Assistant refused the add-on": restart the add-on once. If it persists, create a long-lived token in your Home Assistant profile and paste it into `ha_token`.
- "The AI took longer than ...": raise `svg_ai_timeout`, or draw 1 idea at a time.
- "The AI answered, but not with a usable SVG": the add-on already retried once. Reword the request, or try again.
- "The AI task call with your photo failed": your AI Task can't read images, or Home Assistant can't open the photo. Check that the AI integration supports attachments, and that **Media > My media > svg_maker > ai_photos** shows the photo. Custom `media_dirs` are fine as long as one of them points at `/media`; the add-on finds it by itself.

### If a conversion fails
- "The tracer failed: killed by signal ..." means the tracing program crashed or ran out of memory. The add-on retries automatically at 60% and then 35% of the image size before giving up. If it still fails, lower `svg_max_image_dimension` or `svg_output_size`, or use fewer detail steps.
- The log shows a line "Tracer self-test passed" at start-up. If it says FAILED instead, rebuild the add-on and share that log line.
- Only the Home Assistant ingress gateway can reach this add-on's web server.

Restart the add-on after changing options.

<!-- docs:config (generated from config.yaml) -->
## Configuration reference

Every option on the add-on's **Configuration** tab, with its default. Change them there, then restart the add-on.

| Option | Default | Type | What it does |
|---|---|---|---|
| `photo_paths` | `/media` | list | **Allowed photo paths.** Folders the add-on may read for folder shuffles. Must start with /media, /share, /homeassistant or /addon_configs. |
| `formats` | `jpg`, `png`, `webp` | list | **Picture formats.** Which picture types folder shuffles include. jpg covers .jpg and .jpeg. |
| `max_dimension` | `1920` | whole number (256–4096) | **Max image size (px).** Longest side of every picture sent to Home Assistant, folder or Unsplash. Larger photos are scaled down. |
| `jpeg_quality` | `85` | whole number (30–100) | **JPEG quality.** Quality of the published JPEG (30 to 100). |
| `unsplash_interval_minutes` | `60` | whole number (5–1440) | **Unsplash refresh interval (minutes).** How often every Unsplash collection gets a fresh photo. Each image costs one request, and the free tier allows 50 per hour. |
| `unsplash_image_size` | `regular` | one of: `full`, `regular`, `small` | **Unsplash download size.** Which Unsplash size to download before it is resized. regular (about 1080px) is plenty for most dashboards. |
| `backup_path` | `/share/addon_backups/photo_shuffle` | text | **Backup folder.** Where backups are saved, inside /share, /media or /homeassistant. A folder keeps several dated backups. A path ending in .zip keeps one file that is replaced each time. Open Backups in the add-on page to back up, download or restore. |
| `backup_every` | `daily` | one of: `off`, `daily`, `weekly` | **Automatic backups.** How often a backup is made by itself (off, daily or weekly). |
| `backup_keep` | `10` | whole number (1–100) | **Backups to keep.** The newest this many backups are kept in the folder, older ones are deleted. |
| `wallpaper` | *(empty)* | text, optional | **Wallpaper.** Background image for this add-on's web UI. Leave empty to use your Home Assistant theme's wallpaper, "none" for no wallpaper, or an image: put it in /config/www and enter its file name (pic.jpg) or /local/pic.jpg, or a full https:// link. |
| `edit_output_path` | `/media/photo_hub/edited` | text | **Photo Editor folder.** Where the Photo Editor saves edited pictures. It is added to your photo paths automatically, so edits can be shuffled or used as the wallpaper. |
| `svg_output_path` | `/homeassistant/custom_icons` | text | **SVG save folder.** Where SVG Maker puts files when you press Save locally or Both. Default /homeassistant/custom_icons is the folder the Custom Icons integration reads. Any folder this add-on can see works (/homeassistant, /share, /media). Created if missing. |
| `svg_temp_path` | `/homeassistant/www/svg_maker/temp_icons` | text | **SVG temp folder (auto-saves).** Every conversion is auto-saved here until you save it yourself. Default /homeassistant/www/svg_maker/temp_icons, which Home Assistant serves at /local/svg_maker/temp_icons/. |
| `svg_auto_delete_temp` | `false` | true / false | **SVG auto-delete temp files.** Turn on to automatically delete old files from the SVG temp folder. Never touches your save folder. |
| `svg_auto_delete_after_days` | `7` | whole number (1–365) | **SVG delete temp files older than (days).** Only used when SVG auto-delete temp files is on. |
| `svg_filename_style` | `original_timestamp` | one of: `original`, `timestamp`, `original_timestamp` | **SVG temp file naming.** How auto-saved temp files are named. original = photo name, timestamp = unix time, original_timestamp = both. You choose the name for saved files on the page. |
| `svg_on_name_conflict` | `rename` | one of: `rename`, `overwrite` | **SVG if the file name already exists.** rename adds -1, -2 so nothing gets overwritten. overwrite replaces the old file. |
| `svg_default_mode` | `color` | one of: `color`, `bw` | **SVG default color mode.** Color keeps colors. bw makes a black and white trace. Changeable per upload on the page. |
| `svg_default_detail` | `5` | whole number (1–10) | **SVG default detail (1-10).** 1 is simple and smooth, 10 is highly detailed but bigger files. Changeable per upload. |
| `svg_path_style` | `spline` | one of: `spline`, `polygon`, `none` | **SVG curve style.** spline = smooth curves (best for most). polygon = straight edges. none = raw pixel-ish paths. |
| `svg_max_image_dimension` | `1600` | whole number (400–4000) | **SVG max image size (px).** Photos are shrunk so the longest side fits this before tracing. Lower is faster on a Pi. |
| `svg_max_upload_mb` | `25` | whole number (1–100) | **SVG max upload size (MB).** Reject uploads larger than this. |
| `svg_icon_names` | `true` | true / false | **SVG icon-friendly file names.** Save names as lowercase letters, numbers and hyphens (My Dog becomes my-dog) so they work as Home Assistant icon names. |
| `svg_bw_follow_theme` | `true` | true / false | **SVG black and white follows HA colors.** For black and white conversions, use currentColor instead of hard black so the icon takes on the color Home Assistant gives it (for example yellow when a light is on). Color conversions keep their colors. |
| `svg_crop_editor` | `true` | true / false | **SVG show crop editor.** After you pick a photo, show a draggable, zoomable crop window (like the Facebook profile picture screen) so you can approve or adjust the crop before converting. |
| `svg_auto_crop` | `true` | true / false | **SVG auto-crop suggestion.** Automatically find the main subject and position the crop on it. You can still drag and zoom. With the editor off, the auto crop is applied without asking. |
| `svg_crop_shape` | `circle` | one of: `circle`, `rounded`, `square`, `none` | **SVG default crop shape.** circle, rounded or square crop the result to that shape (great for icons). none keeps the whole photo. Changeable on the page. |
| `svg_crop_padding` | `15` | whole number (0–60) | **SVG crop padding (%).** Extra breathing room around the detected subject. Higher zooms out more. |
| `svg_output_size` | `512` | whole number (128–2048) | **SVG crop output size (px).** The cropped photo is shrunk to this size before upload and tracing. 512 is good for icons and is fast on a Pi. |
| `svg_auto_enhance` | `true` | true / false | **SVG auto-enhance before tracing.** Boosts contrast, smooths texture noise and simplifies colors so photos trace into clean shapes with smaller files. Changeable on the page. |
| `svg_ai_task_entity` | `ai_task.google_ai_task` | text | **AI logo - AI Task entity.** The Home Assistant ai_task entity that draws logos in the AI logo tab. Default ai_task.google_ai_task. |
| `svg_ai_timeout` | `180` | whole number (30–600) | **AI logo - timeout (seconds).** How long to wait for the AI to draw one logo before giving up. Raise it if your AI is slow. |
| `svg_ai_default_style` | `flat` | one of: `auto`, `flat`, `line`, `gradient`, `badge`, `mascot`, `geometric`, `sketch` | **AI logo - default style.** Starting style in the AI logo tab. Changeable on the page. |
| `svg_ai_default_count` | `1` | whole number (1–3) | **AI logo - default number of ideas.** How many different designs to draw at once (1 to 3). Each one is a separate AI call. Changeable on the page. |
| `ha_url` | `http://homeassistant:8123` | text, optional | **Home Assistant URL (optional).** Only used with the token below. Leave the default unless you need to reach Home Assistant a different way. |
| `unsplash_access_key` | *(empty)* | secret, optional | **Unsplash Access Key (optional).** Needed only for Unsplash collections. Use the Access Key, not the Secret Key, from unsplash.com/developers. |
| `mqtt_host` | *(empty)* | text, optional | **MQTT host (optional).** Leave empty to use the Mosquitto add-on automatically. |
| `mqtt_port` | *(empty)* | port, optional | **MQTT port (optional).** Defaults to 1883. |
| `mqtt_username` | *(empty)* | text, optional | **MQTT username (optional).** Only needed with a manual MQTT broker. |
| `mqtt_password` | *(empty)* | secret, optional | **MQTT password (optional).** Only needed with a manual MQTT broker. |
| `photo_ai_image_entity` | *(empty)* | text, optional | **AI for photo edits (optional).** The AI Task entity that edits photos (it must be able to make images, for example Google Gemini or OpenAI). Leave empty to pick one automatically. |
| `photo_ai_data_entity` | *(empty)* | text, optional | **AI for auto-adjust (optional).** The AI Task entity that looks at a photo and suggests slider values. Leave empty to use the SVG Maker AI entity. |
| `ha_token` | *(empty)* | secret, optional | **Home Assistant long-lived token (optional).** Leave empty to use the add-on's built-in access. Only fill this in if the AI logo tab says Home Assistant refused the add-on. |
<!-- /docs:config -->

<!-- docs:footer (generated) -->
## Help and feedback

- **Logs:** the add-on's **Log** tab shows what it's doing and most errors in plain words.
- **Changes:** see the [changelog](CHANGELOG.md) (also on the add-on's **Changelog** tab).
- **Problems or ideas:** [open an issue](https://github.com/jonathangibson98/pi-custom-features/issues) and include the add-on version and the log.
- **Pages follow your theme:** every page in this repository picks up your Home Assistant theme and wallpaper automatically.
- **On your phone:** the pages are built for the Home Assistant iPhone and Android apps. Turn on **Show in sidebar** to reach them from the app's menu.
<!-- /docs:footer -->
