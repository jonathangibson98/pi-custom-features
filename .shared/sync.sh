#!/bin/sh
# Copy the shared backup module into every add-on that uses it. Run from the repository root after editing
# .shared/addon_backup.py (the add-ons build from their own folder, so each needs its own copy).
set -e
# Theme script first, so the backup module copied below carries the latest copy.
python3 .shared/sync_theme.py
for dest in sleep_tracker work_hours photo_shuffle file_reader/app voice_chat/app team_tracker_lite svg_maker \
            zone_creator personal_ai_speech/app; do
  cp .shared/addon_backup.py "$dest/addon_backup.py"
done
echo "addon_backup.py synced"
