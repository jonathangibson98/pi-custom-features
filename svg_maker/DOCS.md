# SVG Maker

Turn photos into scalable SVG vector files, or have AI draw a logo, from the add-on panel. The page has two tabs: **From photo** and **AI logo**.

## How to use
1. Pick a photo. A crop window appears with the suggested crop already in place.
2. Drag the photo to move it, pinch or use the Zoom slider to resize. Choose **Circle**, **Rounded**, **Square** or **Full** (whole photo). **Auto-fit** re-runs the suggestion and **Reset** starts over.
3. Choose **Color** or **Black & white**, set the detail, and tap **Convert to SVG**.
4. Preview the result, type the file name you want, then tap **Save locally** (to your save folder), **Download** (to your device) or **Both**.

**Auto-crop** finds whatever stands out most and centers the crop on it. It is not face detection, so check it and nudge if needed. **Auto-enhance** boosts contrast, smooths texture and simplifies colors so photos trace into clean shapes and smaller files. The crop is made in your browser, so phone photos in formats like HEIC also work if your browser can open them.

Every conversion is also auto-saved to the temp folder (`svg_temp_path`). Save locally or Both moves that copy into your save folder, so only unsaved results stay in temp. Files under `/homeassistant/www` are available in Home Assistant at `/local/...`, for example `/local/svg_maker/temp_icons/name.svg`. If `www` did not exist before, restart Home Assistant once so it starts serving `/local`.

## AI logo
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

The photo's main colors show as dots. **Use its colors** puts them in **Colors**. The description is optional with a photo: leave it blank for a logo of the subject, or say what you want ("Nova as a mascot, no background, navy circle"). **Update logo** keeps using the same photo. **Remove photo** goes back to text only.

This needs an AI Task that can read images (Google Gemini, OpenAI and Anthropic can). The photo is shrunk to 1024 px and saved in `/media/svg_maker/ai_photos/` because Home Assistant passes attachments to the AI from its media folder (**Media > My media**). Photos there are deleted after a day.

This is different from the **From photo** tab: that one traces the pixels with no AI. This one has the AI draw a new design from what it sees.

## File access
The add-on can see `/homeassistant`, `/share` and `/media`. SVG Maker only writes to the save and temp folders you set. Protected system paths are refused.

## SVG options

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

## SVG tips
- Works best on logos, drawings, signatures and images with clear shapes.
- iPhone photo failing? Settings, Camera, Formats, **Most Compatible** (HEIC is not supported).
- Slow on a Raspberry Pi? Lower `svg_max_image_dimension` or the detail slider. Conversions run one at a time.

## Using your icons in Home Assistant
Install the **Custom Icons** integration (HACS), enable the **Local** collection in its configuration, and press **RELOAD** after saving new icons. Icons are then available as `local:<file-name>`. Full-color icons keep their colors. Black and white icons follow the entity color when `svg_bw_follow_theme` is on.

## If the AI logo tab fails
- "The AI Task entity ... was not found": fix `svg_ai_task_entity` to match an entity under Developer tools, States (search `ai_task.`).
- "Home Assistant refused the add-on": restart the add-on once. If it persists, create a long-lived token in your Home Assistant profile and paste it into `ha_token`.
- "The AI took longer than ...": raise `svg_ai_timeout`, or draw 1 idea at a time.
- "The AI answered, but not with a usable SVG": the add-on already retried once. Reword the request, or try again.
- "The AI task call with your photo failed": your AI Task can't read images, or Home Assistant can't open the photo. Check that the AI integration supports attachments, and that **Media > My media > svg_maker > ai_photos** shows the photo. Custom `media_dirs` are fine as long as one of them points at `/media`; the add-on finds it by itself.

## If a conversion fails
- "The tracer failed: killed by signal ..." means the tracing program crashed or ran out of memory. The add-on retries automatically at 60% and then 35% of the image size before giving up. If it still fails, lower `svg_max_image_dimension` or `svg_output_size`, or use fewer detail steps.
- The log shows a line "Tracer self-test passed" at start-up. If it says FAILED instead, rebuild the add-on and share that log line.
- Only the Home Assistant ingress gateway can reach this add-on's web server.

Restart the add-on after changing options.

## Backups

Tap **Backups** at the bottom of the add-on page to back up, download or restore. A backup is a `.zip` with the icons in your save folder (svg_output_path), plus everything in the Configuration tab.

| Option | Default | What |
|---|---|---|
| `backup_path` | `/share/addon_backups/svg_maker` | Where backups go, inside `/share`, `/media` or `/homeassistant`. A folder keeps several dated backups. A path ending in `.zip` keeps one file that is replaced each time |
| `backup_every` | `daily` | `off`, `daily` or `weekly` automatic backups |
| `backup_keep` | `10` | How many backups to keep in the folder. Older ones are deleted |

- **Back up now** makes one straight away. **Download** saves one to your phone or computer.
- **Restore** (tap twice) first saves a safety copy (`..._pre-restore_...zip`, the newest 3 are kept), puts the Configuration tab settings back, and restarts the add-on. The data is put back as it starts, before it reads anything.
- **Restore from a file** takes a backup `.zip` you downloaded, for example to move to another Home Assistant.
- A backup from a different add-on is refused. The page only works from the Home Assistant sidebar, never on the add-on's own ports, because backups include its settings.
- Backups also hold any passwords or API keys from the Configuration tab, so treat the backup folder like your secrets.
