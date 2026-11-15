# Changelog

## 1.1.0

- **Backups.** New **Backups** page (link at the bottom of the add-on page) to back up now, download, restore, or restore from an uploaded file. Backups go to `backup_path` (a folder, or one `.zip` file) automatically on the `backup_every` schedule, and the newest `backup_keep` are kept
- A backup holds its settings (the voice and speech models are left out, they download again by themselves), plus the Configuration tab settings. Restoring saves a safety copy first, puts the settings back and restarts the add-on to put the data back
- The add-on now has Supervisor access (`hassio_api`, to restore its settings and restart itself) and `/share` access for the backup folder

## 1.0.1
- Now published as a prebuilt image (`ghcr.io/jonathangibson98/{arch}-addon-personal_ai_speech`), so the Pi downloads it instead of compiling the speech libraries.
- Install instructions now cover installing from the repository (they only described copying the folder).
- Added a label for the 8880 port on the Network tab.

## 1.0.0
- First release: Kokoro TTS with emotion tags, proxy engine, faster-whisper STT, sidebar test page.
