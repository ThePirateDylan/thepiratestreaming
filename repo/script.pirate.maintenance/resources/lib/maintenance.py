#!/usr/bin/python
# -*- coding: utf-8 -*-

import json
import os
from urllib.parse import unquote
import xml.etree.ElementTree as ET

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from resources.lib.housekeeping import _protected as _protected_runtime_item


ADDON_ID = "script.pirate.maintenance"
ADDON = xbmcaddon.Addon(ADDON_ID)
TITLE = ADDON.getLocalizedString(32010) or ADDON.getAddonInfo("name")
LOG_PREFIX = "The Pirate Maintenance"


def cleanup_is_busy(automatic=False):
    """Do not start or continue automatic deletion while Kodi needs the files."""
    try:
        window = xbmcgui.Window(10000)
        return bool(
            xbmc.Player().isPlaying()
            or xbmc.getCondVisibility(
                "Window.IsActive(busydialog) | Window.IsActive(busydialognocancel)"
            )
            or (automatic and xbmc.getCondVisibility("Window.IsActive(addonbrowser)"))
            or window.getProperty("fenlight.tvguide_preload_running") == "true"
            or window.getProperty("fenlight.tvguide_loading")
        )
    except Exception:
        # If Kodi's state cannot be determined, leave its files alone.
        return True


class CleanupCancelled(Exception):
    pass


def log(message, level=xbmc.LOGINFO):
    xbmc.log("%s: %s" % (LOG_PREFIX, message), level)


def _new_result():
    return {
        "temp_files": 0,
        "package_files": 0,
        "artwork_entries": 0,
        "bytes_freed": 0,
        "errors": [],
        "cancelled": False,
    }


def _translate(path):
    try:
        return xbmcvfs.translatePath(path)
    except Exception:
        return path


def _file_size(path):
    try:
        return max(0, int(xbmcvfs.Stat(path).st_size()))
    except Exception:
        return 0


def _count_files(path, preserve_runtime=False):
    try:
        directories, files = xbmcvfs.listdir(path)
    except Exception:
        return 0

    count = 0
    for filename in files:
        if preserve_runtime and _protected_runtime_item(filename):
            continue
        count += 1

    for directory in directories:
        if preserve_runtime and _protected_runtime_item(directory):
            continue
        count += _count_files(os.path.join(path, directory), preserve_runtime)
    return count


def _clear_tree(path, result, key, progress, monitor, start, span, preserve_runtime=False):
    if not xbmcvfs.exists(path):
        return

    total = max(1, _count_files(path, preserve_runtime))
    completed = 0

    def update_progress():
        if progress is None:
            return
        percent = start + int((float(completed) / total) * span)
        progress.update(
            min(99, percent),
            "%s\n%d / %d" % (
                ADDON.getLocalizedString(32021 if key == "temp_files" else 32022),
                completed, total),
        )

    def visit(folder):
        nonlocal completed
        try:
            directories, files = xbmcvfs.listdir(folder)
        except Exception as exc:
            result["errors"].append(str(exc))
            return

        for filename in files:
            if preserve_runtime and _protected_runtime_item(filename):
                continue
            if monitor.abortRequested():
                raise CleanupCancelled()
            if progress is not None and progress.iscanceled():
                raise CleanupCancelled()

            file_path = os.path.join(folder, filename)
            size = _file_size(file_path)
            try:
                removed = xbmcvfs.delete(file_path)
            except Exception as exc:
                removed = False
                result["errors"].append(str(exc))

            if removed:
                result[key] += 1
                result["bytes_freed"] += size
            else:
                result["errors"].append("Could not remove an item from %s" % folder)

            completed += 1
            if completed == 1 or completed % 8 == 0 or completed == total:
                update_progress()

        for directory in directories:
            if preserve_runtime and _protected_runtime_item(directory):
                continue
            if monitor.abortRequested():
                raise CleanupCancelled()
            child_path = os.path.join(folder, directory)
            visit(child_path)
            try:
                xbmcvfs.rmdir(child_path)
            except Exception:
                pass

    visit(path)


def _directory_size(path):
    try:
        directories, files = xbmcvfs.listdir(path)
    except Exception:
        return 0

    total = sum(_file_size(os.path.join(path, filename)) for filename in files)
    for directory in directories:
        total += _directory_size(os.path.join(path, directory))
    return total


