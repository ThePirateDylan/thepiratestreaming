# -*- coding: utf-8 -*-
from xbmc import Monitor
import os
import json
import inspect
from time import time
from threading import Thread
from caches.settings_cache import get_setting, set_setting, sync_settings
from modules import kodi_utils

pause_services_prop = 'fenlight.pause_services'
firstrun_update_prop = 'fenlight.firstrun_update'
current_skin_prop = 'fenlight.current_skin'
trakt_service_string = 'TraktMonitor Service Update %s - %s'
trakt_success_line_dict = {'success': 'Trakt Update Performed', 'no account': '(Unauthorized) Trakt Update Performed'}
update_string = 'Next Update in %s minutes...'

class SetAddonConstants:
	def run(self):
		kodi_utils.logger('The Pirate', 'SetAddonConstants Service Starting')
		import random
		current_addon_version = kodi_utils.addon_info('version')
		previous_addon_version = kodi_utils.get_property('fenlight.addon_version')
		if previous_addon_version and previous_addon_version != current_addon_version:
			set_setting('changelog.pending_previous_version', previous_addon_version)
		addon_items = [
			('fenlight.playback_key', str(random.randint(1000, 10000))),
			('fenlight.addon_version', current_addon_version),
			('fenlight.addon_path', kodi_utils.addon_info('path')),
			('fenlight.addon_profile', kodi_utils.translate_path(kodi_utils.addon_info('profile'))),
			('fenlight.addon_icon', kodi_utils.translate_path(kodi_utils.addon_info('icon'))),
			('fenlight.addon_icon_mini', os.path.join(kodi_utils.addon_info('path'), 'resources', 'media', 'addon_icons', 'minis',
			os.path.basename(kodi_utils.translate_path(kodi_utils.addon_info('icon'))))),
			('fenlight.addon_fanart', kodi_utils.addon_fanart())
					]
		for item in addon_items: kodi_utils.set_property(*item)
		return kodi_utils.logger('The Pirate', 'SetAddonConstants Service Finished')

class DatabaseMaintenance:
	def run(self):
		kodi_utils.logger('The Pirate', 'DatabaseMaintenance Service Starting')
		from caches.base_cache import check_databases_integrity
		check_databases_integrity(silent=True)
		return kodi_utils.logger('The Pirate', 'DatabaseMaintenance Service Finished')

class SyncSettings:
	def run(self):
		kodi_utils.logger('The Pirate', 'SyncSettings Service Starting')
		sync_settings()
		return kodi_utils.logger('The Pirate', 'SyncSettings Service Finished')

