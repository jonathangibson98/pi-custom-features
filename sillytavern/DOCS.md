# SillyTavern add-on

## Setup
1. Open the **Configuration** tab and set `admin_password`.
2. Start the add-on. The first build takes a few minutes on a Pi.
3. Open **SillyTavern** in the Home Assistant sidebar (or `http://<HA-IP>:8000`) and log in as **default-user** with that password.

The password is re-applied every time the add-on starts. To change it, change the option and restart.
Additional users can be created inside SillyTavern's own user panel.

## Options
| Option | Default | What it does |
|---|---|---|
| `admin_password` | – | Password for `default-user` (required). |
| `log_level` | `info` | `debug`, `info`, `warning` or `error`. Applies to SillyTavern and the sidebar proxy. |
| `extensions_plugins_path` | empty | Folder that holds your third-party extensions (`extensions/`) and server plugins (`plugins/`). Empty = the add-on config folder. Must be inside `/config` (add-on config folder) or `/share`. A relative path is taken relative to `/config`. |

Example: `/share/sillytavern` keeps extensions and plugins in `/share/sillytavern/extensions` and `/share/sillytavern/plugins`.
If you change the path, move the existing `extensions/` and `plugins/` folders there first, otherwise SillyTavern starts with none installed.

## Sidebar
The add-on uses Home Assistant ingress, so it opens inside HA with HA's own login in front of it.
SillyTavern has no base-path support, so an internal proxy rewrites its URLs; direct access on port 8000 is unaffected.

**Sidebar icon:** Home Assistant reads the icon and title from the add-on's `config.yaml` (`panel_icon`, `panel_title`), not from the options, so they cannot be changed from the Configuration tab.
To change the icon, edit `panel_icon` (any `mdi:` icon), bump `version`, reload the add-on store and Rebuild.
Show/hide the sidebar entry on the add-on's Info page ("Show in sidebar").

If something looks broken inside the sidebar, the same UI is still available on port 8000.

## Where your stuff lives
Everything persists in the add-on config folder (`/addon_configs/<id>_sillytavern/` in Samba/SSH): `config/config.yaml`, `data/` (chats, characters), `backups/`, and by default `plugins/` and `extensions/` (see `extensions_plugins_path`).

## Changing the port
Network section of the add-on page. Leave the container port at 8000. Clear the host port to disable direct access and use the sidebar only.

## Reverse proxy (NPM)
Forward to the HA host IP and the port above, with Websockets enabled.

## Updating
Local add-on: bump `version` in `config.yaml`, reload the add-on store, then Rebuild.
This pulls the newest SillyTavern release branch.
