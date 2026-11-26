#!/usr/bin/python
# -*- coding: utf-8 -*-

import time

import xbmc
import xbmcaddon
import xbmcgui

from resources.lib.maintenance import cleanup_is_busy, run_startup_cleanup


ADDON_ID = "script.pirate.maintenance"
STARTUP_DELAY = 3
MAX_IDLE_WAIT = 1800


def log(message, level=xbmc.LOGINFO):
    xbmc.log("The Pirate Maintenance: %s" % message, level)


def _apply_startup_defaults(addon):
    """Migrate the old forced thumbnail wipe to the conservative startup policy."""
    if addon.getSetting("startup_policy_migrated") == "true":
        return
    addon.setSetting("startup_clear_artwork", "false")
    addon.setSetting("startup_defaults_migrated", "true")
    addon.setSetting("startup_policy_migrated", "true")


def kodi_is_busy():
    return cleanup_is_busy(automatic=True)


def run():
    addon = xbmcaddon.Addon(ADDON_ID)
    monitor = xbmc.Monitor()
    _apply_startup_defaults(addon)

    if not addon.getSettingBool("startup_cleanup"):
        log("startup cleanup is disabled in settings")
        return

    log("startup cleanup is enabled; waiting for Kodi startup to settle")
    if monitor.waitForAbort(STARTUP_DELAY):
        return

    deadline = time.time() + MAX_IDLE_WAIT
    while not monitor.abortRequested() and kodi_is_busy():
        if time.time() >= deadline:
            log("startup cleanup skipped because Kodi did not become idle")
            return
        if monitor.waitForAbort(10):
            return

    if monitor.abortRequested():
        return

    clear_artwork = addon.getSettingBool("startup_clear_artwork")
    try:
        result = run_startup_cleanup(
            include_artwork=clear_artwork,
            monitor=monitor,
        )
        if result["cancelled"]:
            log("startup cleanup stopped because Kodi became busy or is shutting down")
            return
        log(
            "startup cleanup finished: %d temporary files, %d packages, "
            "%d artwork entries, %d errors"
            % (
                result["temp_files"],
                result["package_files"],
                result["artwork_entries"],
                len(result["errors"]),
            )
        )
        for error in result["errors"]:
            log("startup cleanup detail: %s" % error, xbmc.LOGWARNING)
        if result["errors"]:
            message = addon.getLocalizedString(32031)
        elif result["temp_files"] or result["package_files"] or result["artwork_entries"]:
            message = addon.getLocalizedString(32035)
        else:
            message = addon.getLocalizedString(32034)
        xbmcgui.Dialog().notification(
            addon.getAddonInfo("name"),
            message,
            addon.getAddonInfo("icon"),
            4000,
            False,
        )
    except Exception as exc:
        log("startup cleanup failed: %s" % exc, xbmc.LOGERROR)


if __name__ == "__main__":
    run()
