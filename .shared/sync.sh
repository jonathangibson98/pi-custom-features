#!/bin/sh
# Copy the shared backup module into every add-on that uses it. Run from the repository root after editing
# .shared/addon_backup.py (the add-ons build from their own folder, so each needs its own copy).
set -e
for dest in sleep_tracker work_hours photo_shuffle voice_chat/app team_tracker_lite svg_maker \
            zone_creator personal_ai_speech/app; do
  cp .shared/addon_backup.py "$dest/addon_backup.py"
done
echo "addon_backup.py synced"
# Then the theme script into every page (each copy gets its own add-on name).
python3 .shared/sync_theme.py