class OnUpdateChanges:
	def run(self):
		kodi_utils.logger('The Pirate', 'OnUpdateChanges Service Starting')
		try:
			from modules.updater import show_startup_changelog
			show_startup_changelog()
		except Exception as e:
			kodi_utils.logger('OnUpdateChanges', 'Changelog notice failed: %s' % str(e))
		try:
			for method in list(filter(lambda x: x[0] != 'run', inspect.getmembers(OnUpdateChanges, predicate=inspect.isfunction))):
				if not get_setting('fenlight.updatechecks.%s' % method[0], 'false') == 'true':
					method[1](self)
					set_setting('updatechecks.%s' % method[0], 'true')
		except: pass
		return kodi_utils.logger('The Pirate', 'OnUpdateChanges Service Finished')

	def refresh_addon_keys(self):
		# For update 2.2.01 - 03
		from caches.trakt_cache import clear_all_trakt_cache_data
		from caches.tmdb_lists import tmdb_lists_cache
		from caches.settings_cache import restore_setting_default
		show_dialog = False
		if get_setting('fenlight.tmdb_api') == 'b370b60447737762ca38457bd77579b3':
			restore_setting_default({'silent': 'true', 'setting_id': 'tmdb_api'})
			set_setting('tmdb.token', 'empty_setting')
			set_setting('tmdb.account_id', 'empty_setting')
			set_setting('tmdb.username', 'empty_setting')
			set_setting('tmdb.session_id', 'empty_setting')
			set_setting('tmdb.account_session_id', 'empty_setting')
			tmdb_lists_cache.clear_all()
			show_dialog = True
		if get_setting('fenlight.trakt.client') == '1038ef327e86e7f6d39d80d2eb5479bff66dd8394e813c5e0e387af0f84d89fb':
			restore_setting_default({'silent': 'true', 'setting_id': 'trakt.client'})
			set_setting('trakt.user', 'empty_setting')
			set_setting('trakt.expires', '0')
			set_setting('trakt.token', '0')
			set_setting('trakt.refresh', '0')
			set_setting('trakt.next_daily_clear', '0')
			set_setting('watched_indicators', '0')
			clear_all_trakt_cache_data(silent=True, refresh=False)
			show_dialog = True
		if show_dialog:
			text = 'The original developer of The Pirate has revoked all keys (Trakt, TMDb) that have been used up until now '\
			'within this addon, with permission, due to security concerns.'
			kodi_utils.ok_dialog(heading='Addon Credentials Reset', text=text)
			text = 'This unfortunately means you will need to re-authenticate your Trakt & TMDb accounts through The Pirate AM  if you are currently using them. ' \
			'My apologies, but with the previous keys being revoked, this is necessary.'
			kodi_utils.ok_dialog(heading='Addon Credentials Reset', text=text)

class CustomWindowsPrepare:
	def run(self):
		kodi_utils.logger('The Pirate', 'CustomWindowsPrepare Service Starting')
		from windows.base_window import FontUtils, ExtrasUtils
		monitor, player = kodi_utils.kodi_monitor(), kodi_utils.kodi_player()
		wait_for_abort, is_playing = monitor.waitForAbort, player.isPlayingVideo
		kodi_utils.clear_property(current_skin_prop)
		ExtrasUtils().run()
		font_utils = FontUtils()
		while not monitor.abortRequested():
			font_utils.execute_custom_fonts()
			wait_for_abort(20)
		try: del monitor
		except: pass
		try: del player
		except: pass
		return kodi_utils.logger('The Pirate', 'CustomWindowsPrepare Service Finished')

class TraktMonitor:
	def run(self):
		kodi_utils.logger('The Pirate', 'TraktMonitor Service Starting')
		from apis.trakt_api import trakt_sync_activities
		from modules.settings import trakt_user_active, trakt_sync_interval
		monitor, player = kodi_utils.kodi_monitor(), kodi_utils.kodi_player()
		wait_for_abort, is_playing = monitor.waitForAbort, player.isPlayingVideo
		while not monitor.abortRequested():
			while is_playing() or kodi_utils.get_property(pause_services_prop) == 'true': wait_for_abort(10)
			wait_time = 1800
			try:
				sync_interval, wait_time = trakt_sync_interval()
				next_update_string = update_string % sync_interval
				if trakt_user_active: status = trakt_sync_activities()
				else: status = 'no_auth'
				if status == 'failed': kodi_utils.logger('The Pirate', trakt_service_string % ('Failed. Error from Trakt', next_update_string))
				elif status == 'no_auth': kodi_utils.logger('The Pirate', trakt_service_string % ('Not Run. No Current Trakt Account', next_update_string))
				else:
					if status in ('success', 'no account'):
						kodi_utils.logger('The Pirate', trakt_service_string % ('Success. %s' % trakt_success_line_dict[status], next_update_string))
					else:
						kodi_utils.logger('The Pirate', trakt_service_string % ('Success. No Changes Needed', next_update_string))# 'not needed'
					if status == 'success' and get_setting('fenlight.trakt.refresh_widgets', 'false') == 'true':
						kodi_utils.run_plugin({'mode': 'kodi_refresh'})
			except Exception as e: kodi_utils.logger('The Pirate', trakt_service_string % ('Failed', 'The following Error Occured: %s' % str(e)))
			wait_for_abort(wait_time)
		try: del monitor
		except: pass
		try: del player
		except: pass
		return kodi_utils.logger('The Pirate', 'TraktMonitor Service Finished')

