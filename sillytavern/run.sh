#!/bin/sh
set -e

OPTIONS=/data/options.json
APP=/home/node/app
STORE=/config   # add-on config folder, visible in HA as /addon_configs/<id>_sillytavern

opt() { jq -r --arg k "$1" '.[$k] // ""' "$OPTIONS"; }

PASSWORD="$(opt admin_password)"
LOG_LEVEL="$(opt log_level)"
EXT_BASE="$(opt extensions_plugins_path)"

if [ -z "$PASSWORD" ]; then
  echo "[addon] ERROR: set 'admin_password' in the add-on Configuration tab, then start again."
  echo "[addon] SillyTavern refuses to listen on the network with a password-less admin account."
  exit 1
fi

# ---- log level -------------------------------------------------------------
# SillyTavern: 0 debug, 1 info, 2 warn, 3 error
case "$LOG_LEVEL" in
  debug)   ST_LEVEL=0; NGINX_LEVEL=info ;;
  info|"") ST_LEVEL=1; NGINX_LEVEL=notice; LOG_LEVEL=info ;;
  warning) ST_LEVEL=2; NGINX_LEVEL=warn ;;
  error)   ST_LEVEL=3; NGINX_LEVEL=error ;;
  *)
    echo "[addon] Unknown log_level '$LOG_LEVEL', using 'info'"
    LOG_LEVEL=info; ST_LEVEL=1; NGINX_LEVEL=notice ;;
esac

# ---- extensions / plugins location ----------------------------------------
# Empty = the add-on config folder (/config), same as before this option existed.
[ -z "$EXT_BASE" ] && EXT_BASE="$STORE"
case "$EXT_BASE" in
  /*) ;;
  *)  EXT_BASE="$STORE/$EXT_BASE" ;;
esac
case "$EXT_BASE" in
  *..*)
    echo "[addon] ERROR: extensions_plugins_path must not contain '..'"
    exit 1 ;;
esac
EXT_BASE="${EXT_BASE%/}"
case "$EXT_BASE" in
  /config|/config/*|/share|/share/*) ;;
  *)
    echo "[addon] ERROR: extensions_plugins_path must be inside /config or /share (got '$EXT_BASE')"
    exit 1 ;;
esac
if ! mkdir -p "$EXT_BASE/extensions" "$EXT_BASE/plugins" 2>/dev/null; then
  echo "[addon] ERROR: cannot create folders in '$EXT_BASE'"
  exit 1
fi

cd "$APP"

# Everything that matters lives in persistent folders
for d in config data backups; do
  mkdir -p "$STORE/$d"
done
rm -rf "$APP/config" "$APP/data" "$APP/plugins" "$APP/backups" \
       "$APP/public/scripts/extensions/third-party"
ln -s "$STORE/config"          "$APP/config"
ln -s "$STORE/data"            "$APP/data"
ln -s "$STORE/backups"         "$APP/backups"
ln -s "$EXT_BASE/plugins"      "$APP/plugins"
ln -s "$EXT_BASE/extensions"   "$APP/public/scripts/extensions/third-party"

# First run: seed config, then let ST fill in any missing keys
[ -e config/config.yaml ] || cp default/config.yaml config/config.yaml
npm run init

# Settings via ST's built-in SILLYTAVERN_* env overrides
export SILLYTAVERN_LISTEN=true
export SILLYTAVERN_ENABLEUSERACCOUNTS=true
export SILLYTAVERN_WHITELISTMODE=false
export SILLYTAVERN_BROWSERLAUNCH_ENABLED=false
export SILLYTAVERN_LOGGING_MINLOGLEVEL="$ST_LEVEL"

# Apply the admin password from the add-on options (re-applied on every start)
echo "[addon] Applying admin password for 'default-user'"
node recover.js default-user "$PASSWORD" >/dev/null

# ---- ingress (sidebar) proxy ----------------------------------------------
mkdir -p /run/nginx
sed "s/__NGINX_LOG_LEVEL__/$NGINX_LEVEL/" /etc/nginx/ingress.conf.tpl > /etc/nginx/ingress.conf
nginx -t -c /etc/nginx/ingress.conf
nginx -c /etc/nginx/ingress.conf -g 'daemon off;' &

echo "[addon] log_level=$LOG_LEVEL, extensions/plugins in $EXT_BASE"
echo "[addon] Starting SillyTavern on port 8000 (sidebar proxy on 8099)"
exec node server.js --listen
