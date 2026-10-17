# -*- coding: utf-8 -*-
"""Fake cable guide backed by The Pirate's existing catalog routes."""
import sys
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

from modules import kodi_utils


GENRE_CHANNELS = (
	{
		'id': 'comedy', 'number': '101', 'name': 'Comedy Channel', 'icon': 'genre_comedy',
		'description': 'A rotating lineup of comedy series and comedy movies.',
		'movie_genre': '35', 'tv_genre': '35',
		'slots': ('Comedy Series', 'Comedy Movies', 'Comedy Encore')
	},
	{
		'id': 'thriller', 'number': '102', 'name': 'Thriller Channel', 'icon': 'genre_thriller',
		'description': 'Suspenseful films and mystery-led series.',
		'movie_genre': '53', 'tv_genre': '9648',
		'slots': ('Mystery Series', 'Thriller Movies', 'Suspense Encore')
	},
	{
		'id': 'scifi', 'number': '103', 'name': 'Sci-Fi Channel', 'icon': 'genre_scifi',
		'description': 'Science-fiction and fantasy series, films, and reruns.',
		'movie_genre': '878', 'tv_genre': '10765',
		'slots': ('Sci-Fi Series', 'Sci-Fi Movies', 'Future Encore')
	},
	{
		'id': 'drama', 'number': '104', 'name': 'Drama Channel', 'icon': 'genre_drama',
		'description': 'Character-driven dramas from the TV and movie catalog.',
		'movie_genre': '18', 'tv_genre': '18',
		'slots': ('Drama Series', 'Drama Movies', 'Drama Encore')
	},
	{
		'id': 'action', 'number': '105', 'name': 'Action Channel', 'icon': 'genre_action',
		'description': 'Action-packed series and movies.',
		'movie_genre': '28', 'tv_genre': '10759',
		'slots': ('Action Series', 'Action Movies', 'Action Encore')
	},
	{
		'id': 'crime_mystery', 'number': '106', 'name': 'Crime & Mystery Channel', 'icon': 'genre_crime',
		'description': 'Crime stories, mysteries, investigations, and suspense.',
		'movie_genre': '80|9648', 'tv_genre': '80|9648',
		'slots': ('Crime & Mystery Series', 'Crime & Mystery Movies', 'Case Files Encore')
	},
	{
		'id': 'horror', 'number': '107', 'name': 'Horror Channel', 'icon': 'genre_horror',
		'description': 'Horror films and spooky series selected from TMDb horror keywords.',
		'movie_genre': '27', 'movie_keyword': 'horror', 'tv_keyword': 'horror',
		'slots': ('Horror Series', 'Horror Movies', 'Late Night Frights')
	},
	{
		'id': 'family_kids', 'number': '108', 'name': 'Family & Kids Channel', 'icon': 'genre_family',
		'description': 'Family films and kid-friendly series for all ages.',
		'movie_genre': '10751', 'tv_genre': '10751|10762',
		'slots': ('Kids Series', 'Family Movies', 'Family Favorites')
	},
	{
		'id': 'animation', 'number': '109', 'name': 'Animation Channel', 'icon': 'genre_animation',
		'description': 'Animated series and movies from across the catalog.',
		'movie_genre': '16', 'tv_genre': '16',
		'slots': ('Animated Series', 'Animated Movies', 'Animation Encore')
	},
	{
		'id': 'documentary_reality', 'number': '110', 'name': 'Documentary & Reality Channel', 'icon': 'genre_documentary',
		'description': 'Documentary films and reality series from the catalog.',
		'movie_genre': '99', 'tv_genre': '99|10764',
		'slots': ('Documentary Series', 'Documentary Movies', 'Reality Encore')
	},
)


def _holiday_channel(now=None):
	now = now or datetime.now()
	if now.month == 10:
		return {
			'id': 'holiday', 'number': '199', 'name': 'Halloween Channel', 'season': 'Halloween',
			'icon': 'horror',
			'movie_genre': '27',
			'movie_keyword': 'halloween', 'tv_keyword': 'horror',
			'description': 'Seasonal Halloween picks, with spooky shows and movies.',
			'slots': ('Halloween Series', 'Halloween Movies', 'Spooky Encore')
		}
	if now.month == 12:
		return {
			'id': 'holiday', 'number': '199', 'name': 'Christmas Channel', 'season': 'Christmas',
			'icon': 'genre_family',
			'movie_genre': '10751', 'tv_genre': '10765',
			'movie_keyword': 'christmas', 'tv_keyword': 'christmas',
			'description': 'Seasonal Christmas picks for cozy TV and movie nights.',
			'slots': ('Holiday Series', 'Christmas Movies', 'Holiday Encore')
		}
	return None