class UpdateCheck:
	def run(self):
		if kodi_utils.get_property(firstrun_update_prop) == 'true': return
		kodi_utils.logger('The Pirate', 'UpdateCheck Service Starting')
		from modules.updater import update_check
		from modules.settings import update_action, update_delay
		end_pause = time() + update_delay()
		monitor, player = kodi_utils.kodi_monitor(), kodi_utils.kodi_player()
		wait_for_abort, is_playing = monitor.waitForAbort, player.isPlayingVideo
		while not monitor.abortRequested():
			while time() < end_pause: wait_for_abort(1)
			while kodi_utils.get_property(pause_services_prop) == 'true' or is_playing(): wait_for_abort(1)
			update_check(update_action())
			break
		kodi_utils.set_property(firstrun_update_prop, 'true')
		try: del monitor
		except: pass
		try: del player
		except: pass
		return kodi_utils.logger('The Pirate', 'UpdateCheck Service Finished')

class WidgetRefresher:
	def run(self):
		kodi_utils.logger('The Pirate', 'WidgetRefresher Service Starting')
		from time import time
		monitor, player = kodi_utils.kodi_monitor(), kodi_utils.kodi_player()
		wait_for_abort, self.is_playing = monitor.waitForAbort, player.isPlayingVideo
		wait_for_abort(10)
		self.set_next_refresh(time())
		while not monitor.abortRequested():
			try:
				wait_for_abort(10)
				offset = int(get_setting('fenlight.widget_refresh_timer', '60'))
				if offset != self.offset:
					self.set_next_refresh(time())
					continue
				if self.condition_check(): continue
				if self.next_refresh < time():
					kodi_utils.logger('The Pirate', 'WidgetRefresher Service - Widgets Refreshed')
					kodi_utils.refresh_widgets()
					self.set_next_refresh(time())
			except: pass
		try: del monitor
		except: pass
		try: del player
		except: pass
		return kodi_utils.logger('The Pirate', 'WidgetRefresher Service Finished')

	def condition_check(self):
		if not self.external(): return True

		if self.next_refresh == None or self.is_playing() or kodi_utils.get_property(pause_services_prop) == 'true': return True
		if kodi_utils.get_property('fenlight.window_loaded') == 'true': return True 
		try:
			window_stack = json.loads(kodi_utils.get_property('fenlight.window_stack'))
			if window_stack or window_stack == []: return True
		except: pass
		return False

	def set_next_refresh(self, _time):
		self.offset = int(get_setting('fenlight.widget_refresh_timer', '60'))
		if self.offset: self.next_refresh = _time + (self.offset*60)
		else: self.next_refresh = None

	def external(self):
		return 'plugin' not in kodi_utils.get_infolabel('Container.PluginName')

