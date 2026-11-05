"""Non-blocking guide ownership across Kodi plugin and service interpreters."""
from contextlib import contextmanager, closing
from threading import local
import os
import sqlite3

from modules import kodi_utils

_tuning = local()

@contextmanager
def operation(name):
	# Separate empty databases let lineup preparation and tuning proceed independently.
	# SQLite releases the reservation even if Kodi terminates an interpreter.
	profile = kodi_utils.addon_profile()
	os.makedirs(profile, exist_ok=True)
	path = os.path.join(profile, 'tvguide_%s.lock.db' % name)
	with closing(sqlite3.connect(path, timeout=0)) as connection:
		try:
			connection.execute('BEGIN IMMEDIATE')
		except sqlite3.OperationalError as exc:
			if 'locked' not in str(exc).lower() and 'busy' not in str(exc).lower():
				raise
			yield None
		else:
			yield connection

@contextmanager
def tuning_request():
	with operation('tune') as connection:
		if connection is None:
			yield False
			return
		_tuning.connection = connection
		try:
			kodi_utils.set_property('fenlight.tvguide_tuning', 'true')
			yield True
		finally:
			playback_started()

def playback_started():
	connection = getattr(_tuning, 'connection', None)
	if connection is not None:
		kodi_utils.clear_property('fenlight.tvguide_tuning')
		_tuning.connection = None
		connection.rollback()
