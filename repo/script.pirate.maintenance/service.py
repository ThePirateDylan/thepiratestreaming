#!/usr/bin/python
# -*- coding: utf-8 -*-

import time

import xbmc
import xbmcaddon
import xbmcgui

from resources.lib.maintenance import run_cleanup


ADDON_ID = "script.pirate.maintenance"
STARTUP_DELAY = 3
MAX_IDLE_WAIT = 1800


def log(message, level=xbmc.LOGINFO):
    xbmc.log("The Pirate Maintenance: %s" % message, level)


def _apply_startup_defaults(addon):
    """Enable the requested boot cleanup once on upgrade while preserving future opt-outs."""
    if addon.getSetting("startup_defaults_migrated") == "true":
        return
    addon.setSetting("startup_cleanup", "true")
    addon.setSetting("startup_clear_artwork", "true")
    addon.setSetting("startup_defaults_migrated", "true")


def guide_preload_running():
    try:
        return xbmcgui.Window(10000).getProperty("fenlight.tvguide_preload_running") == "true"
    except Exception:
        return False


def kodi_is_busy():
    try:
        if xbmc.Player().isPlaying():
            return True
    except Exception:
        pass

    try:
        return bool(xbmc.getCondVisibility("Window.IsActive(busydialog)"))
    except Exception:
        return False


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
        result = run_cleanup(
            include_artwork=clear_artwork,
            interactive=False,
            monitor=monitor,
        )
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
        if result["temp_files"] or result["package_files"] or result["artwork_entries"]:
            xbmcgui.Dialog().notification(
                addon.getAddonInfo("name"),
                "Startup cleanup completed",
                addon.getAddonInfo("icon"),
                4000,
            )
    except Exception as exc:
        log("startup cleanup failed: %s" % exc, xbmc.LOGERROR)


run()
