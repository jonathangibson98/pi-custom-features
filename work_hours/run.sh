#!/usr/bin/with-contenv bashio
bashio::log.info "Starting Work Hours Tracker..."

# Backups: restore first (if asked), then back up in the background (see backup.py)
export BACKUP_SLUG=work_hours BACKUP_EXTRA=@save_folder
python3 /app/backup.py restore || true
python3 -u /app/backup.py daemon &

exec python3 /app/main.py
