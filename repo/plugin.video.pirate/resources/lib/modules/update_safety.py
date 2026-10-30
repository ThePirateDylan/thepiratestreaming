"""Fail-closed update guard for private development packages."""

from os.path import dirname, isfile, join


_PRIVATE_BUILD_MARKER = join(dirname(dirname(__file__)), 'PRIVATE_DEVELOPMENT_BUILD')


def is_private_development_build(marker_path=None):
	return isfile(marker_path or _PRIVATE_BUILD_MARKER)


def block_private_updates(kodi_utils):
	if not is_private_development_build(): return False
	kodi_utils.ok_dialog(
		heading='Private Development Build',
		text='Online update and rollback are disabled for this private build. Install updates from a manually transferred ZIP.'
	)
	return True
