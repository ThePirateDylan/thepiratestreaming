#!/usr/bin/python
# -*- coding: utf-8 -*-

import json
import os

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs


ADDON_ID = "script.pirate.maintenance"
ADDON = xbmcaddon.Addon(ADDON_ID)
TITLE = ADDON.getLocalizedString(32010) or ADDON.getAddonInfo("name")
LOG_PREFIX = "The Pirate Maintenance"


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


def _is_log_file(name):
    filename = name.lower()
    return ".log" in filename


def _count_files(path, preserve_logs=False):
    try:
        directories, files = xbmcvfs.listdir(path)
    except Exception:
        return 0

    count = 0
    for filename in files:
        if preserve_logs and _is_log_file(filename):
            continue
        count += 1

    for directory in directories:
        count += _count_files(os.path.join(path, directory), preserve_logs)
    return count


def _clear_tree(path, result, key, progress, monitor, start, span, preserve_logs=False):
    if not xbmcvfs.exists(path):
        return

    total = max(1, _count_files(path, preserve_logs))
    completed = 0

    def update_progress():
        if progress is None:
            return
        percent = start + int((float(completed) / total) * span)
        progress.update(
            min(99, percent),
            ADDON.getLocalizedString(32021 if key == "temp_files" else 32022),
            "%d / %d" % (completed, total),
        )

    def visit(folder):
        nonlocal completed
        try:
            directories, files = xbmcvfs.listdir(folder)
        except Exception as exc:
            result["errors"].append(str(exc))
            return

        for filename in files:
            if preserve_logs and _is_log_file(filename):
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


def _get_texture_ids():
    response = _json_rpc("Textures.GetTextures", {"properties": ["url"]})
    if not isinstance(response, dict):
        raise RuntimeError("Kodi did not return its cached texture list")
    textures = response.get("textures", [])
    return [texture["textureid"] for texture in textures if "textureid" in texture]


def _clear_textures(result, progress, monitor, start=60, span=39):
    texture_ids = _get_texture_ids()
    total = len(texture_ids)
    before_size = _directory_size(_translate("special://thumbnails"))

    for index, texture_id in enumerate(texture_ids, 1):
        if monitor.abortRequested():
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
                ADDON.getLocalizedString(32023),
                "%d / %d" % (index, total),
            )
        if index % 20 == 0:
            xbmc.sleep(5)

    after_size = _directory_size(_translate("special://thumbnails"))
    result["bytes_freed"] += max(0, before_size - after_size)


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
            preserve_logs=True,
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

    if xbmc.Player().isPlaying() or xbmc.getCondVisibility("Window.IsActive(DialogBusy)"):
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
            ADDON.getLocalizedString(32029),
        ],
    )
    if selected != 0:
        return

    result = run_cleanup(include_artwork=True, interactive=True)
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