def _channels(now=None):
	channels = list(GENRE_CHANNELS)
	channels.append({
		'id': 'favorites', 'number': '111', 'name': 'Favorites Channel', 'icon': 'favorites',
		'description': 'Your saved shows and movies from Kodi Favorites and The Pirate Favorites.',
		'slots': ('Favorite Series', 'Favorite Movies', 'Your Favorites Encore')
	})
	holiday = _holiday_channel(now)
	if holiday: channels.append(holiday)
	return channels


def _format_time(value):
	return value.strftime('%I %p').lstrip('0')


def _rotate_programs_for_time(programs, start_time):
	"""Advance each channel's lineup by one program at each local hour."""
	if len(programs) < 2: return programs
	hour_number = start_time.toordinal() * 24 + start_time.hour
	rotation = hour_number % len(programs)
	return programs[rotation:] + programs[:rotation]


def _program_record(result, media_type, fallback_icon):
	if not isinstance(result, dict): return None
	title = result.get('name') or result.get('title')
	tmdb_id = result.get('id')
	if not title or not str(tmdb_id or '').isdigit(): return None
	poster_path = result.get('poster_path') or ''
	backdrop_path = result.get('backdrop_path') or ''
	return {
		'title': title,
		'plot': result.get('overview') or 'Program information is not available.',
		'thumb': 'https://image.tmdb.org/t/p/w342%s' % poster_path if poster_path else fallback_icon,
		'fanart': 'https://image.tmdb.org/t/p/w1280%s' % backdrop_path if backdrop_path else '',
		'media_type': media_type,
		'tmdb_id': str(tmdb_id),
	}


def _matches_channel_genre(result, genre_ids):
	if not genre_ids: return True
	expected = {item.strip() for item in str(genre_ids).split('|') if item.strip()}
	actual = {str(item) for item in result.get('genre_ids', [])}
	return bool(expected.intersection(actual))


def _favorite_tvshow_id(favourite):
	"""Return the TMDb ID when a Kodi favorite points at a Pirate TV series."""
	try:
		path = favourite.get('path', '')
		query = parse_qs(urlparse(path).query)
		tmdb_id = query.get('tmdb_id', [None])[0]
		mode = query.get('mode', [''])[0]
		media_type = query.get('media_type', [''])[0].lower()
		is_tvshow = media_type in ('tvshow', 'tv', 'episode', 'shows') or mode in ('build_season_list', 'build_episode_list')
		if is_tvshow and tmdb_id and str(tmdb_id).isdigit(): return str(tmdb_id)
	except Exception:
		pass
	return None