def _json_rpc(method, params=None):
    request = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": 1,
    }
    response = xbmc.executeJSONRPC(json.dumps(request))
    try:
        payload = json.loads(response)
    except Exception as exc:
        raise RuntimeError("Kodi returned an invalid JSON-RPC response") from exc

    if "error" in payload:
        error = payload["error"]
        raise RuntimeError("Kodi JSON-RPC error %s: %s" % (error.get("code"), error.get("message")))
    return payload.get("result")


def _get_texture_ids(allowed_urls=None):
    response = _json_rpc("Textures.GetTextures", {"properties": ["url"]})
    if not isinstance(response, dict):
        raise RuntimeError("Kodi did not return its cached texture list")
    textures = response.get("textures", [])
    return [texture["textureid"] for texture in textures
            if "textureid" in texture and (allowed_urls is None
                or _artwork_key(texture.get("url", "")) in allowed_urls)]


def _clear_textures(result, progress, monitor, start=60, span=39,
                    allowed_urls=None, should_stop=None):
    texture_ids = _get_texture_ids(allowed_urls)
    total = len(texture_ids)
    before_size = _directory_size(_translate("special://thumbnails"))

    for index, texture_id in enumerate(texture_ids, 1):
        if monitor.abortRequested() or (should_stop is not None and should_stop()):
            raise CleanupCancelled()
        if progress is not None and progress.iscanceled():
            raise CleanupCancelled()
        try:
            _json_rpc("Textures.RemoveTexture", {"textureid": texture_id})
            result["artwork_entries"] += 1
        except Exception as exc:
            result["errors"].append(str(exc))

        if progress is not None and (index == 1 or index % 20 == 0 or index == total):
            percent = start + int((float(index) / max(1, total)) * span)
            progress.update(
                min(99, percent),
                "%s\n%d / %d" % (ADDON.getLocalizedString(32023), index, total),
            )
        if index % 20 == 0:
            xbmc.sleep(5)

    after_size = _directory_size(_translate("special://thumbnails"))
    result["bytes_freed"] += max(0, before_size - after_size)


def _artwork_key(url):
    if url.startswith("image://"):
        url = unquote(url[len("image://"):]).rstrip("/")
    url = url.split("|", 1)[0]
    return os.path.normcase(_translate(url)).replace("\\", "/")


def _pirate_artwork_urls():
    """Only add-on branding, never posters, fanart from widgets, or user media."""
    urls = set()
    ids = ("skin.pirate", "plugin.video.pirate", "repository.pirate",
           "resource.uisounds.pirate", "screensaver.pirate", "script.pirate.widgets",
           "plugin.video.tmdb.pirate.helper", "script.pirate.toolbox",
           "script.pirate.shortcuts", "script.pirate.helper", "script.module.pirate",
           "script.pirate.maintenance")
    for addon_id in ids:
        try:
            addon_path = xbmcaddon.Addon(addon_id).getAddonInfo("path")
            handle = xbmcvfs.File(os.path.join(addon_path, "addon.xml"))
            try:
                root = ET.fromstring(handle.read())
            finally:
                handle.close()
            assets = root.findall("./extension[@point='xbmc.addon.metadata']/assets/*")
            paths = [item.text for item in assets if item.tag in ("icon", "fanart") and item.text]
            paths += ["icon.png", "fanart.jpg"]
            if addon_id == "skin.pirate":
                paths += ["skin_icon.png", "media/branding/thepirate-logo.png"]
            elif addon_id == "plugin.video.pirate":
                paths += ["resources/media/addon_icons/pirate_icon.png",
                          "resources/media/fenlight_fanart_01.jpg", "resources/media/thepirate-logo.png"]
            for path in paths:
                urls.add(_artwork_key(os.path.join(addon_path, path)))
                urls.add(_artwork_key("special://home/addons/%s/%s" % (addon_id, path)))
        except Exception:
            # An optional Pirate component may not be installed on this profile.
            continue
    return urls


