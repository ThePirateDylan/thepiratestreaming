"""Passive, request-owned tuning artwork. Never starts, stops or seeks playback."""
from time import monotonic
from uuid import uuid4

from modules import kodi_utils as ku


class GuideSignal:
	key = 'fenlight.tvguide.signal'

	def __init__(self):
		self.token = uuid4().hex
		self.active = False
		self.target = None
		self.seek_started = None
		self.deadline = None

	def begin(self):
		self.target = self.seek_started = self.deadline = None
		self.active = True
		ku.set_property(self.key, self.token)

	def player_started(self):
		# Fail open if Kodi never confirms the join. This is not a success signal.
		self.deadline = monotonic() + 20.0

	def seeking(self, target):
		self.target = float(target)
		self.seek_started = monotonic()

	def sample(self, pending, position, stable):
		if not self.active:
			return
		if ku.get_property(self.key) != self.token:
			self.active = False
			return
		if self.expired():
			return
		if pending or not stable:
			return
		if self.target is None:
			# No scheduled jump, or the existing player declined an unsafe jump.
			self.close()
			return
		elapsed = monotonic() - self.seek_started
		tolerance = max(3.0, min(15.0, self.target * 0.05))
		if abs(float(position) - (self.target + elapsed)) <= tolerance:
			self.close()

	def expired(self):
		if self.active and self.deadline is not None and monotonic() >= self.deadline:
			self.close()
			return True
		return False

	def close(self):
		if self.active and ku.get_property(self.key) == self.token:
			ku.clear_property(self.key)
		self.active = False