def _channel_programs(channel):
	"""Load real titles and artwork from the same cached TMDb genre feeds as the catalog."""
	icon = kodi_utils.get_icon(channel['icon'])
	if channel['id'] == 'favorites':
		show_programs, other_programs = [], []
		for favourite in _get_kodi_favourites():
			if not isinstance(favourite, dict): continue
			if favourite.get('type') != 'media': continue
			title = favourite.get('title')
			if not title: continue
			tmdb_id = _favorite_tvshow_id(favourite)
			program = {
				'title': title,
				'plot': 'Saved in your Kodi Favorites.',
				'thumb': favourite.get('thumbnail') or icon,
				'fanart': '',
				'media_type': 'tvshow' if tmdb_id else 'video',
				'tmdb_id': tmdb_id,
			}
			(show_programs if tmdb_id else other_programs).append(program)
		# Keep an episode-playable show in the active slot. Movie and other
		# favorites can still appear in the later guide slots.
		programs = show_programs[:1] + other_programs[:2]
		if programs: return programs

	try:
		from modules.settings import tmdb_api_key
		if tmdb_api_key() in (None, '', 'empty_setting'): return []
		from apis import tmdb_api
		show_data = tmdb_api.tmdb_tv_keyword_results_direct(channel['tv_keyword'], 1) if channel.get('tv_keyword') else None
		movie_data = tmdb_api.tmdb_movie_keyword_results_direct(channel['movie_keyword'], 1) if channel.get('movie_keyword') else None
		# Seasonal channels must stay seasonal; do not pad an empty holiday
		# keyword feed with unrelated titles from a broad genre feed.
		seasonal = bool(channel.get('season'))
		genre_show_data = tmdb_api.tmdb_tv_genres(channel.get('tv_genre'), 1) if channel.get('tv_genre') and not seasonal else None
		genre_movie_data = tmdb_api.tmdb_movies_genres(channel.get('movie_genre'), 1) if channel.get('movie_genre') and not seasonal else None
		shows, movies = [], []
		seen = set()
		def append_programs(data, media_type, genre_ids=None, require_genre=False):
			for result in (data or {}).get('results', []):
				if not isinstance(result, dict): continue
				if require_genre and not _matches_channel_genre(result, genre_ids): continue
				program = _program_record(result, media_type, icon)
				if not program: continue
				key = (media_type, program['tmdb_id'])
				if key in seen: continue
				seen.add(key)
				(shows if media_type == 'tvshow' else movies).append(program)
		append_programs(show_data, 'tvshow')
		append_programs(genre_show_data, 'tvshow', channel.get('tv_genre'), True)
		append_programs(movie_data, 'movie')
		append_programs(genre_movie_data, 'movie', channel.get('movie_genre'), True)
		programs = []
		for index in range(max(len(shows), len(movies))):
			if index < len(shows): programs.append(shows[index])
			if index < len(movies): programs.append(movies[index])
		if programs: return programs[:6]
	except Exception:
		pass
	return []


def _source_check_cache_key(program):
	from modules import settings
	media_type = 'episode' if program.get('media_type') == 'tvshow' else 'movie'
	providers = '-'.join(settings.active_internal_scrapers())
	autoplay = media_type == 'episode' or settings.auto_play('movie')
	quality_type = 'autoplay' if autoplay else 'results'
	quality = ','.join(settings.quality_filter('%s_quality_%s' % (quality_type, media_type)))
	return 'tvguide_source_v1_%s_%s_%s_%s' % (media_type, program['tmdb_id'], providers, quality)


def _check_program_source(program, channel, progress_state):
	"""Check and cache a playable source; for series, cache the exact episode tested."""
	if program.get('media_type') not in ('tvshow', 'movie') or not str(program.get('tmdb_id', '')).isdigit():
		return False
	try:
		progress_state['checked'] = progress_state.get('checked', 0) + 1
		def update_progress():
			progress = progress_state.get('dialog')
			if not progress: return
			percent = min(99, int(100.0 * progress_state['checked'] / max(progress_state.get('total', 1), 1)))
			try: progress.update(percent, 'Preparing TV Guide', '%s: %s' % (channel['name'], program['title']))
			except Exception: pass
		from caches.main_cache import main_cache
		from modules import settings
		cache_key = _source_check_cache_key(program)
		cached = main_cache.get(cache_key)
		if isinstance(cached, dict) and 'available' in cached:
			if cached.get('available'):
				program['_guide_season'] = cached.get('season')
				program['_guide_episode'] = cached.get('episode')
			update_progress()
			return bool(cached.get('available'))
		progress_state['probed'] = progress_state.get('probed', 0) + 1
		if progress_state.get('dialog') is None:
			try:
				progress_state['dialog'] = kodi_utils.kodi_progress_background()
				progress_state['dialog'].create('Preparing TV Guide', 'Checking which programs have playable sources...')
			except Exception:
				progress_state['dialog'] = None
		update_progress()
		tmdb_id = str(program['tmdb_id'])
		from modules import metadata
		from modules.utils import get_datetime
		season = episode = None
		if program['media_type'] == 'movie':
			meta = metadata.movie_meta('tmdb_id', tmdb_id, settings.tmdb_api_key(), settings.mpaa_region(), get_datetime())
			params = {'media_type': 'movie', 'tmdb_id': tmdb_id}
			playback_key = settings.playback_key()
			params[playback_key] = playback_key
		else:
			meta = metadata.tvshow_meta('tmdb_id', tmdb_id, settings.tmdb_api_key(), settings.mpaa_region(), get_datetime())
			if not meta or meta.get('blank_entry'):
				return False
			from modules.episode_tools import EpisodeTools
			episode_params = EpisodeTools(meta).get_random_episode()
			if not isinstance(episode_params, dict):
				return False
			season, episode = episode_params.get('season'), episode_params.get('episode')
			if not str(season or '').isdigit() or not str(episode or '').isdigit():
				return False
			params = dict(episode_params)
			params.update({'media_type': 'episode', 'tmdb_id': tmdb_id, 'autoplay': 'true'})
		if not meta or meta.get('blank_entry'):
			return False
		params.update({'background': 'true', 'check_sources_only': 'true'})
		from modules.sources import Sources
		available = bool(Sources().playback_prep(params))
		result = {'available': available}
		if available and season is not None and episode is not None:
			result.update({'season': int(season), 'episode': int(episode)})
			program['_guide_season'], program['_guide_episode'] = int(season), int(episode)
		# Positive checks stay warm through the next few guide hours. Negative
		# checks expire sooner so a new source can appear without waiting long.
		main_cache.set(cache_key, result, expiration=6 if available else 1)
		return available
	except Exception:
		return False


