#!/usr/bin/with-contenv bashio
bashio::log.info "Starting Sleep Tracker..."
exec python3 /app/main.py
