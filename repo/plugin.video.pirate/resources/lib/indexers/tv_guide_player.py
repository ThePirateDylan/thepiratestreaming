"""Single-owner playback lifecycle for programs launched from the guide."""
from indexers.tv_guide_trace import event
from threading import Event
from uuid import uuid4

from modules import kodi_utils as ku
from modules.player import FenLightPlayer
from modules.sources import Sources


class GuideSources(Sources):
	def _kill_progress_dialog(self):
		# Only close the dialog created by this invocation. Kodi restores its own
		# video window and selected guide row when the fullscreen player leaves.
		dialog, worker = self.progress_dialog, self.progress_thread
		self.progress_dialog = self.progress_thread = None
		if dialog:
			dialog.close()
		if worker:
			worker.join()


class GuidePlayer(FenLightPlayer):
	owner_key = 'fenlight.tvguide.playback_owner'

	def __init__(self):
		self._ended = Event()
		self._failed = False
		self._closed = True
		self._stop_sent = False
		self._owner = uuid4().hex
		super().__init__()

	def play(self, *args, **kwargs):
		# Terminal events are broadcast to registered players, including other
		# attempts. Only accept them during our own native play call and monitor.
		self._closed = False
		return super().play(*args, **kwargs)

	def run(self, url=None, obj=None):
		ku.set_property(self.owner_key, self._owner)
		try:
			return super().run(url, obj)
		finally:
			self._closed = True
			self._ended.set()
			if self._owns_session():
				self.clear_playback_properties()
				ku.clear_property(self.owner_key)
			self.sources_object = None
			event('player cleanup complete')

	def _owns_session(self):
		return ku.get_property(self.owner_key) == self._owner

	def clear_playback_properties(self):
		if self._owns_session():
			super().clear_playback_properties()

	def onPlayBackStopped(self):
		if self._closed: return
		self._ended.set()
		event('stop callback')

	def onPlayBackEnded(self):
		if not self._closed: self._ended.set()

	def onPlayBackError(self):
		if self._closed: return
		self._failed = True
		self._ended.set()

	def stop(self):
		if self._closed or self._stop_sent or self._ended.is_set() or not self._owns_session():
			return
		self._stop_sent = True
		super().stop()

	def playback_interrupted(self):
		return self._ended.is_set() or not self._owns_session() or self.kodi_monitor.abortRequested()

	def wait_for_sample(self):
		return not self._ended.wait(1) and not self.playback_interrupted() and self.isPlayingVideo()

	def check_playback_start(self):
		super().check_playback_start()
		if self._failed and self._owns_session():
			self.cancel_all_playback = False
			self.playback_successful = False
		if self.playback_successful:
			self.sources_object.playback_successful = True
			from indexers.tv_guide_guard import playback_started
			playback_started()
			self.playback_started()

	def playback_started(self):
		pass

	def playback_close_dialogs(self):
		self.sources_object.playback_successful = True
		self.kill_dialog()

	def kill_dialog(self):
		if self.sources_object:
			self.sources_object._kill_progress_dialog()

	def dispatch_progress(self, function, params):
		# Already on the plug-in invocation thread. Finish its bookmark/watch
		# update before Kodi releases this interpreter and its Player wrapper.
		if self._owns_session() and not self.kodi_monitor.abortRequested():
			self.run_media_progress(function, params)

	def make_listing(self):
		item = super().make_listing()
		logo = self.sources_object.params.get('tv_guide_channel_logo')
		if logo:
			item.setArt({'pirate_channel_logo': logo})
		return item