class TVGuidePreloader:
	def run(self):
		kodi_utils.logger('The Pirate', 'TVGuidePreloader Service Starting')
		monitor, player = kodi_utils.kodi_monitor(), kodi_utils.kodi_player()
		wait_for_abort = monitor.waitForAbort
		if wait_for_abort(5):
			return kodi_utils.logger('The Pirate', 'TVGuidePreloader Service Finished')
		try:
			from indexers.tv_guide import retire_guide_probe_misses
			retire_guide_probe_misses()
		except Exception as exc:
			kodi_utils.logger('TV Guide', 'cache migration deferred: %s' % exc)
		while not monitor.abortRequested():
			try:
				if kodi_utils.get_property(pause_services_prop) == 'true' or player.isPlayingVideo():
					wait_for_abort(15)
					continue
				kodi_utils.set_property('fenlight.tvguide_preload_running', 'true')
				try:
					from indexers.tv_guide import prewarm_snapshot, refresh_visible_guide
					ready = prewarm_snapshot(monitor, player)
				finally:
					kodi_utils.clear_property('fenlight.tvguide_preload_running')
				# Only refresh a Guide which actually rendered pending rows. Let
				# Kodi finish its first directory load before issuing the refresh.
				if kodi_utils.get_property('fenlight.tvguide_refresh_when_ready') == 'true':
					kodi_utils.clear_property('fenlight.tvguide_refresh_when_ready')
					for _ in range(30):
						if monitor.waitForAbort(0.1) or not kodi_utils.get_visibility('Window.IsActive(Videos)'):
							break
						if not kodi_utils.get_visibility('Container.IsUpdating'):
							refresh_visible_guide()
							break
				if ready:
					kodi_utils.logger('The Pirate', 'TV Guide startup snapshot is ready')
					break
				kodi_utils.logger('TV Guide Preload', 'startup snapshot incomplete; partial work is saved for retry')
			except Exception as e:
				kodi_utils.logger('TV Guide Preload', 'startup prewarm failed: %s' % str(e))
			if wait_for_abort(600):
				break
		try: del monitor
		except: pass
		try: del player
		except: pass
		return kodi_utils.logger('The Pirate', 'TVGuidePreloader Service Finished')


class TVGuideRefresher:
	"""Refresh an already-built guide cache quietly during active playback."""
	def run(self):
		kodi_utils.logger('The Pirate', 'TVGuideRefresher Service Starting')
		monitor, player = kodi_utils.kodi_monitor(), kodi_utils.kodi_player()
		wait_for_abort = monitor.waitForAbort
		playback_started, last_check = None, 0
		playback_file, end_refresh_attempted = None, False
		while not monitor.abortRequested():
			if wait_for_abort(30): break
			now = time()
			if kodi_utils.get_property(pause_services_prop) == 'true':
				playback_started = None
				playback_file, end_refresh_attempted = None, False
				continue
			try:
				is_playing = player.isPlayingVideo()
			except Exception:
				is_playing = False
			if not is_playing:
				playback_started = None
				playback_file, end_refresh_attempted = None, False
				continue
			if playback_started is None:
				playback_started = now
				continue
			# Let playback settle, then check at most once per minute. No guide cache
			# is created at startup: the first guide open still owns the progress UI.
			if now - playback_started < 60 or now - last_check < 60: continue
			last_check = now
			cache_key = kodi_utils.get_property('fenlight.tvguide_snapshot_key')
			if not cache_key: continue
			try:
				from indexers.tv_guide import (
					SNAPSHOT_PRE_END_REFRESH_SECONDS, playback_seconds_remaining,
					refresh_snapshot_for_key, should_refresh_before_end,
				)
				try: current_file = player.getPlayingFile()
				except Exception: current_file = None
				if current_file != playback_file:
					playback_file, end_refresh_attempted = current_file, False
				remaining = playback_seconds_remaining(player)
				if remaining is None or remaining > SNAPSHOT_PRE_END_REFRESH_SECONDS:
					end_refresh_attempted = False
				force_refresh = should_refresh_before_end(remaining, end_refresh_attempted)
				if force_refresh: end_refresh_attempted = True
				refresh_snapshot_for_key(cache_key, monitor, force=force_refresh)
			except Exception as e:
				kodi_utils.logger('TV Guide Refresh', 'Background refresh failed: %s' % str(e))
		try: del monitor
		except: pass
		try: del player
		except: pass
		return kodi_utils.logger('The Pirate', 'TVGuideRefresher Service Finished')

class AutoStart:
	def run(self):
		kodi_utils.logger('The Pirate', 'AutoStart Service Starting')
		from modules.settings import auto_start_fenlight
		if auto_start_fenlight(): kodi_utils.run_addon()
		return kodi_utils.logger('The Pirate', 'AutoStart Service Finished')

