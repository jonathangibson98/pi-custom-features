#!/bin/sh
# Backups: restore first (if asked), then back up in the background (see backup.py).
# SVG Maker keeps its icons in the save folder, so /data is left out.
export BACKUP_SLUG=svg_maker BACKUP_EXTRA=@svg_output_path BACKUP_DATA=0
python3 /app/backup.py restore || true
python3 -u /app/backup.py daemon &

exec python3 -u /app/server.py
