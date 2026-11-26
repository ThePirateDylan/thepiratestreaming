"""Copy legacy Pirate menus once, leaving the original add-on's data untouched."""

import os
import tempfile

LEGACY_ID = 'script.skinshortcuts'
ADDON_ID = 'script.pirate.shortcuts'
MARKER = '.pirate-v2-imported'


def _owned_file(name):
    if name in ('skin.pirate.properties', 'settings.xml'):
        return True
    if name.endswith('.DATA.xml'):
        return name.startswith('skin.pirate-') or not name.startswith('skin.')
    # Legacy generated playlists are referenced by menu actions.
    return name.endswith('.xsp')


def _write_new(path, data):
    if os.path.exists(path):
        return False
    fd, temporary = tempfile.mkstemp(prefix='.pirate-import-', dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        if os.path.exists(path):
            return False
        os.replace(temporary, path)
        return True
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def migrate_profile(profile):
    """Import this profile's v2 menus; never replace an existing Pirate setting.

    Hashes are deliberately excluded so the owned engine builds its own includes.
    The marker is written last. An interrupted copy can safely resume on next run.
    """
    source = os.path.join(profile, 'addon_data', LEGACY_ID)
    target = os.path.join(profile, 'addon_data', ADDON_ID)
    marker = os.path.join(target, MARKER)
    if os.path.exists(marker):
        return 0
    os.makedirs(target, exist_ok=True)
    copied = 0
    if os.path.isdir(source):
        for name in sorted(os.listdir(source)):
            original = os.path.join(source, name)
            if not _owned_file(name) or not os.path.isfile(original) or os.path.islink(original):
                continue
            with open(original, 'rb') as stream:
                data = stream.read()
            # Keep user labels, paths and assignments; redirect only our engine references.
            data = data.replace(b'RunScript(script.skinshortcuts,', b'RunScript(script.pirate.shortcuts,')
            data = data.replace(b'$ADDON[script.skinshortcuts ', b'$ADDON[script.pirate.shortcuts ')
            if name == 'settings.xml':
                data = data.replace(b'script.skinshortcuts', b'script.pirate.shortcuts')
            data = data.replace(b'addon_data/script.skinshortcuts/', b'addon_data/script.pirate.shortcuts/')
            data = data.replace(b'addon_data\\script.skinshortcuts\\', b'addon_data\\script.pirate.shortcuts\\')
            copied += _write_new(os.path.join(target, name), data)
    _write_new(marker, b'1\n')
    return copied