def _channel_item(handle, channel, start_time, fanart, progress_state):
	candidates = _channel_programs(channel)
	if not candidates: return
	programs, probes_before = [], progress_state.get('probed', 0)
	for program in candidates:
		if _check_program_source(program, channel, progress_state):
			programs.append(program)
		if len(programs) >= 3 or progress_state.get('probed', 0) - probes_before >= 4: break
	if not programs: return
	item = kodi_utils.make_listitem()
	icon = kodi_utils.get_icon(channel['icon'])
	programs = _rotate_programs_for_time(programs, start_time)
	current_program = programs[0]
	# Keep channel labels separate from the show's title in VideoInfoTag. Kodi
	# exposes the title as ListItem.Label on some builds, so the skin uses the
	# explicit channel properties below for the guide columns.
	item.setLabel(channel['name'])
	item.setLabel2(channel['number'])
	item.setArt({
		'icon': icon,
		'thumb': current_program['thumb'],
		'poster': current_program['thumb'],
		'fanart': current_program['fanart'] or fanart,
		'banner': icon,
	})
	info = item.getVideoInfoTag(True)
	info.setTitle(current_program['title'])
	info.setPlot(current_program['plot'])
	info.setMediaType(current_program['media_type'])
	if current_program.get('media_type') == 'tvshow' and current_program.get('tmdb_id'):
		try:
			from modules import metadata, settings
			from modules.utils import get_datetime
			if settings.tmdb_api_key():
				program_meta = metadata.tvshow_meta('tmdb_id', current_program['tmdb_id'], settings.tmdb_api_key(), settings.mpaa_region(), get_datetime())
				if program_meta and program_meta.get('mpaa'):
					info.setMpaa(program_meta['mpaa'])
		except Exception:
			pass
	item.setProperty('channel_number', channel['number'])
	item.setProperty('channel_id', channel['id'])
	item.setProperty('channel_name', channel['name'])
	item.setProperty('channel_description', channel['description'])
	item.setProperty('now_title', current_program['title'])
	item.setProperty('now_plot', current_program['plot'])
	for index, program in enumerate(programs[:3], 1):
		slot_start = start_time + timedelta(hours=index - 1)
		slot_end = slot_start + timedelta(hours=1)
		item.setProperty('slot_%s' % index, '%s–%s   %s' % (_format_time(slot_start), _format_time(slot_end), program['title']))
		item.setProperty('program_%s_title' % index, program['title'])
		item.setProperty('program_%s_plot' % index, program['plot'])
		item.setProperty('program_%s_thumb' % index, program['thumb'])
	# Keep a TMDb ID on playable show and movie entries. Show entries start a
	# random aired episode; movie entries start that film.
	tmdb_id = current_program.get('tmdb_id')
	if tmdb_id and current_program.get('media_type') in ('tvshow', 'movie'):
		item.setProperty('IsPlayable', 'true')
		item.setProperty('tmdb_id', str(tmdb_id))
		info.setUniqueIDs({'tmdb': str(tmdb_id)})
	url_params = {'mode': 'tvguide.play_channel', 'channel': channel['id'], 'tmdb_id': tmdb_id or '',
				  'media_type': current_program.get('media_type', '')}
	if current_program.get('media_type') == 'tvshow':
		url_params.update({'season': current_program.get('_guide_season', ''), 'episode': current_program.get('_guide_episode', '')})
	url = kodi_utils.build_url(url_params)
	kodi_utils.add_item(handle, url, item, False)


