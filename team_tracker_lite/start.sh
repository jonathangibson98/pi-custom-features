#!/bin/sh
# Backups: restore first (if asked), then back up in the background (see backup.py).
# Team Tracker keeps its settings in the add-on config folder (/config/data).
export BACKUP_SLUG=team_tracker_lite BACKUP_EXTRA=/config/data BACKUP_DATA=0
python3 /app/backup.py restore || true
python3 -u /app/backup.py daemon &

exec python3 -u /app/app.py
