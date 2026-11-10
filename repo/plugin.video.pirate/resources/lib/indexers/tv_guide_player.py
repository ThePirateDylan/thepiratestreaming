"""Single-owner playback lifecycle for programs launched from the guide."""
from indexers.tv_guide_trace import event
from threading import Event
from uuid import uuid4

from modules import kodi_utils as ku
from modules.player import FenLightPlayer
from modules.sources import Sources


class GuideSources(Sources):
	def playback_prep(self, *args, **kwargs):
		# One visual request covers scraping, resolution and the scheduled join.
		# Recursive rescrapes retain the outer request and its cleanup ownership.
		if getattr(self, '_guide_signal', None) is not None:
			return super().playback_prep(*args, **kwargs)
		from indexers.tv_guide_signal import GuideSignal
		signal = self._guide_signal = GuideSignal()
		try:
			signal.begin()
			return super().playback_prep(*args, **kwargs)
		finally:
			signal.close()
			self._guide_signal = None

	def _make_progress_dialog(self):
		# Same dialog and worker as Sources; stamp ownership BEFORE run starts so
		# its first rendered scraper frame already has the signal visibility state.
		from windows.base_window import create_window
		from threading import Thread
		self.progress_dialog = create_window(('windows.sources', 'SourcesPlayback'), 'sources_playback.xml', meta=self.meta)
		signal = getattr(self, '_guide_signal', None)
		if signal and self.progress_dialog:
			self.progress_dialog.setProperty('pirate_signal_token', signal.token)
		self.progress_thread = Thread(target=self.progress_dialog.run)
		self.progress_thread.start()

	def resolve_sources(self, *args, **kwargs):
		# A failed URL lookup must not blink the mask between source retries.
		# A failed native player can clear it; re-arm only if no newer request owns it.
		signal = getattr(self, '_guide_signal', None)
		if signal and not signal.active and ku.get_property(signal.key) in ('', signal.token):
			signal.begin()
		return super().resolve_sources(*args, **kwargs)

	def play_file(self, *args, **kwargs):
		try:
			return super().play_file(*args, **kwargs)
		finally:
			signal = getattr(self, '_guide_signal', None)
			if signal: signal.close()

	def _kill_progress_dialog(self):
		# Only close the dialog created by this invocation. Kodi restores its own
		# video window and selected guide row when the fullscreen player leaves.
		dialog, worker = self.progress_dialog, self.progress_thread
		self.progress_dialog = self.progress_thread = None
		if dialog:
			event('progress dialog close begin')
			dialog.close()
		if worker:
			event('progress worker join begin')
			worker.join()
		if dialog or worker: event('progress dialog cleanup complete')


class GuidePlayer(FenLightPlayer):
	owner_key = 'fenlight.tvguide.playback_owner'

	def __init__(self):
		self._signal = None
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
		self._signal = getattr(obj, '_guide_signal', None)
		event('player run enter owner=' + self._owner)
		ku.set_property(self.owner_key, self._owner)
		try:
			return super().run(url, obj)
		finally:
			if self._signal: self._signal.close()
			event('player cleanup begin owner=' + self._owner)
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
		if self._signal: self._signal.expired()
		return not self._ended.wait(1) and not self.playback_interrupted() and self.isPlayingVideo()

	def check_playback_start(self):
		super().check_playback_start()
		if self._failed and self._owns_session():
			self.cancel_all_playback = False
			self.playback_successful = False
		if self.playback_successful:
			if self._signal: self._signal.player_started()
			event('video started; scheduled join not yet checked')
			self.sources_object.playback_successful = True
			from indexers.tv_guide_guard import playback_started
			playback_started()
			self.playback_started()

	def playback_started(self):
		pass

	def monitor(self):
		event('monitor enter')
		try:
			return super().monitor()
		finally:
			event('monitor returned')

	def seekTime(self, target):
		if self._signal: self._signal.seeking(target)
		event('scheduled seek dispatch')
		try:
			return super().seekTime(target)
		except Exception:
			if self._signal: self._signal.close()
			raise
		finally:
			# Return from the native request is not confirmation of seek completion.
			event('scheduled seek request returned')

	def playback_position_sample(self, join_pending, position):
		if self._signal and self._signal.active:
			self._signal.sample(join_pending, position,
				not ku.get_visibility('Player.Seeking | Player.Caching'))

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
			event('progress update begin operation=' + getattr(function, '__name__', 'callable'), stack=True)
			try:
				self.run_media_progress(function, params)
			finally:
				event('progress update returned')

	def make_listing(self):
		item = super().make_listing()
		if self._signal:
			# Token is compared by the skin; it is never rendered as an image.
			item.setArt({'pirate_signal_token': self._signal.token})
		logo = self.sources_object.params.get('tv_guide_channel_logo')
		if logo:
			item.setArt({'pirate_channel_logo': logo})
		return item