def main(params=None):
	handle = int(sys.argv[1])
	start_time = datetime.now().replace(minute=0, second=0, microsecond=0)
	channels = _channels()
	fanart = kodi_utils.get_addon_fanart()
	# A previously-selected sort mode can otherwise reorder the schedule using
	# the program titles. The guide is a fixed numbered channel lineup.
	kodi_utils.set_sort_method(handle, 'none')
	progress_state = {'dialog': None, 'checked': 0, 'probed': 0, 'total': max(len(channels) * 4, 1)}
	try:
		for channel in channels:
			try: _channel_item(handle, channel, start_time, fanart, progress_state)
			except Exception: continue
		kodi_utils.set_content(handle, 'files')
		kodi_utils.set_category(handle, 'TV Guide')
		kodi_utils.end_directory(handle, cacheToDisc=False)
	finally:
		progress = progress_state.get('dialog')
		if progress:
			try:
				progress.update(100, 'TV Guide ready', 'Playable channel lineups are cached.')
				progress.close()
			except Exception: pass
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
	target = 'mode=%s' % mode
	ready_checks = 0
	for unused in range(80):
		if target in kodi_utils.folder_path() and kodi_utils.get_visibility('Window.IsActive(Videos)'):
			try:
				item_count = int(kodi_utils.get_infolabel('Container.NumItems') or '0')
			except (TypeError, ValueError):
				item_count = 0
			if item_count > 0:
				ready_checks += 1
				if ready_checks >= 2:
					# Let Kodi finish attaching the plugin directory to the video
					# window before applying its custom view on a first visit.
					kodi_utils.sleep(150)
					if target not in kodi_utils.folder_path(): return
					kodi_utils.execute_builtin('Container.SetViewMode(%s)' % view_id)
					kodi_utils.sleep(300)
					# On the initial plugin launch Kodi can process the view action
					# before the skin has registered the requested view; retry once.
					if target in kodi_utils.folder_path() and not kodi_utils.get_visibility('Control.IsVisible(%s)' % view_id):
						kodi_utils.execute_builtin('Container.SetViewMode(%s)' % view_id)
					return
			else:
				ready_checks = 0
		else:
			ready_checks = 0
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


def play_channel(params):
	"""Play the current program: a random aired episode for shows, or the movie."""
	tmdb_id = params.get('tmdb_id', '')
	media_type = params.get('media_type', 'tvshow')
	if not str(tmdb_id).isdigit():
		return kodi_utils.notification('No playable program is available in this channel.', 4000)
	try:
		from modules import metadata, settings
		from modules.utils import get_datetime
		if media_type == 'movie':
			meta = metadata.movie_meta('tmdb_id', tmdb_id, settings.tmdb_api_key(), settings.mpaa_region(), get_datetime())
			if not meta or meta.get('blank_entry'):
				return kodi_utils.notification('Could not load the selected movie.', 4000)
			from modules.sources import Sources
			playback_key = settings.playback_key()
			return Sources().playback_prep({'media_type': 'movie', 'tmdb_id': str(tmdb_id), playback_key: playback_key})
		from modules.episode_tools import EpisodeTools
		meta = metadata.tvshow_meta('tmdb_id', tmdb_id, settings.tmdb_api_key(), settings.mpaa_region(), get_datetime())
		if not meta or meta.get('blank_entry'):
			return kodi_utils.notification('Could not load the selected series.', 4000)
		season, episode = params.get('season'), params.get('episode')
		if str(season or '').isdigit() and str(episode or '').isdigit():
			from modules.sources import Sources
			playback_key = settings.playback_key()
			return Sources().playback_prep({'media_type': 'episode', 'tmdb_id': str(tmdb_id), 'season': int(season),
											'episode': int(episode), 'autoplay': 'true', playback_key: playback_key})
		return EpisodeTools(meta).play_random()
	except Exception:
		message = 'Could not play the selected movie.' if media_type == 'movie' else 'Could not play a random episode from this series.'
		return kodi_utils.notification(message, 4000)


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
	if not isinstance(favourite, dict): return
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
		result = kodi_utils.get_jsonrpc(request)
		if not isinstance(result, dict): return []
		favourites = result.get('favourites')
		return favourites if isinstance(favourites, list) else []
	except Exception:
		return []

