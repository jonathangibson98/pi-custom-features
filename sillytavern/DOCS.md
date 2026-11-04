# SillyTavern add-on

## Setup
1. Open the **Configuration** tab and set `admin_password`.
2. Start the add-on. The first build takes a few minutes on a Pi.
3. Open `http://<HA-IP>:8000` and log in as **default-user** with that password.

The password is re-applied every time the add-on starts. To change it, change the option and restart.
Additional users can be created inside SillyTavern's own user panel.

## Where your stuff lives
Everything persists in the add-on config folder (`/addon_configs/<id>_sillytavern/`
in Samba/SSH): `config/config.yaml`, `data/` (chats, characters), `plugins/`, `extensions/`, `backups/`.

## Changing the port
Network section of the add-on page. Leave the container port at 8000.

## Reverse proxy (NPM)
Forward to the HA host IP and the port above, with Websockets enabled.

## Updating
Local add-on: bump `version` in `config.yaml`, reload the add-on store, then Rebuild.
This pulls the newest SillyTavern release branch.