def run_startup_cleanup(include_artwork=False, monitor=None):
    from resources.lib.housekeeping import prune_old_files

    result = _new_result()
    monitor = monitor or xbmc.Monitor()
    should_stop = lambda: monitor.abortRequested() or cleanup_is_busy(automatic=True)
    seen = set()
    for path, age, key, packages in (
        ("special://temp", 86400, "temp_files", False),
        ("special://home/cache", 86400, "temp_files", False),
        ("special://home/addons/packages", 7 * 86400, "package_files", True),
    ):
        folder = _translate(path)
        canonical = os.path.normcase(os.path.realpath(folder))
        if canonical in seen:
            continue
        seen.add(canonical)
        part = prune_old_files(folder, age, packages=packages, should_stop=should_stop)
        result[key] += part["files"]
        result["bytes_freed"] += part["bytes"]
        result["errors"].extend(part["errors"])
        if part["cancelled"]:
            result["cancelled"] = True
            return result
    if include_artwork and not should_stop():
        try:
            _clear_textures(result, None, monitor, should_stop=should_stop)
        except CleanupCancelled:
            result["cancelled"] = True
        except Exception as exc:
            result["errors"].append(str(exc))
    return result


def refresh_pirate_artwork(monitor=None):
    result = _new_result()
    monitor = monitor or xbmc.Monitor()
    progress = xbmcgui.DialogProgress()
    progress.create(TITLE, ADDON.getLocalizedString(32033))
    try:
        if cleanup_is_busy():
            raise CleanupCancelled()
        _clear_textures(result, progress, monitor, start=0, span=100,
                        allowed_urls=_pirate_artwork_urls(), should_stop=cleanup_is_busy)
    except CleanupCancelled:
        result["cancelled"] = True
    except Exception as exc:
        result["errors"].append(str(exc))
    finally:
        progress.close()
    return result


def run_cleanup(include_artwork=True, interactive=False, monitor=None):
    result = _new_result()
    monitor = monitor or xbmc.Monitor()
    progress = xbmcgui.DialogProgress() if interactive else None

    if progress is not None:
        progress.create(TITLE, ADDON.getLocalizedString(32024))

    try:
        temp_path = _translate("special://temp")
        packages_path = _translate("special://home/addons/packages")
        _clear_tree(
            temp_path,
            result,
            "temp_files",
            progress,
            monitor,
            start=5,
            span=30,
            preserve_runtime=True,
        )
        if monitor.abortRequested():
            raise CleanupCancelled()

        _clear_tree(
            packages_path,
            result,
            "package_files",
            progress,
            monitor,
            start=38,
            span=21,
        )
        if monitor.abortRequested():
            raise CleanupCancelled()

        if include_artwork:
            _clear_textures(result, progress, monitor)
    except CleanupCancelled:
        result["cancelled"] = True
    except Exception as exc:
        result["errors"].append(str(exc))
        log("cleanup error: %s" % exc, xbmc.LOGERROR)
    finally:
        if progress is not None:
            progress.close()

    return result


def _format_size(byte_count):
    size = float(byte_count)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return "%.1f %s" % (size, unit)
        size /= 1024


def _summary(result):
    lines = [
        "%s: %d" % (ADDON.getLocalizedString(32017), result["temp_files"]),
        "%s: %d" % (ADDON.getLocalizedString(32018), result["package_files"]),
        "%s: %d" % (ADDON.getLocalizedString(32019), result["artwork_entries"]),
        "%s: %s" % (ADDON.getLocalizedString(32020), len(result["errors"])),
        _format_size(result["bytes_freed"]),
    ]
    return "\n".join(lines)


def run_manual():
    dialog = xbmcgui.Dialog()
    icon = ADDON.getAddonInfo("icon")

    if cleanup_is_busy():
        dialog.notification(
            TITLE,
            ADDON.getLocalizedString(32013),
            icon,
            5000,
            False,
        )
        return

    selected = dialog.select(
        ADDON.getLocalizedString(32011),
        [
            ADDON.getLocalizedString(32001),
            ADDON.getLocalizedString(32033),
            ADDON.getLocalizedString(32029),
        ],
    )
    if selected not in (0, 1):
        return

    result = (run_cleanup(include_artwork=True, interactive=True) if selected == 0
              else refresh_pirate_artwork())
    if result["cancelled"]:
        dialog.notification(
            TITLE,
            ADDON.getLocalizedString(32015),
            icon,
            5000,
            False,
        )
        return

    for error in result["errors"]:
        log("manual cleanup detail: %s" % error, xbmc.LOGWARNING)

    heading_id = 32031 if result["errors"] else 32014
    summary = ADDON.getLocalizedString(32030) % (
        result["temp_files"],
        result["package_files"],
        result["artwork_entries"],
        _format_size(result["bytes_freed"]),
    )
    if result["errors"]:
        summary += "\n" + ADDON.getLocalizedString(32032)

    dialog.notification(
        ADDON.getLocalizedString(heading_id),
        summary,
        icon,
        7000,
        False,
    )
