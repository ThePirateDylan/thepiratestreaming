# The Pirate Maintenance

## Startup cleanup

Removes disposable files older than 24 hours from Kodi's temporary and home/cache folders, and installer ZIPs older than seven days from addons/packages. It leaves recent downloads, log files, cache databases, lock files, protected cache folders and filesystem links alone. Add-on data, favorites, watched progress, Trakt, source results and TV Guide schedules are outside its cleanup paths.

A brief notification confirms startup completion even when there is nothing to remove.

Cleanup waits for playback, busy dialogs, the add-on browser and TV Guide preparation to finish. It stops if Kodi becomes busy again or starts shutting down. No extra service or background thread is added.

Thumbnail clearing is off by default. This update turns off the previous forced startup thumbnail wipe once, while preserving the startup-cleanup opt-out. Users can still explicitly enable thumbnail clearing afterward.

## Manual tools

Open The Pirate Maintenance or the existing cleanup entry in skin settings:

- **Clean now** cleans disposable temporary files, packages and artwork while preserving cache databases, logs, lock files and protected runtime folders.
- **Refresh Pirate artwork** removes only cached Pirate add-on icons, fanart and branding logos. Movie/episode posters, widget artwork and metadata remain cached.
- **Cancel** closes the menu without changes.

Artwork removal uses Kodi's texture API rather than deleting its database. Kodi reloads images when needed; restart Kodi after installing an add-on update if its details still show the old metadata.

## EZ Maintenance

The installed EZ Maintenance+ 2026.04.05.0 clears temporary/cache folders at startup and offers package and thumbnail size warnings. Pirate Maintenance provides the focused cleanup above without clearing useful media caches each boot. It does not depend on EZ Maintenance or change its settings. If both are installed, turn off EZ Maintenance's startup and scheduled AutoClean to avoid duplicate cleanup. Add-on updates remain managed by Kodi.
