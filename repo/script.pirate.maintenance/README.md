# The Pirate Maintenance

This add-on removes Kodi temporary files, old add-on installer packages, and cached thumbnails.

## Manual cleanup

Open the skin's Settings → Backup & Restore page and choose Clean temporary files, packages, and artwork. The confirmation dialog has clear **Clean now** and **Cancel** buttons. Completion and cancellation appear as brief notifications, so you do not have to dismiss a second modal warning. If any item cannot be removed, the add-on logs the details and the notification points to the Kodi log. Thumbnail cleanup uses Kodi's Textures.GetTextures and Textures.RemoveTexture JSON-RPC methods so texture records and cached files stay in sync.

## Automatic cleanup

Automatic cleanup and thumbnail clearing are enabled at startup. Existing profiles receive these defaults once when the updated add-on starts; you can turn either option off in add-on settings. Cleanup waits until Kodi is idle and TV Guide startup preparation is not running, with a 30-minute maximum wait. It starts after Kodi has settled.

Cleared thumbnails are downloaded again as you browse and may refill storage. The add-on preserves log files in the temporary directory and does not clear add-on settings, libraries, watched status, Trakt data, or Kodi databases.
