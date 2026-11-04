#!/bin/sh
set -e

OPTIONS=/data/options.json
APP=/home/node/app
STORE=/config   # add-on config folder, visible in HA as /addon_configs/<id>_sillytavern

PASSWORD="$(jq -r '.admin_password // ""' "$OPTIONS")"

if [ -z "$PASSWORD" ]; then
  echo "[addon] ERROR: set 'admin_password' in the add-on Configuration tab, then start again."
  echo "[addon] SillyTavern refuses to listen on the network with a password-less admin account."
  exit 1
fi

cd "$APP"

# Keep everything that matters in the persistent add-on config folder
for d in config data plugins extensions backups; do
  mkdir -p "$STORE/$d"
done
rm -rf "$APP/config" "$APP/data" "$APP/plugins" "$APP/backups" \
       "$APP/public/scripts/extensions/third-party"
ln -s "$STORE/config"     "$APP/config"
ln -s "$STORE/data"       "$APP/data"
ln -s "$STORE/plugins"    "$APP/plugins"
ln -s "$STORE/backups"    "$APP/backups"
ln -s "$STORE/extensions" "$APP/public/scripts/extensions/third-party"

# First run: seed config, then let ST fill in any missing keys
[ -e config/config.yaml ] || cp default/config.yaml config/config.yaml
npm run init

# Settings via ST's built-in SILLYTAVERN_* env overrides
export SILLYTAVERN_LISTEN=true
export SILLYTAVERN_ENABLEUSERACCOUNTS=true
export SILLYTAVERN_WHITELISTMODE=false
export SILLYTAVERN_BROWSERLAUNCH_ENABLED=false

# Apply the admin password from the add-on options (re-applied on every start)
echo "[addon] Applying admin password for 'default-user'"
node recover.js default-user "$PASSWORD" >/dev/null

echo "[addon] Starting SillyTavern on port 8000"
exec node server.js --listen
