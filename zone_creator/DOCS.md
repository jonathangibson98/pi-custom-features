# Zone Creator Documentation

## Using it
1. Type an address or place in the search box and press Enter. You can also paste
   coordinates like `34.5230, -82.4940`.
2. Tap a result. The map jumps there and drops a pin.
3. Drag the pin or tap the map to adjust. Change the radius if needed.
4. Set the name and icon (or let the AI do it), then tap **Create zone**.

New zones appear immediately under Settings > Areas, labels & zones > Zones.

## Options

| Option | Default | What it does |
|---|---|---|
| `ai_task_entity` | blank | An `ai_task` entity used to suggest a name and icon. Blank turns the AI button off. Example: `ai_task.gemini_pro_ai_task` |
| `default_radius` | `100` | Starting radius in meters (10 to 5000) |

Restart the add-on after changing options.

## How the AI part works
After you pick a result, the add-on sends the place name and your existing zone names
to the `ai_task.generate_data` service and asks for a short name and one mdi icon.
The ✨ AI button asks again for a different take. If the AI fails or returns junk,
you get an error message and can type the name and icon yourself.

## How address search works
Searches run against three free services at the same time and the results are merged:

- US Census Geocoder: best for US street addresses
- OpenStreetMap Nominatim: best for businesses and landmarks
- Photon: backup

No API keys needed. Only the text you search for leaves your network.

## Troubleshooting

**"No match" on an address**
- Use the format `123 Main St, City, ST`. Adding the city and state helps a lot.
- Read the red error box under the button. It lists what each service said.
- If the add-on can't reach the internet, check HA's DNS settings.
- Fallback: tap the map to place the pin yourself, or paste coordinates.

**Create zone fails**
The add-on creates zones over the Home Assistant websocket API using its Supervisor token.
Check the add-on log for the exact error and open an issue with it.

**Icon preview is blank**
The icon name isn't a real Material Design Icon. Look up a valid one at pictogrammers.com/library/mdi.

## Privacy
Searches go to the services above. The AI call goes only to your own Home Assistant.

## Backups

Tap **Backups** at the bottom of the add-on page to back up, download or restore. A backup is a `.zip` with its settings (zones themselves live in Home Assistant, so a Home Assistant backup covers them), plus everything in the Configuration tab.

| Option | Default | What |
|---|---|---|
| `backup_path` | `/share/addon_backups/zone_creator` | Where backups go, inside `/share`, `/media` or `/homeassistant`. A folder keeps several dated backups. A path ending in `.zip` keeps one file that is replaced each time |
| `backup_every` | `daily` | `off`, `daily` or `weekly` automatic backups |
| `backup_keep` | `10` | How many backups to keep in the folder. Older ones are deleted |

- **Back up now** makes one straight away. **Download** saves one to your phone or computer.
- **Restore** (tap twice) first saves a safety copy (`..._pre-restore_...zip`, the newest 3 are kept), puts the Configuration tab settings back, and restarts the add-on. The data is put back as it starts, before it reads anything.
- **Restore from a file** takes a backup `.zip` you downloaded, for example to move to another Home Assistant.
- A backup from a different add-on is refused. The page only works from the Home Assistant sidebar, never on the add-on's own ports, because backups include its settings.
- Backups also hold any passwords or API keys from the Configuration tab, so treat the backup folder like your secrets.
