"""Age-limited cleanup of disposable files; never follows filesystem links."""

import os
import stat
import time


def _protected(name):
    name = name.lower()
    return (
        ".log" in name
        or name.endswith((".db", ".db-wal", ".db-shm", ".db-journal",
                          ".sqlite", ".sqlite3", ".sqlite-wal", ".sqlite-shm",
                          ".sqlite3-wal", ".sqlite3-shm", ".sqlite-journal",
                          ".lock", ".socket"))
        or name in ("archive_cache", "temp", "addon_data", "database")
    )


def prune_old_files(root, age_seconds, packages=False, should_stop=None, now=None):
    result = {"files": 0, "bytes": 0, "errors": [], "cancelled": False}
    should_stop = should_stop or (lambda: False)
    root = os.path.abspath(root)
    # Refuse redirected roots (including Windows junctions).
    if os.path.normcase(os.path.realpath(root)) != os.path.normcase(root):
        result["errors"].append("Skipped redirected cleanup folder")
        return result
    if not os.path.isdir(root):
        return result
    cutoff = (time.time() if now is None else now) - age_seconds

    def visit(folder):
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    if should_stop():
                        result["cancelled"] = True
                        return
                    try:
                        info = entry.stat(follow_symlinks=False)
                        if (entry.is_symlink()
                                or getattr(info, "st_file_attributes", 0) & 0x400):
                            continue
                        target = os.path.realpath(entry.path)
                        if os.path.commonpath((root, target)) != root:
                            continue
                        if _protected(entry.name):
                            continue
                        if stat.S_ISDIR(info.st_mode):
                            if not packages:
                                visit(entry.path)
                            if result["cancelled"]:
                                return
                            continue
                        if not stat.S_ISREG(info.st_mode):
                            continue
                        if packages and not entry.name.lower().endswith(".zip"):
                            continue
                        if info.st_mtime <= 0 or info.st_mtime >= cutoff:
                            continue
                        # DirEntry.stat reports zero inode/device on Windows.
                        # Take a full stat before comparing file identity.
                        original = os.stat(entry.path, follow_symlinks=False)
                        # Recheck immediately before deletion; a file may have been
                        # replaced or updated while the directory was scanned.
                        current = os.stat(entry.path, follow_symlinks=False)
                        if (not stat.S_ISREG(current.st_mode)
                                or getattr(current, "st_file_attributes", 0) & 0x400
                                or current.st_mtime >= cutoff
                                or current.st_mtime != info.st_mtime
                                or current.st_size != info.st_size
                                or (current.st_dev, current.st_ino) != (original.st_dev, original.st_ino)):
                            continue
                        if should_stop():
                            result["cancelled"] = True
                            return
                        os.remove(entry.path)
                        result["files"] += 1
                        result["bytes"] += current.st_size
                    except OSError as exc:
                        result["errors"].append("Could not clean %s (OS error %s)" %
                                                (entry.name, exc.errno))
        except OSError as exc:
            result["errors"].append("Could not read cleanup folder (OS error %s)" % exc.errno)

    visit(root)
    return result
