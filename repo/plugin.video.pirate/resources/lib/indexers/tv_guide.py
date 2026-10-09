# -*- coding: utf-8 -*-
"""Fake cable guide backed by The Pirate's existing catalog routes."""
import sys
from datetime import datetime, timedelta

from modules import kodi_utils


GENRE_CHANNELS = (
	{
		'id': 'comedy', 'number': '101', 'name': 'Comedy', 'icon': 'genre_comedy',
		'description': 'A rotating lineup of comedy series and comedy movies.',
		'movie_genre': '35', 'tv_genre': '35',
		'slots': ('Comedy Series', 'Comedy Movies', 'Comedy Encore')
	},
	{
		'id': 'thriller', 'number': '102', 'name': 'Thriller', 'icon': 'genre_thriller',
		'description': 'Suspenseful films and mystery-led series.',
		'movie_genre': '53', 'tv_genre': '9648',
		'slots': ('Mystery Series', 'Thriller Movies', 'Suspense Encore')
	},
	{
		'id': 'scifi', 'number': '103', 'name': 'Sci-Fi', 'icon': 'genre_scifi',
		'description': 'Science-fiction and fantasy series, films, and reruns.',
		'movie_genre': '878', 'tv_genre': '10765',
		'slots': ('Sci-Fi Series', 'Sci-Fi Movies', 'Future Encore')
	},
	{
		'id': 'drama', 'number': '104', 'name': 'Drama', 'icon': 'genre_drama',
		'description': 'Character-driven dramas from the TV and movie catalog.',
		'movie_genre': '18', 'tv_genre': '18',
		'slots': ('Drama Series', 'Drama Movies', 'Drama Encore')
	},
	{
		'id': 'action', 'number': '105', 'name': 'Action', 'icon': 'genre_action',
		'description': 'Action-packed series and movies.',
		'movie_genre': '28', 'tv_genre': '10759',
		'slots': ('Action Series', 'Action Movies', 'Action Encore')
	},
)


def _holiday_channel(now=None):
	now = now or datetime.now()
	if now.month == 10:
		return {
			'id': 'holiday', 'number': '199', 'name': 'Halloween Channel', 'season': 'Halloween',
			'icon': 'horror',
			'description': 'Seasonal Halloween picks, with spooky shows and movies.',
			'slots': ('Halloween Series', 'Halloween Movies', 'Spooky Encore')
		}
	if now.month == 12:
		return {
			'id': 'holiday', 'number': '199', 'name': 'Christmas Channel', 'season': 'Christmas',
			'icon': 'genre_family',
			'description': 'Seasonal Christmas picks for cozy TV and movie nights.',
			'slots': ('Holiday Series', 'Christmas Movies', 'Holiday Encore')
		}
	return None


def _channels(now=None):
	channels = list(GENRE_CHANNELS)
	channels.append({
		'id': 'favorites', 'number': '106', 'name': 'Favorites', 'icon': 'favorites',
		'description': 'Your saved shows and movies from Kodi Favorites and The Pirate Favorites.',
		'slots': ('Favorite Series', 'Favorite Movies', 'Your Favorites Encore')
	})
	holiday = _holiday_channel(now)
	if holiday: channels.append(holiday)
	return channels


def _format_time(value):
	return value.strftime('%I %p').lstrip('0')


def _channel_item(handle, channel, start_time, fanart):
	item = kodi_utils.make_listitem()
	item.setLabel('%s  |  %s' % (channel['number'], channel['name']))
	item.setLabel2('NOW  %s–%s' % (_format_time(start_time), _format_time(start_time + timedelta(hours=1))))
	icon = kodi_utils.get_icon(channel['icon'])
	item.setArt({'icon': icon, 'thumb': icon, 'poster': icon, 'fanart': fanart, 'banner': icon})
	item.setProperty('channel_number', channel['number'])
	item.setProperty('channel_name', channel['name'])
	for index, slot in enumerate(channel['slots'], 1):
		slot_start = start_time + timedelta(hours=index - 1)
		slot_end = slot_start + timedelta(hours=1)
		item.setProperty('slot_%s' % index, '%s–%s   %s' % (_format_time(slot_start), _format_time(slot_end), slot))
	info = item.getVideoInfoTag(True)
	info.setTitle(channel['name'])
	info.setPlot(channel['description'])
	info.setMediaType('video')
	url = kodi_utils.build_url({'mode': 'tvguide.channel', 'channel': channel['id']})
	kodi_utils.add_item(handle, url, item, True)


def main(params=None):
	handle = int(sys.argv[1])
	start_time = datetime.now().replace(minute=0, second=0, microsecond=0)
	channels = _channels()
	fanart = kodi_utils.get_addon_fanart()
	for channel in channels:
		_channel_item(handle, channel, start_time, fanart)
	kodi_utils.set_content(handle, 'files')
	kodi_utils.set_category(handle, 'TV Guide')
	kodi_utils.end_directory(handle, cacheToDisc=False)
	if kodi_utils.current_skin() == 'skin.pirate':
		from threading import Thread
		Thread(target=_set_guide_view, daemon=True).start()


def _set_guide_view():
	# Wait until Kodi has opened this plugin folder, then select the guide layout.
	return _set_view_for_mode('tvguide.main', 58)


def _set_catalog_view():
	# The channel's genre/favorites choices use the skin's regular detail list.
	return _set_view_for_mode('tvguide.channel', 51)


