# SVG Maker

Turn photos into scalable SVG vector files from the add-on panel.

## How to use
1. Pick a photo. A crop window appears with the suggested crop already in place.
2. Drag the photo to move it, pinch or use the Zoom slider to resize. Choose **Circle**, **Rounded**, **Square** or **Full** (whole photo). **Auto-fit** re-runs the suggestion and **Reset** starts over.
3. Choose **Color** or **Black & white**, set the detail, and tap **Convert to SVG**.
4. Preview the result, type the file name you want, then tap **Save locally** (to your save folder), **Download** (to your device) or **Both**.

**Auto-crop** finds whatever stands out most and centers the crop on it. It is not face detection, so check it and nudge if needed. **Auto-enhance** boosts contrast, smooths texture and simplifies colors so photos trace into clean shapes and smaller files. The crop is made in your browser, so phone photos in formats like HEIC also work if your browser can open them.

Every conversion is also auto-saved to the temp folder (`svg_temp_path`). Save locally or Both moves that copy into your save folder, so only unsaved results stay in temp. Files under `/homeassistant/www` are available in Home Assistant at `/local/...`, for example `/local/svg_maker/temp_icons/name.svg`. If `www` did not exist before, restart Home Assistant once so it starts serving `/local`.

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

Restart the add-on after changing options.

## SVG tips
- Works best on logos, drawings, signatures and images with clear shapes.
- iPhone photo failing? Settings, Camera, Formats, **Most Compatible** (HEIC is not supported).
- Slow on a Raspberry Pi? Lower `svg_max_image_dimension` or the detail slider. Conversions run one at a time.

## Using your icons in Home Assistant
Install the **Custom Icons** integration (HACS), enable the **Local** collection in its configuration, and press **RELOAD** after saving new icons. Icons are then available as `local:<file-name>`. Full-color icons keep their colors. Black and white icons follow the entity color when `svg_bw_follow_theme` is on.

## If a conversion fails
- "The tracer failed: killed by signal ..." means the tracing program crashed or ran out of memory. The add-on retries automatically at 60% and then 35% of the image size before giving up. If it still fails, lower `svg_max_image_dimension` or `svg_output_size`, or use fewer detail steps.
- The log shows a line "Tracer self-test passed" at start-up. If it says FAILED instead, rebuild the add-on and share that log line.
- Only the Home Assistant ingress gateway can reach this add-on's web server.

Restart the add-on after changing options.