class AddonXMLCheck:
	def run(self):
		kodi_utils.logger('The Pirate', 'AddonXMLCheck Service Starting')
		from xml.dom.minidom import parse as mdParse
		self.addon_xml = kodi_utils.translate_path('special://home/addons/plugin.video.pirate/addon.xml')
		self.root = mdParse(self.addon_xml)
		self.change_list = []
		self.check_property('reuse_language_invoker', 'reuselanguageinvoker')
		self.check_property('addon_icon_choice', 'icon')
		self.change_xml_file()
		return kodi_utils.logger('The Pirate', 'AddonXMLCheck Service Finished')

	def check_property(self, setting, tag_name):
		current_addon_setting = get_setting('fenlight.%s' % setting, None)
		if current_addon_setting is None: return
		tag_instance = self.root.getElementsByTagName(tag_name)[0].firstChild
		current_property = tag_instance.data
		if current_property != current_addon_setting:
			tag_instance.data = current_addon_setting
			self.change_list.append(tag_name)

	def change_xml_file(self):
		if not self.change_list: return
		if 'icon' in self.change_list: self.reassign_addon_icon()
		kodi_utils.notification('Refreshing Addon XML. Restarting Addons')
		new_xml = str(self.root.toxml()).replace('<?xml version="1.0" ?>', '')
		with open(self.addon_xml, 'w') as f: f.write(new_xml)
		kodi_utils.logger('The Pirate', 'AddonXMLCheck Service - Change Detected. Restarting Addons')
		kodi_utils.execute_builtin('ActivateWindow(Home)', True)
		kodi_utils.update_local_addons()
		kodi_utils.disable_enable_addon()

	def reassign_addon_icon(self):
		from indexers.dialogs import addon_icon_choice
		addon_icon_choice({'set_icon': get_setting('addon_icon_choice_name', 'pirate_icon.png')})

class FenLightMonitor(Monitor):
	def __init__ (self):
		Monitor.__init__(self)
		self.startServices()

	def startServices(self):
		try: SetAddonConstants().run()
		except Exception as e: kodi_utils.logger('SetAddonConstants', str(e))
		try: DatabaseMaintenance().run()
		except Exception as e: kodi_utils.logger('DatabaseMaintenance', str(e))
		try: SyncSettings().run()
		except Exception as e: kodi_utils.logger('SyncSettings', str(e))
		try: OnUpdateChanges().run()
		except Exception as e: kodi_utils.logger('OnUpdateChanges', str(e))
		try: AddonXMLCheck().run()
		except Exception as e: kodi_utils.logger('AddonXMLCheck', str(e))
		Thread(target=CustomWindowsPrepare().run).start()
		Thread(target=TraktMonitor().run).start()
		Thread(target=UpdateCheck().run).start()
		Thread(target=WidgetRefresher().run).start()
		Thread(target=TVGuideRefresher().run).start()
		Thread(target=TVGuidePreloader().run).start()
		try: AutoStart().run()
		except Exception as e: kodi_utils.logger('AutoStart', str(e))

	def onNotification(self, sender, method, data):
		if sender == "plugin.video.pirate" and method.rsplit(".", 1)[-1] == "GuideTraceUnload":
			from indexers.tv_guide_trace import window_unloaded
			window_unloaded()
			return
		if method in ('GUI.OnScreensaverActivated', 'System.OnSleep'):
			kodi_utils.set_property(pause_services_prop, 'true')
			kodi_utils.logger('OnNotificationActions', 'PAUSING ThePirateStreaming Services Due to Device Sleep')
		elif method in ('GUI.OnScreensaverDeactivated', 'System.OnWake'):
			kodi_utils.clear_property(pause_services_prop)
			kodi_utils.logger('OnNotificationActions', 'UNPAUSING ThePirateStreaming Services Due to Device Awake')

kodi_utils.logger('The Pirate', 'Main Monitor Service Starting')
FenLightMonitor().waitForAbort()
kodi_utils.logger('The Pirate', 'Main Monitor Service Finished')