def _set_view_for_mode(mode, view_id):
	for unused in range(60):
		if 'mode=%s' % mode in kodi_utils.folder_path():
			return kodi_utils.execute_builtin('Container.SetViewMode(%s)' % view_id)
		kodi_utils.sleep(100)


def channel(params):
	handle = int(sys.argv[1])
	channel_id = params.get('channel', '')
	channel = next((i for i in _channels() if i['id'] == channel_id), None)
	if not channel:
		return kodi_utils.end_directory(handle, cacheToDisc=False)
	entries = _channel_entries(channel)
	for title, url_params, icon in entries:
		item = kodi_utils.make_listitem()
		item.setLabel(title)
		item.setArt({'icon': kodi_utils.get_icon(icon), 'thumb': kodi_utils.get_icon(icon), 'fanart': kodi_utils.get_addon_fanart()})
		info = item.getVideoInfoTag(True)
		info.setTitle(title)
		info.setPlot('Browse %s from The Pirate catalog.' % title)
		info.setMediaType('video')
		kodi_utils.add_item(handle, kodi_utils.build_url(url_params), item, True)
	kodi_utils.set_content(handle, 'files')
	channel_name = channel['name'].replace(' Channel', '')
	kodi_utils.set_category(handle, '%s Channel' % channel_name)
	kodi_utils.end_directory(handle, cacheToDisc=False)
	if kodi_utils.current_skin() == 'skin.pirate':
		from threading import Thread
		Thread(target=_set_catalog_view, daemon=True).start()


def _channel_entries(channel):
	channel_id = channel['id']
	if channel_id == 'favorites':
		return [
			('The Pirate • TV Favorites', {'mode': 'build_tvshow_list', 'action': 'favorites_tvshows', 'name': 'TV Favorites'}, 'favorites'),
			('The Pirate • Movie Favorites', {'mode': 'build_movie_list', 'action': 'favorites_movies', 'name': 'Movie Favorites'}, 'favorites'),
			('Kodi Favorites', {'mode': 'tvguide.kodi_favorites', 'name': 'Kodi Favorites'}, 'favorites'),
		]
	if 'season' in channel:
		season = channel['season']
		return [
			('%s TV Shows' % season, {'mode': 'build_tvshow_list', 'action': 'tmdb_tv_keyword_results_direct', 'key_id': season, 'name': '%s TV Shows' % season}, channel['icon']),
			('%s Movies' % season, {'mode': 'build_movie_list', 'action': 'tmdb_movie_keyword_results_direct', 'key_id': season, 'name': '%s Movies' % season}, channel['icon']),
		]
	return [
		('%s TV Shows' % channel['name'], {'mode': 'build_tvshow_list', 'action': 'tmdb_tv_genres', 'key_id': channel['tv_genre'], 'name': '%s TV Shows' % channel['name']}, channel['icon']),
		('%s Movies' % channel['name'], {'mode': 'build_movie_list', 'action': 'tmdb_movies_genres', 'key_id': channel['movie_genre'], 'name': '%s Movies' % channel['name']}, channel['icon']),
	]


def kodi_favorites(params):
	handle = int(sys.argv[1])
	favourites = _get_kodi_favourites()
	for index, favourite in enumerate(favourites):
		if favourite.get('type') not in ('media', 'window'):
			continue
		title = favourite.get('title') or 'Kodi Favorite %s' % (index + 1)
		if favourite.get('type') == 'media' and not favourite.get('path'):
			continue
		if favourite.get('type') == 'window' and not favourite.get('window'):
			continue
		item = kodi_utils.make_listitem()
		item.setLabel(title)
		item.setArt({'icon': favourite.get('thumbnail') or kodi_utils.get_icon('favorites'), 'thumb': favourite.get('thumbnail') or kodi_utils.get_icon('favorites')})
		info = item.getVideoInfoTag(True)
		info.setTitle(title)
		info.setPlot('Open this item from your Kodi Favorites.')
		info.setMediaType('video')
		url = kodi_utils.build_url({'mode': 'tvguide.play_favorite', 'index': index})
		kodi_utils.add_item(handle, url, item, False)
	kodi_utils.set_content(handle, 'files')
	kodi_utils.set_category(handle, params.get('name') or 'Kodi Favorites')
	kodi_utils.end_directory(handle, cacheToDisc=False)


def play_favorite(params):
	try:
		index = int(params.get('index', '-1'))
		if index < 0: return
		favourite = _get_kodi_favourites()[index]
	except (IndexError, TypeError, ValueError):
		return
	if favourite.get('type') == 'window' and favourite.get('window'):
		window = favourite['window'].replace(')', '').replace(',', '')
		parameter = favourite.get('windowparameter', '').replace('"', '\\"')
		return kodi_utils.execute_builtin('ActivateWindow(%s,"%s",return)' % (window, parameter))
	if favourite.get('type') == 'media' and favourite.get('path'):
		# Some Kodi builds store an action, while others expose the direct media path.
		path = favourite['path']
		if path.lstrip().lower().startswith(('playmedia(', 'activatewindow(', 'runplugin(', 'runscript(', 'runaddon(')):
			action = path
		else:
			action = 'PlayMedia("%s")' % path.replace('"', '\\"')
		return kodi_utils.execute_builtin(action)


def _get_kodi_favourites():
	request = {
		'jsonrpc': '2.0', 'id': 1, 'method': 'Favourites.GetFavourites',
		'params': {'properties': ['path', 'thumbnail', 'window', 'windowparameter']}
	}
	try:
		return (kodi_utils.get_jsonrpc(request) or {}).get('favourites', [])
	except Exception:
		return []

