#!/usr/bin/with-contenv bashio

# Backups: restore first (if asked), then back up in the background (see backup.py).
# The Unsplash thumbnails are rebuilt automatically, so they are left out.
export BACKUP_SLUG=photo_shuffle BACKUP_EXCLUDE=unsplash_thumbs
python3 /app/backup.py restore || true
python3 -u /app/backup.py daemon &

exec python3 -u /app/main.py
