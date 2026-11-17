#!/bin/sh
set -e

CONFIG_PATH=/data/options.json

FILES_PATH="$(jq --raw-output '.files_path // "/data/files"' "$CONFIG_PATH")"
SCAN_INTERVAL="$(jq --raw-output '.scan_interval // 30' "$CONFIG_PATH")"
API_TOKEN="$(jq --raw-output '.api_token // ""' "$CONFIG_PATH")"
MQTT_HOST="$(jq --raw-output '.mqtt_host // "core-mosquitto"' "$CONFIG_PATH")"
MQTT_PORT="$(jq --raw-output '.mqtt_port // 1883' "$CONFIG_PATH")"
MQTT_USER="$(jq --raw-output '.mqtt_user // ""' "$CONFIG_PATH")"
MQTT_PASS="$(jq --raw-output '.mqtt_password // ""' "$CONFIG_PATH")"
export FILES_PATH SCAN_INTERVAL API_TOKEN MQTT_HOST MQTT_PORT MQTT_USER MQTT_PASS

echo "[file_reader] Files folder: $FILES_PATH"
exec python3 -u /usr/src/app/app/app.py
