# -*- coding: utf-8 -*-
"""Fake cable guide backed by The Pirate's existing catalog routes."""
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timedelta
from time import perf_counter, time
from urllib.parse import parse_qs, quote_plus, urlparse

from modules import kodi_utils


SNAPSHOT_SCHEMA = 5
SNAPSHOT_CACHE_HOURS = 6
SNAPSHOT_INITIAL_REFRESH_DELAY = 5 * 60
SNAPSHOT_REFRESH_INTERVAL = 45 * 60
SNAPSHOT_RETRY_DELAY = 10 * 60
SNAPSHOT_PRE_END_REFRESH_SECONDS = 5 * 60
SOURCE_NEGATIVE_CACHE_HOURS = SNAPSHOT_RETRY_DELAY / 3600.0
MAX_GUIDE_SOURCE_PROBES_PER_CHANNEL = 6
MAX_REFRESH_SOURCE_PROBES_PER_CHANNEL = 4
SNAPSHOT_KEY_PROPERTY = 'fenlight.tvguide_snapshot_key'
GUIDE_DAYS_BACK = 30
GUIDE_DAYS_AHEAD = 45


# Invalid configuration fails closed so it cannot invent off-brand genre channels.
_FALLBACK_SEASONAL_CHANNELS = {
	'10': {
		'id': 'holiday', 'number': '199', 'name': 'Halloween Channel', 'season': 'Halloween',
		'icon': 'genre_horror', 'movie_keyword': 'halloween', 'tv_keyword': 'horror',
		'description': 'Seasonal Halloween picks with playable spooky shows and movies.',
		'slots': ('Halloween Shows', 'Halloween Movies', 'Spooky Encore')
	},
	'12': {
		'id': 'holiday', 'number': '199', 'name': 'Christmas Channel', 'season': 'Christmas',
		'icon': 'genre_family', 'movie_keyword': 'christmas', 'tv_keyword': 'christmas',
		'description': 'Seasonal Christmas picks with playable holiday shows and movies.',
		'slots': ('Christmas Shows', 'Christmas Movies', 'Holiday Encore')
	}
}
_DEFAULT_CHANNEL_CONFIG = {
	'network_channels': (),
	'seasonal_channels': _FALLBACK_SEASONAL_CHANNELS,
}


def _normalize_channel_definition(channel):
	if not isinstance(channel, dict):
		raise ValueError('each channel must be an object')
	if any(not channel.get(field) for field in ('id', 'number', 'name', 'icon', 'description')):
		raise ValueError('channel identity and display fields are required')
	loaded = dict(channel)
	loaded['id'], loaded['number'] = str(loaded['id']), str(loaded['number'])
	if not loaded['number'].isdigit():
		raise ValueError('channel numbers must be numeric')
	slots = loaded.get('slots')
	if not isinstance(slots, list) or not slots or not all(isinstance(slot, str) and slot for slot in slots):
		raise ValueError('each channel needs one or more named slots')
	loaded['slots'] = tuple(slots)
	return loaded

def _dedupe_channels(channels, source='lineup'):
	"""Keep the first channel for each ID, number, and case-insensitive name."""
	unique = []
	seen_ids, seen_numbers, seen_names = set(), set(), set()
	for channel in channels:
		channel_id = str(channel.get('id', '')).strip().casefold()
		number = str(channel.get('number', '')).strip().casefold()
		name = ' '.join(str(channel.get('name', '')).casefold().split())
		if channel_id in seen_ids or number in seen_numbers or name in seen_names:
			kodi_utils.logger(
				'TV Guide skipped duplicate %s channel: %s (%s)' %
				(source, channel.get('name', 'Unknown'), channel.get('number', '?'))
			)
			continue
		seen_ids.add(channel_id)
		seen_numbers.add(number)
		seen_names.add(name)
		unique.append(channel)
	return tuple(unique)




def _channel_logo(channel):
	"""Generate an original badge with colors and geometry keyed to each parody network."""
	fallback = kodi_utils.get_icon(channel.get('icon', 'folder'))
	custom_path = channel.get('logo_path')
	if custom_path:
		try:
			if custom_path.lower().startswith('special://') or os.path.isabs(custom_path):
				resolved_path = kodi_utils.translate_path(custom_path)
			else:
				resolved_path = kodi_utils.translate_path(
					os.path.join(kodi_utils.addon_path(), custom_path)
				)
		except Exception:
			resolved_path = custom_path
		if os.path.isfile(resolved_path):
			return resolved_path
	try:
		from PIL import Image, ImageDraw, ImageFont
		profile_path = kodi_utils.addon_profile()
		if not profile_path:
			return fallback
		channel_id = str(channel.get('id') or 'channel')
		slug = ''.join(character.lower() for character in channel_id if character.isalnum() or character in ('-', '_'))
		if not slug:
			return fallback
		# Supplied logos override generated artwork; seasonal styles use separate files.
		logo_style = str(channel.get('logo_style') or '')
		style_slug = ''.join(character.lower() for character in logo_style if character.isalnum() or character in ('-', '_'))
		logo_dir = os.path.join(kodi_utils.addon_path(), 'resources', 'media', 'tv_guide', 'channels')
		for logo_name in (style_slug, slug):
			if logo_name:
				user_logo = os.path.join(logo_dir, '%s.png' % logo_name)
				if os.path.isfile(user_logo):
					return user_logo
		cache_dir = os.path.join(profile_path, 'tv_guide', 'channel_logos_v2')
		if not os.path.isdir(cache_dir):
			os.makedirs(cache_dir)
		logo_path = os.path.join(cache_dir, '%s.png' % slug)
		if os.path.isfile(logo_path):
			return logo_path

		# Colors and silhouettes nod to each counterpart while using the parody
		# wordmarks and fresh artwork instead of copied network logo files.
		styles = {
			'diznoy': ((10, 63, 156), (20, 116, 201), (43, 191, 238), (255, 218, 99), (255, 255, 255), 'orb'),
			'diznoy_exb': ((12, 20, 67), (29, 47, 125), (0, 157, 239), (134, 229, 255), (255, 255, 255), 'bolt'),
			'diznoy_jr': ((0, 141, 207), (5, 186, 219), (248, 191, 42), (255, 255, 255), (255, 255, 255), 'bubbles'),
			'toon_diznoy': ((29, 51, 113), (45, 78, 147), (255, 196, 67), (255, 238, 178), (255, 255, 255), 'retro'),
			'nickelodium': ((211, 63, 13), (244, 111, 20), (255, 136, 22), (255, 238, 111), (255, 255, 255), 'splat'),
			'nicktoonz': ((214, 77, 12), (245, 128, 25), (255, 147, 31), (76, 191, 239), (255, 255, 255), 'splat'),
			'cartoon_signal': ((17, 17, 20), (29, 29, 34), (246, 246, 246), (15, 15, 18), (255, 255, 255), 'checker'),
			'doomerwang': ((15, 61, 104), (31, 106, 151), (255, 179, 63), (255, 238, 188), (255, 255, 255), 'oval'),
			'adult_svim': ((9, 9, 10), (34, 34, 37), (255, 255, 255), (87, 230, 164), (255, 255, 255), 'split'),
			'tlc': ((194, 0, 94), (244, 24, 131), (255, 65, 157), (255, 233, 242), (255, 255, 255), 'blocks'),
			'usa': ((20, 39, 77), (117, 25, 43), (215, 50, 61), (255, 255, 255), (255, 255, 255), 'stripes'),
			'truetv': ((23, 21, 13), (56, 49, 13), (232, 191, 0), (255, 239, 151), (255, 255, 255), 'bold'),
			'history': ((101, 15, 23), (169, 28, 39), (232, 192, 124), (255, 244, 220), (255, 255, 255), 'bold'),
			'animal_planet': ((0, 58, 111), (16, 101, 151), (63, 177, 117), (172, 224, 186), (255, 255, 255), 'planet'),
			'ae': ((12, 43, 93), (31, 75, 139), (201, 35, 54), (255, 255, 255), (255, 255, 255), 'stripes'),
			'hbo': ((9, 9, 11), (37, 37, 40), (255, 255, 255), (225, 186, 104), (255, 255, 255), 'orb'),
			'comedy_central': ((11, 33, 38), (16, 79, 83), (0, 171, 176), (255, 225, 100), (255, 255, 255), 'circle'),
			'tnt': ((15, 15, 16), (49, 49, 50), (242, 204, 59), (255, 244, 181), (255, 255, 255), 'circle'),
			'syfy': ((13, 22, 75), (25, 44, 133), (22, 166, 218), (149, 225, 247), (255, 255, 255), 'orb'),
			'abc_family': ((40, 22, 91), (87, 44, 131), (227, 89, 177), (255, 199, 236), (255, 255, 255), 'bubbles'),
			'mtv': ((20, 20, 22), (55, 37, 60), (240, 49, 150), (255, 255, 255), (255, 255, 255), 'bold'),
			'lifetime': ((70, 28, 88), (131, 54, 110), (222, 176, 75), (255, 234, 175), (255, 255, 255), 'orb'),
			'amc': ((120, 15, 22), (195, 30, 36), (255, 255, 255), (255, 229, 219), (255, 255, 255), 'bold'),
			'bet': ((13, 13, 15), (45, 45, 48), (213, 177, 92), (255, 231, 166), (255, 255, 255), 'orb'),
			'bravo': ((112, 15, 24), (189, 30, 42), (255, 255, 255), (255, 222, 225), (255, 255, 255), 'bold'),
			'food_network': ((0, 61, 102), (5, 112, 160), (242, 101, 38), (255, 213, 165), (255, 255, 255), 'circle'),
			'showtime': ((12, 12, 16), (63, 16, 27), (196, 23, 44), (255, 255, 255), (255, 255, 255), 'orb'),
			'natgeo': ((15, 31, 50), (16, 53, 81), (248, 194, 62), (255, 240, 176), (255, 255, 255), 'frame'),
			'discovery': ((3, 54, 116), (15, 105, 165), (242, 111, 43), (255, 216, 171), (255, 255, 255), 'planet'),
			'fox_movie': ((15, 40, 96), (29, 87, 145), (210, 43, 53), (255, 255, 255), (255, 255, 255), 'frame'),
			'starz': ((11, 11, 16), (43, 30, 73), (198, 171, 90), (241, 224, 165), (255, 255, 255), 'orb'),
			'halloween': ((38, 16, 18), (117, 37, 19), (255, 104, 20), (255, 209, 114), (255, 255, 255), 'splat'),
			'christmas': ((14, 61, 48), (25, 106, 67), (192, 37, 47), (246, 223, 132), (255, 255, 255), 'ornament'),
		}
		style = channel.get('logo_style') or channel_id
		top_color, bottom_color, accent, highlight, foreground, motif = styles.get(
			style, ((17, 34, 58), (20, 77, 109), (255, 122, 35), (188, 235, 116), (255, 255, 255), 'orb')
		)
		image = Image.new('RGB', (128, 112), top_color)
		draw = ImageDraw.Draw(image)
		for y in range(112):
			ratio = y / 111.0
			color = tuple(int(round(top_color[i] + (bottom_color[i] - top_color[i]) * ratio)) for i in range(3))
			draw.line((0, y, 127, y), fill=color)
		draw.rectangle((0, 0, 127, 5), fill=accent)

		if motif in ('splat',):
			points = []
			for point_index in range(24):
				angle = (math.pi * 2 * point_index / 24.0) - math.pi / 2
				radius = 48 if point_index % 2 == 0 else (34 if point_index % 4 else 39)
				points.append((64 + radius * math.cos(angle), 55 + radius * math.sin(angle)))
			draw.polygon(points, fill=accent)
			draw.ellipse((22, 17, 106, 93), fill=bottom_color, outline=highlight, width=2)
		elif motif == 'checker':
			for row in range(3):
				for column in range(4):
					if (row + column) % 2 == 0:
						draw.rectangle((column * 32, 10 + row * 25, column * 32 + 31, 34 + row * 25), fill=accent)
		elif motif == 'blocks':
			draw.rectangle((8, 16, 45, 97), fill=accent)
			draw.rectangle((46, 16, 83, 97), fill=highlight)
			draw.rectangle((84, 16, 120, 97), fill=bottom_color)
		elif motif == 'bolt':
			draw.polygon([(72, 8), (46, 53), (63, 53), (51, 103), (87, 47), (68, 47)], fill=accent)
		elif motif == 'stripes':
			for y in (21, 39, 57, 75, 93):
				draw.rectangle((8, y, 120, y + 7), fill=accent if y % 2 else highlight)
		elif motif == 'frame':
			draw.rectangle((12, 9, 115, 102), outline=accent, width=6)
			draw.rectangle((20, 17, 107, 94), outline=highlight, width=2)
		elif motif == 'planet':
			draw.ellipse((20, 12, 106, 98), fill=accent, outline=highlight, width=2)
			draw.ellipse((38, 34, 90, 86), fill=bottom_color)
			draw.line((10, 80, 117, 29), fill=highlight, width=4)
		elif motif == 'bubbles':
			for x, y, radius in ((28, 34, 18), (66, 24, 24), (99, 47, 15), (43, 78, 14), (86, 82, 20)):
				draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=accent, outline=highlight, width=2)
		elif motif == 'ornament':
			draw.ellipse((25, 16, 103, 98), fill=accent, outline=highlight, width=3)
			draw.rectangle((56, 8, 72, 23), fill=highlight)
		elif motif in ('orb', 'oval', 'retro', 'circle'):
			draw.ellipse((13, 9, 115, 103), fill=accent, outline=highlight, width=3)
			if motif == 'retro':
				draw.ellipse((22, 23, 106, 87), outline=bottom_color, width=4)
			elif motif == 'oval':
				draw.ellipse((7, 36, 121, 78), outline=highlight, width=3)

		logo_name = str(channel.get('logo_text') or channel.get('name') or 'TV')
		# Keep network names legible in a compact badge, wrapping on word boundaries.
		words = logo_name.replace('&', 'and').split()
		lines, current = [], ''
		for word in words:
			candidate = (current + ' ' + word).strip()
			if len(candidate) > 11 and current:
				lines.append(current)
				current = word
			else:
				current = candidate
		if current:
			lines.append(current)
		if not lines:
			lines = ['TV']
		if len(lines) > 3:
			lines = lines[:2] + [' '.join(lines[2:])]
		font_paths = []
		for kodi_font in ('special://xbmc/media/Fonts/arialbd.ttf', 'special://xbmc/media/Fonts/Arial.ttf'):
			try:
				font_paths.append(kodi_utils.translate_path(kodi_font))
			except Exception:
				continue
		fonts = []
		for font_path in font_paths:
			try:
				for font_size in (24, 22, 20, 18, 16, 14, 12):
					fonts.append(ImageFont.truetype(font_path, font_size))
			except Exception:
				continue
		if not fonts:
			fonts = [ImageFont.load_default()]
		font = fonts[-1]
		for candidate_font in fonts:
			max_width = 0
			for line in lines:
				try:
					box = draw.textbbox((0, 0), line, font=candidate_font)
					line_width = box[2] - box[0]
				except Exception:
					line_width = draw.textsize(line, font=candidate_font)[0]
				max_width = max(max_width, line_width)
			if max_width <= 106:
				font = candidate_font
				break
		heights = []
		widths = []
		for line in lines:
			try:
				box = draw.textbbox((0, 0), line, font=font)
				widths.append(box[2] - box[0])
				heights.append(box[3] - box[1])
			except Exception:
				width, height = draw.textsize(line, font=font)
				widths.append(width)
				heights.append(height)
		line_gap = 1
		total_height = sum(heights) + line_gap * (len(lines) - 1)
		y = max(12, (112 - total_height) / 2)
		text_color = foreground if motif != 'checker' else (255, 255, 255)
		for index, line in enumerate(lines):
			x = (128 - widths[index]) / 2
			draw.text((x + 1, y + 2), line, fill=(0, 0, 0), font=font)
			draw.text((x, y), line, fill=text_color, font=font)
			y += heights[index] + line_gap

		temp_path = '%s.%s.tmp' % (logo_path, id(image))
		try:
			image.save(temp_path, format='PNG', optimize=True)
			os.replace(temp_path, logo_path)
		finally:
			try:
				image.close()
			except Exception:
				pass
			if os.path.isfile(temp_path):
				os.remove(temp_path)
		return logo_path
	except Exception:
		return fallback

def _load_channel_config():
	try:
		config_path = os.path.join(
			kodi_utils.addon_path(), 'resources', 'data', 'tv_guide_channels.json'
		)
		with open(config_path, 'r', encoding='utf-8') as config_file:
			config = json.load(config_file)
		if not isinstance(config, dict):
			raise ValueError('channel configuration must be an object')
		network_data = config.get('network_channels', [])
		if not isinstance(network_data, list):
			raise ValueError('network_channels must be a list')
		network_channels = tuple(_normalize_channel_definition(item) for item in network_data)
		for channel in network_channels:
			if 'tv_genre' in channel or 'movie_genre' in channel:
				raise ValueError('network channels cannot use broad genre feeds')
			network_id = channel.get('tv_network_id')
			candidate_titles = channel.get('tv_candidate_titles', [])
			movie_titles = channel.get('movie_candidate_titles', [])
			expected_network_names = channel.get('expected_tv_network_names', [])
			enabled = channel.get('enabled', True)
			if not isinstance(enabled, bool):
				raise ValueError('network channel enabled must be true or false')
			if network_id and not str(network_id).isdigit():
				raise ValueError('TV network IDs must be numeric')
			if not isinstance(candidate_titles, list) or any(not isinstance(title, str) or not title.strip() for title in candidate_titles):
				raise ValueError('TV candidate titles must be a list of names')
			if not isinstance(movie_titles, list) or any(not isinstance(title, str) or not title.strip() for title in movie_titles):
				raise ValueError('movie candidate titles must be a list of names')
			if not isinstance(expected_network_names, list) or any(not isinstance(name, str) or not name.strip() for name in expected_network_names):
				raise ValueError('expected TV network names must be a list of names')
			if network_id and not expected_network_names:
				raise ValueError('network IDs must declare the expected TMDb network name')
			if expected_network_names and not network_id:
				raise ValueError('expected TV network names require a network ID')
			channel['tv_network_id'] = str(network_id) if network_id else ''
			channel['enabled'] = enabled
			channel['tv_candidate_titles'] = tuple(title.strip() for title in candidate_titles)
			channel['movie_candidate_titles'] = tuple(title.strip() for title in movie_titles)
			channel['expected_tv_network_names'] = tuple(name.strip() for name in expected_network_names)
			if enabled and not (
				channel['tv_network_id'] or channel['tv_candidate_titles'] or channel['movie_candidate_titles']
			):
				raise ValueError('enabled network channels need a verified network or curated titles')
		network_channels = _dedupe_channels(network_channels, 'configuration')
		seasonal_data = config.get('seasonal_channels')
		if not isinstance(seasonal_data, dict):
			raise ValueError('seasonal_channels must be an object')
		seasonal_channels = {}
		for month, channel in seasonal_data.items():
			month = str(month)
			if not month.isdigit() or not 1 <= int(month) <= 12:
				raise ValueError('seasonal channel keys must be calendar months')
			seasonal = _normalize_channel_definition(channel)
			if seasonal['id'] != 'holiday' or not seasonal.get('season'):
				raise ValueError('seasonal channels must identify their season')
			if not seasonal.get('movie_keyword') or not seasonal.get('tv_keyword'):
				raise ValueError('seasonal channels require specific holiday keywords')
			if seasonal.get('movie_genre') or seasonal.get('tv_genre'):
				raise ValueError('seasonal channels cannot fall back to broad genres')
			seasonal_channels[month] = seasonal
		network_numbers = {item['number'] for item in network_channels}
		if any(item['number'] in network_numbers for item in seasonal_channels.values()):
			raise ValueError('seasonal channel numbers must not collide with network channels')
		return {
			'network_channels': network_channels,
			'seasonal_channels': seasonal_channels,
		}
	except Exception as exc:
		kodi_utils.logger('TV Guide channel configuration fallback: %s' % exc)
		return _DEFAULT_CHANNEL_CONFIG

CHANNEL_CONFIG = _load_channel_config()
NETWORK_CHANNELS = CHANNEL_CONFIG['network_channels']
SEASONAL_CHANNELS = CHANNEL_CONFIG['seasonal_channels']


def _holiday_channel(now=None):
	now = now or datetime.now()
	channel = SEASONAL_CHANNELS.get(str(now.month))
	return dict(channel) if channel else None


def _channels(now=None):
	channels = [channel for channel in NETWORK_CHANNELS if channel.get('enabled', True)]
	holiday = _holiday_channel(now)
	if holiday:
		channels.append(holiday)
	channels = _dedupe_channels(channels, 'active lineup')
	return sorted(channels, key=lambda channel: int(channel['number']))

def _format_time(value):
	return value.strftime('%I:%M %p').lstrip('0')


def _guide_day_offset(params):
	"""Clamp a requested guide day to the rolling history and forecast window."""
	if not isinstance(params, dict):
		return 0
	try:
		offset = int(str(params.get('day_offset', 0)).strip())
	except (TypeError, ValueError):
		return 0
	return max(-GUIDE_DAYS_BACK, min(GUIDE_DAYS_AHEAD, offset))


def _format_guide_date(value):
	return '%s, %d %s %d' % (
		value.strftime('%A'), value.day, value.strftime('%B'), value.year,
	)


def _guide_header(value):
	return '%s   •   %s   •   YOUR ON-DEMAND CHANNELS' % (
		_format_guide_date(value), _format_time(value),
	)


def _guide_day_url(day_offset):
	return kodi_utils.build_url({
		'mode': 'tvguide.main',
		'day_offset': str(_guide_day_offset({'day_offset': day_offset})),
	})


def _schedule_daypart(value):
	hour = value.hour
	if 6 <= hour < 17: return 'daytime'
	if 17 <= hour < 23: return 'prime_time'
	return 'overnight'


def _program_duration_minutes(program, channel, slot_start):
	"""Use verified TMDb runtime; use a restrained media-type estimate only if absent."""
	try:
		duration = int(float(program.get('duration_minutes')))
		if 15 <= duration <= 360:
			return duration
	except (TypeError, ValueError):
		pass
	return 110 if program.get('media_type') == 'movie' else 30

def _schedule_for_time(programs, channel, now, count=3):
	"""Build a deterministic, continuous daily schedule and return now plus the next slots."""
	if not programs: return []
	try:
		count = max(int(count), 1)
	except (TypeError, ValueError):
		count = 3
	day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
	channel_seed = int(hashlib.sha1(str(channel.get('id', 'channel')).encode('utf-8')).hexdigest()[:8], 16)
	program_index = (day_start.toordinal() + channel_seed) % len(programs)
	cursor = day_start
	schedule, iterations = [], 0
	# The shortest accepted slot is 15 minutes, so 100 iterations cover a full day
	# and the three displayed look-ahead entries without unbounded work.
	while cursor <= now and iterations < 100:
		program = programs[program_index]
		duration = _program_duration_minutes(program, channel, cursor)
		end = cursor + timedelta(minutes=duration)
		if end <= cursor: break
		schedule.append({
			'program': program,
			'start': cursor,
			'end': end,
			'duration_minutes': duration,
			'daypart': _schedule_daypart(cursor),
		})
		cursor = end
		program_index = (program_index + 1) % len(programs)
		iterations += 1
	if not schedule: return []
	current_index = len(schedule) - 1
	target_length = current_index + count
	while len(schedule) < target_length and iterations < 100:
		program = programs[program_index]
		duration = _program_duration_minutes(program, channel, cursor)
		end = cursor + timedelta(minutes=duration)
		if end <= cursor: break
		schedule.append({
			'program': program,
			'start': cursor,
			'end': end,
			'duration_minutes': duration,
			'daypart': _schedule_daypart(cursor),
		})
		cursor = end
		program_index = (program_index + 1) % len(programs)
		iterations += 1
	return schedule[current_index:target_length]


def _program_record(result, media_type, fallback_icon):
	if not isinstance(result, dict): return None
	title = result.get('name') or result.get('title')
	tmdb_id = result.get('id')
	if not title or not str(tmdb_id or '').isdigit(): return None
	poster_path = result.get('poster_path') or ''
	backdrop_path = result.get('backdrop_path') or ''
	program = {
		'title': title,
		'plot': result.get('overview') or 'Program information is not available.',
		'thumb': 'https://image.tmdb.org/t/p/w342%s' % poster_path if poster_path else fallback_icon,
		'fanart': 'https://image.tmdb.org/t/p/w1280%s' % backdrop_path if backdrop_path else '',
		'media_type': media_type,
		'tmdb_id': str(tmdb_id),
	}
	runtime = result.get('runtime')
	if media_type == 'tvshow':
		runtime = result.get('episode_run_time') or runtime
	if isinstance(runtime, (list, tuple)):
		runtime = next((value for value in runtime if value not in (None, '', 0)), None)
	try:
		duration = int(float(runtime))
		if 15 <= duration <= 360:
			program['duration_minutes'] = duration
	except (TypeError, ValueError):
		pass
	return program


def _matches_channel_genre(result, genre_ids):
	if not genre_ids: return True
	expected = {item.strip() for item in str(genre_ids).split('|') if item.strip()}
	actual = {str(item) for item in result.get('genre_ids', [])}
	return bool(expected.intersection(actual))


def _canonical_title(title):
	return ''.join(character.lower() for character in str(title or '') if character.isalnum())


def _curated_candidate_titles(channel, tmdb_api, media_type):
	"""Resolve channel-curated titles using exact normalized title matches."""
	is_movie = media_type == 'movie'
	field = 'movie_candidate_titles' if is_movie else 'tv_candidate_titles'
	search_function = tmdb_api.tmdb_movies_search if is_movie else tmdb_api.tmdb_tv_search
	programs = []
	for title in channel.get(field, ()):
		try:
			search = search_function(quote_plus(title), 1)
			expected = _canonical_title(title)
			match = next((
				result for result in (search or {}).get('results', [])
				if isinstance(result, dict) and _canonical_title(result.get('name') or result.get('title')) == expected
			), None)
			if match: programs.append(match)
		except Exception:
			continue
	return {'results': programs}


def _network_candidate_titles(channel, tmdb_api):
	"""Resolve curated network series without accepting loose search matches."""
	return _curated_candidate_titles(channel, tmdb_api, 'tvshow')


def _network_movie_candidate_titles(channel, tmdb_api):
	"""Resolve curated network films without accepting loose search matches."""
	return _curated_candidate_titles(channel, tmdb_api, 'movie')


def _verified_tv_network_feed(channel, tmdb_api):
	"""Use a network feed only when TMDb confirms the configured network ID."""
	network_id = channel.get('tv_network_id')
	if not network_id: return None
	expected = {_canonical_title(name) for name in channel.get('expected_tv_network_names', ())}
	if expected:
		details = tmdb_api.tmdb_network_details(network_id)
		actual = _canonical_title((details or {}).get('name', ''))
		if actual not in expected:
			kodi_utils.logger('TV Guide network mapping mismatch', '%s expected=%s actual=%s' % (
				channel.get('id', 'unknown'), '|'.join(sorted(expected)), actual or 'missing'
			))
			return None
	return tmdb_api.tmdb_tv_networks(network_id, 1)


def _favorite_program_identity(favourite):
	"""Return an add-on media type and TMDb ID when Kodi exposes one."""
	try:
		path = favourite.get('path', '')
		query = parse_qs(urlparse(path).query)
		tmdb_id = query.get('tmdb_id', [None])[0]
		if not tmdb_id or not str(tmdb_id).isdigit(): return None, None
		mode = query.get('mode', [''])[0].lower()
		media_type = query.get('media_type', [''])[0].lower()
		if media_type in ('tvshow', 'tv', 'episode', 'shows') or mode in (
			'build_tvshow_list', 'build_season_list', 'build_episode_list', 'tvshow'
		):
			return 'tvshow', str(tmdb_id)
		if media_type in ('movie', 'movies', 'film') or mode in (
			'build_movie_list', 'play_movie', 'movie'
		):
			return 'movie', str(tmdb_id)
	except Exception:
		pass
	return None, None


def _favorite_tvshow_id(favourite):
	"""Keep compatibility for callers that need only a saved show's TMDb ID."""
	media_type, tmdb_id = _favorite_program_identity(favourite)
	return tmdb_id if media_type == 'tvshow' else None


def _channel_programs(channel, favourites=None, error_state=None):
	"""Load only verified network feeds, exact curated titles, or seasonal keywords."""
	if not channel.get('enabled', True):
		return []
	icon = kodi_utils.get_icon(channel['icon'])
	try:
		from modules.settings import tmdb_api_key
		if tmdb_api_key() in (None, '', 'empty_setting'):
			return []
		from apis import tmdb_api
		seasonal = bool(channel.get('season'))
		show_data = (
			tmdb_api.tmdb_tv_keyword_results_direct(channel['tv_keyword'], 1)
			if seasonal and channel.get('tv_keyword') else None
		)
		movie_data = (
			tmdb_api.tmdb_movie_keyword_results_direct(channel['movie_keyword'], 1)
			if seasonal and channel.get('movie_keyword') else None
		)
		if seasonal and str(channel.get('season', '')).strip().lower() == 'halloween' and isinstance(movie_data, dict):
			# Keep the Halloween row horror-focused even when the holiday keyword also
			# returns family or comedy titles. Missing genre metadata fails closed.
			movie_data = dict(movie_data)
			movie_data['results'] = [
				result for result in (movie_data.get('results') or [])
				if isinstance(result, dict) and '27' in {str(genre_id) for genre_id in (result.get('genre_ids') or [])}
			]
		network_data = _verified_tv_network_feed(channel, tmdb_api) if not seasonal and channel.get('tv_network_id') else None
		curated_show_data = _network_candidate_titles(channel, tmdb_api) if not seasonal and channel.get('tv_candidate_titles') else None
		curated_movie_data = _network_movie_candidate_titles(channel, tmdb_api) if not seasonal and channel.get('movie_candidate_titles') else None
		shows, movies, seen = [], [], set()

		def append_programs(data, media_type):
			for result in (data or {}).get('results', []):
				if not isinstance(result, dict):
					continue
				program = _program_record(result, media_type, icon)
				if not program:
					continue
				key = (media_type, program['tmdb_id'])
				if key in seen:
					continue
				seen.add(key)
				(shows if media_type == 'tvshow' else movies).append(program)

		append_programs(show_data, 'tvshow')
		append_programs(network_data, 'tvshow')
		append_programs(curated_show_data, 'tvshow')
		append_programs(movie_data, 'movie')
		append_programs(curated_movie_data, 'movie')
		programs = []
		for index in range(max(len(shows), len(movies))):
			if index < len(shows):
				programs.append(shows[index])
			if index < len(movies):
				programs.append(movies[index])
		if programs:
			return programs[:6]
	except Exception as exc:
		if error_state is not None:
			error_state['error'] = str(exc)
	return []

def _source_check_cache_key(program):
	from modules import settings
	media_type = 'episode' if program.get('media_type') == 'tvshow' else 'movie'
	providers = '-'.join(settings.active_internal_scrapers())
	autoplay = media_type == 'episode' or settings.auto_play('movie')
	quality_type = 'autoplay' if autoplay else 'results'
	quality = ','.join(settings.quality_filter('%s_quality_%s' % (quality_type, media_type)))
	return 'tvguide_source_v3_%s_%s_%s_%s' % (media_type, program['tmdb_id'], providers, quality)


def _guide_snapshot_cache_key(channels, favourites):
	"""Build a profile-specific key so stale source checks do not cross settings changes."""
	from modules import settings
	autoplay_movie = settings.auto_play('movie')
	context = {
		'schema': SNAPSHOT_SCHEMA,
		'addon_version': kodi_utils.addon_version(),
		'channels': channels,
		'favorites': favourites,
		'providers': settings.active_internal_scrapers(),
		'episode_quality': settings.quality_filter('autoplay_quality_episode'),
		'movie_quality': settings.quality_filter(
			'%s_quality_movie' % ('autoplay' if autoplay_movie else 'results')
		),
		'autoplay_movie': autoplay_movie,
		'tmdb_api_key': settings.tmdb_api_key(),
	}
	serialized = json.dumps(context, sort_keys=True, separators=(',', ':'), default=str)
	return 'tvguide_snapshot_v4_%s' % hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def _process_rss_mb():
	"""Return Kodi's current process RSS where the platform exposes /proc."""
	try:
		with open('/proc/self/status', 'r') as status_file:
			for line in status_file:
				if line.startswith('VmRSS:'):
					return round(float(line.split()[1]) / 1024.0, 1)
	except Exception:
		pass
	return None


def safe_guide_join_target(offset_seconds, total_seconds, current_seconds=0.0, seek_enabled=False):
	"""Return a join position only when Kodi confirms a seekable, fresh stream."""
	try:
		offset, total, current = float(offset_seconds), float(total_seconds), float(current_seconds)
	except (TypeError, ValueError):
		return None
	if not seek_enabled or offset <= 0 or total <= 0 or current > 5:
		return None
	if offset >= total * 0.90:
		return None
	return offset


def playback_seconds_remaining(player):
	"""Return Kodi player time remaining, or None when duration data is unavailable."""
	try:
		total = float(player.getTotalTime())
		current = float(player.getTime())
	except Exception:
		return None
	if total <= 0 or current < 0:
		return None
	return max(total - current, 0.0)


def should_refresh_before_end(remaining_seconds, already_attempted=False):
	return (
		remaining_seconds is not None
		and remaining_seconds <= SNAPSHOT_PRE_END_REFRESH_SECONDS
		and not already_attempted
	)


def _new_progress_state(total, show_progress=True):
	return {
		'dialog': None,
		'show_progress': show_progress,
		'checked': 0,
		'probed': 0,
		'total': max(total, 1),
		'source_cache_hits': 0,
		'source_probes': 0,
		'source_check_seconds': 0.0,
		'catalog_seconds': 0.0,
		'catalog_feed_lookups': 0,
		'candidate_count': 0,
		'item_build_seconds': 0.0,
		'logo_reference_seconds': 0.0,
		'rows_added': 0,
	}


def _check_program_source(program, channel, progress_state):
	"""Check and cache a playable source; for series, cache the exact episode tested."""
	if program.get('favorite_index') is not None:
		return str(program.get('favorite_index', '')).isdigit() and bool(program.get('favorite_path'))
	if program.get('media_type') not in ('tvshow', 'movie') or not str(program.get('tmdb_id', '')).isdigit():
		return False
	check_started = perf_counter()
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
			progress_state['source_cache_hits'] = progress_state.get('source_cache_hits', 0) + 1
			if cached.get('duration_minutes'):
				program['duration_minutes'] = cached['duration_minutes']
			if cached.get('available'):
				program['_guide_season'] = cached.get('season')
				program['_guide_episode'] = cached.get('episode')
				if program.get('media_type') == 'tvshow' and 'mpaa' in cached:
					program['_guide_mpaa'] = cached.get('mpaa') or ''
			update_progress()
			return bool(cached.get('available'))
		progress_state['probed'] = progress_state.get('probed', 0) + 1
		progress_state['source_probes'] = progress_state.get('source_probes', 0) + 1
		if progress_state.get('show_progress', True) and progress_state.get('dialog') is None:
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
		mpaa = None
		if program['media_type'] == 'movie':
			meta = metadata.movie_meta('tmdb_id', tmdb_id, settings.tmdb_api_key(), settings.mpaa_region(), get_datetime())
			params = {'media_type': 'movie', 'tmdb_id': tmdb_id}
			playback_key = settings.playback_key()
			params[playback_key] = playback_key
		else:
			meta = metadata.tvshow_meta('tmdb_id', tmdb_id, settings.tmdb_api_key(), settings.mpaa_region(), get_datetime())
			if not meta or meta.get('blank_entry'):
				return False
			mpaa = meta.get('mpaa') or ''
			program['_guide_mpaa'] = mpaa
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
		try:
			duration_seconds = float(meta.get('duration') or 0)
			duration_minutes = int(round(duration_seconds / 60.0))
			if 15 <= duration_minutes <= 360:
				program['duration_minutes'] = duration_minutes
		except (TypeError, ValueError):
			pass
		params.update({'background': 'true', 'check_sources_only': 'true'})
		from modules.sources import Sources
		available = bool(Sources().playback_prep(params))
		result = {'available': available}
		if program.get('duration_minutes'):
			result['duration_minutes'] = int(program['duration_minutes'])
		if program.get('media_type') == 'tvshow':
			result['mpaa'] = mpaa or ''
		if available and season is not None and episode is not None:
			result.update({'season': int(season), 'episode': int(episode)})
			program['_guide_season'], program['_guide_episode'] = int(season), int(episode)
		# Positive checks stay warm through the next few guide hours. Negative
		# checks expire sooner so a new source can appear without waiting long.
		main_cache.set(cache_key, result, expiration=6 if available else SOURCE_NEGATIVE_CACHE_HOURS)
		return available
	except Exception:
		return False
	finally:
		progress_state['source_check_seconds'] = progress_state.get('source_check_seconds', 0.0) + (perf_counter() - check_started)


def _schedule_slot_widths(schedule, available_width=1320, minimum_width=140):
	"""Convert actual program runtimes to proportional screen widths."""
	durations = [max(int(entry.get('duration_minutes') or 1), 1) for entry in schedule]
	if not durations:
		return []
	width_count = len(durations)
	minimum_width = min(int(minimum_width), int(available_width) // width_count)
	pinned = {index for index, duration in enumerate(durations) if duration * available_width / float(sum(durations)) < minimum_width}
	widths = [0] * width_count
	for index in pinned:
		widths[index] = minimum_width
	remaining_width = available_width - sum(widths)
	remaining_duration = sum(durations[index] for index in range(width_count) if index not in pinned)
	if remaining_duration <= 0:
		each = available_width // width_count
		widths = [each] * width_count
		widths[-1] += available_width - sum(widths)
	else:
		allocated = 0
		for index, duration in enumerate(durations):
			if index in pinned:
				continue
			width = int(round(remaining_width * duration / float(remaining_duration)))
			widths[index] = width
			allocated += width
		last = next((index for index in range(width_count - 1, -1, -1) if index not in pinned), None)
		if last is not None:
			widths[last] += remaining_width - allocated
	return widths


def _channel_item(handle, channel, start_time, fanart, progress_state, prevalidated=None, favourites=None, day_offset=0):
	if prevalidated is None:
		catalog_started = perf_counter()
		candidates = _channel_programs(channel, favourites)
		progress_state['catalog_seconds'] += perf_counter() - catalog_started
		progress_state['catalog_feed_lookups'] += sum((
			2 * bool(channel.get('tv_network_id')),
			len(channel.get('tv_candidate_titles', ())),
			len(channel.get('movie_candidate_titles', ())),
			bool(channel.get('tv_keyword') and channel.get('season')),
			bool(channel.get('movie_keyword') and channel.get('season')),
		))
		progress_state['candidate_count'] += len(candidates)
		if not candidates:
			return None
		programs, probes_before = [], progress_state.get('probed', 0)
		for program in candidates:
			if _check_program_source(program, channel, progress_state):
				programs.append(program)
			if len(programs) >= 3 or progress_state.get('probed', 0) - probes_before >= MAX_GUIDE_SOURCE_PROBES_PER_CHANNEL:
				break
	else:
		programs = prevalidated
	if not programs:
		return None
	validated_programs = programs
	item_started = perf_counter()
	item = kodi_utils.make_listitem()
	logo_started = perf_counter()
	icon = _channel_logo(channel)
	progress_state['logo_reference_seconds'] += perf_counter() - logo_started
	schedule = _schedule_for_time(list(validated_programs), channel, start_time, count=3)
	if not schedule:
		return None
	programs = [entry['program'] for entry in schedule]
	# Keep channel labels separate from the show's title in VideoInfoTag. Kodi
	# exposes the title as ListItem.Label on some builds, so the skin uses the
	# explicit channel properties below for the guide columns.
	item.setLabel(channel['name'])
	item.setLabel2(channel['number'])
	item.setArt({
		'icon': icon,
		'thumb': programs[0]['thumb'],
		'poster': programs[0]['thumb'],
		'fanart': programs[0]['fanart'] or fanart,
		'banner': icon,
	})
	current_program = programs[0]
	info = item.getVideoInfoTag(True)
	info.setTitle(current_program['title'])
	info.setPlot(current_program['plot'])
	info.setMediaType(current_program['media_type'])
	if current_program.get('media_type') == 'tvshow' and current_program.get('tmdb_id'):
		try:
			mpaa = current_program.get('_guide_mpaa')
			if mpaa is None:
				from modules import metadata, settings
				from modules.utils import get_datetime
				if settings.tmdb_api_key():
					program_meta = metadata.tvshow_meta('tmdb_id', current_program['tmdb_id'], settings.tmdb_api_key(), settings.mpaa_region(), get_datetime())
					if program_meta and not program_meta.get('blank_entry'):
						mpaa = program_meta.get('mpaa') or ''
					else:
						mpaa = ''
					current_program['_guide_mpaa'] = mpaa
			if mpaa:
				info.setMpaa(mpaa)
		except Exception:
			pass
	item.setProperty('channel_number', channel['number'])
	item.setProperty('channel_id', channel['id'])
	item.setProperty('channel_name', channel['name'])
	item.setProperty('channel_description', channel['description'])
	day_offset = _guide_day_offset({'day_offset': day_offset})
	item.setProperty('guide_header', _guide_header(start_time))
	item.setProperty('guide_previous_url', _guide_day_url(max(-GUIDE_DAYS_BACK, day_offset - 1)))
	item.setProperty('guide_next_url', _guide_day_url(min(GUIDE_DAYS_AHEAD, day_offset + 1)))
	item.setProperty('now_title', current_program['title'])
	item.setProperty('now_plot', current_program['plot'])
	slot_widths = _schedule_slot_widths(schedule)
	slot_left = 465
	for index, entry in enumerate(schedule, 1):
		program = entry['program']
		width = slot_widths[index - 1]
		item.setProperty('slot_%s' % index, '%s–%s   %s' % (_format_time(entry['start']), _format_time(entry['end']), program['title']))
		item.setProperty('program_%s_title' % index, program['title'])
		item.setProperty('program_%s_plot' % index, program['plot'])
		item.setProperty('program_%s_thumb' % index, program['thumb'])
		item.setProperty('program_%s_duration' % index, str(entry['duration_minutes']))
		item.setProperty('program_%s_daypart' % index, entry['daypart'])
		item.setProperty('program_%s_width' % index, str(width))
		item.setProperty('program_%s_left' % index, str(slot_left))
		item.setProperty('program_%s_text_left' % index, str(slot_left + 14))
		item.setProperty('program_%s_text_width' % index, str(max(width - 28, 24)))
		slot_left += width
	# Keep a TMDb ID on playable show and movie entries. Show entries start a
	# random aired episode; movie entries start that film.
	tmdb_id = current_program.get('tmdb_id')
	if tmdb_id and current_program.get('media_type') in ('tvshow', 'movie'):
		item.setProperty('IsPlayable', 'true')
		item.setProperty('tmdb_id', str(tmdb_id))
		info.setUniqueIDs({'tmdb': str(tmdb_id)})
	elif current_program.get('favorite_index') is not None:
		item.setProperty('IsPlayable', 'true')
	# Keep the channel action stable across time-slot changes. The playback
	# route resolves the current scheduled program from the validated snapshot.
	url_params = {
		'mode': 'tvguide.play_channel',
		'channel': channel['id'],
		'day_offset': str(day_offset),
	}
	url = kodi_utils.build_url(url_params)
	kodi_utils.add_item(handle, url, item, False)
	progress_state['rows_added'] += 1
	progress_state['item_build_seconds'] += perf_counter() - item_started
	return validated_programs

def refresh_snapshot_for_key(cache_key, monitor=None, force=False):
	"""Refresh a previously opened guide quietly while Kodi is playing video.

	The force flag lets the playback monitor update the cache shortly before a
	video ends, so the next guide open can use a ready snapshot.
	"""
	if not cache_key: return False
	from caches.main_cache import main_cache
	snapshot = main_cache.get(cache_key)
	if not isinstance(snapshot, dict) or snapshot.get('schema') != SNAPSHOT_SCHEMA: return False
	channels = snapshot.get('channels')
	favourites = snapshot.get('favorites')
	previous_programs = snapshot.get('programs')
	if not isinstance(channels, list) or not isinstance(favourites, list) or not isinstance(previous_programs, dict): return False
	now = int(time())
	if not force and int(snapshot.get('refresh_after') or snapshot.get('updated_at', 0) + SNAPSHOT_INITIAL_REFRESH_DELAY) > now: return False
	progress_state = _new_progress_state(len(channels) * 4, show_progress=False)
	updated_programs = dict(previous_programs)
	processed, failed = 0, 0
	refresh_started = perf_counter()
	for channel in channels:
		if monitor and monitor.abortRequested():
			kodi_utils.logger('TV Guide Refresh Profile', 'aborted=true channels=%d source_probes=%d' % (processed, progress_state['source_probes']))
			return False
		try:
			catalog_started = perf_counter()
			catalog_status = {}
			candidates = _channel_programs(channel, favourites, catalog_status)
			if catalog_status.get('error'): raise RuntimeError(catalog_status['error'])
			progress_state['catalog_seconds'] += perf_counter() - catalog_started
			progress_state['catalog_feed_lookups'] += sum((
				2 * bool(channel.get('tv_network_id')),
				len(channel.get('tv_candidate_titles', ())),
				len(channel.get('movie_candidate_titles', ())),
				bool(channel.get('tv_keyword') and channel.get('season')),
				bool(channel.get('movie_keyword') and channel.get('season')),
			))
			progress_state['candidate_count'] += len(candidates)
			playable, probes_before = [], progress_state.get('probed', 0)
			for program in candidates:
				if monitor and monitor.abortRequested():
					kodi_utils.logger('TV Guide Refresh Profile', 'aborted=true channels=%d source_probes=%d' % (processed, progress_state['source_probes']))
					return False
				if _check_program_source(program, channel, progress_state): playable.append(program)
				if len(playable) >= 3 or progress_state.get('probed', 0) - probes_before >= MAX_REFRESH_SOURCE_PROBES_PER_CHANNEL: break
			updated_programs[channel['id']] = playable
			processed += 1
		except Exception as exc:
			failed += 1
			kodi_utils.logger('TV Guide Refresh', 'Channel %s refresh failed: %s' % (channel.get('id', 'unknown'), str(exc)))
	if not processed:
		snapshot['refresh_after'] = now + SNAPSHOT_RETRY_DELAY
		refreshed_at = snapshot.get('updated_at', 0)
		remaining_hours = max((refreshed_at + SNAPSHOT_CACHE_HOURS * 3600 - now) / 3600.0, 0)
		if remaining_hours: main_cache.set(cache_key, snapshot, expiration=remaining_hours)
	else:
		refreshed_at = now
		snapshot.update({
			'schema': SNAPSHOT_SCHEMA,
			'channels': channels,
			'favorites': favourites,
			'programs': updated_programs,
			'completed_channels': [channel['id'] for channel in channels],
			'complete': True,
			'updated_at': refreshed_at,
			'refresh_after': now + (SNAPSHOT_RETRY_DELAY if failed else SNAPSHOT_REFRESH_INTERVAL),
		})
		main_cache.set(cache_key, snapshot, expiration=SNAPSHOT_CACHE_HOURS)
	elapsed = perf_counter() - refresh_started
	kodi_utils.logger(
		'TV Guide Refresh Profile',
		'channels=%d failed=%d candidates=%d source_cache_hits=%d source_probes=%d forced=%s '
		'catalog_s=%.3f source_s=%.3f total_s=%.3f next_refresh_seconds=%d' % (
			processed, failed, progress_state['candidate_count'], progress_state['source_cache_hits'],
			progress_state['source_probes'], str(bool(force)).lower(), progress_state['catalog_seconds'],
			progress_state['source_check_seconds'], elapsed,
			max(snapshot.get('refresh_after', now) - now, 0),
		),
	)
	return bool(processed)



def prewarm_snapshot(monitor=None, player=None):
	"""Build the guide snapshot quietly during Kodi startup, resuming partial work."""
	channels = _channels()
	if not channels:
		return True
	from caches.main_cache import main_cache
	favourites = []
	cache_key = _guide_snapshot_cache_key(channels, favourites)
	kodi_utils.set_property(SNAPSHOT_KEY_PROPERTY, cache_key)
	now = int(time())
	snapshot = main_cache.get(cache_key)
	if isinstance(snapshot, dict) and snapshot.get('schema') == SNAPSHOT_SCHEMA:
		if snapshot.get('complete') and now - int(snapshot.get('updated_at', 0)) < SNAPSHOT_CACHE_HOURS * 3600:
			kodi_utils.logger('TV Guide Preload Profile', 'snapshot=warm channels=%d complete=true' % len(channels))
			return True
		if now - int(snapshot.get('updated_at', 0)) >= SNAPSHOT_CACHE_HOURS * 3600:
			programs, completed = {}, set()
		else:
			programs = dict(snapshot.get('programs') or {})
			completed = set(snapshot.get('completed_channels') or ())
	else:
		programs, completed = {}, set()
	progress_state = _new_progress_state(len(channels) * 4, show_progress=False)
	started = perf_counter()

	def save_partial(complete=False):
		current_time = int(time())
		main_cache.set(cache_key, {
			'schema': SNAPSHOT_SCHEMA,
			'channels': channels,
			'favorites': favourites,
			'programs': programs,
			'completed_channels': sorted(completed),
			'complete': bool(complete),
			'updated_at': current_time,
			'refresh_after': current_time + SNAPSHOT_INITIAL_REFRESH_DELAY,
		}, expiration=SNAPSHOT_CACHE_HOURS)

	for channel in channels:
		channel_id = channel['id']
		if channel_id in completed:
			continue
		try:
			if monitor and monitor.abortRequested():
				save_partial()
				return False
			if player and player.isPlayingVideo():
				save_partial()
				return False
			if not kodi_utils.get_visibility('Window.IsActive(Home)'):
				save_partial()
				return False
			error_state = {}
			catalog_started = perf_counter()
			candidates = _channel_programs(channel, favourites, error_state)
			progress_state['catalog_seconds'] += perf_counter() - catalog_started
			if error_state.get('error'):
				kodi_utils.logger('TV Guide Preload', 'channel=%s catalog_error=%s' % (channel_id, error_state['error']))
				save_partial()
				return False
			progress_state['catalog_feed_lookups'] += sum((
				2 * bool(channel.get('tv_network_id')),
				len(channel.get('tv_candidate_titles', ())),
				len(channel.get('movie_candidate_titles', ())),
				bool(channel.get('tv_keyword') and channel.get('season')),
				bool(channel.get('movie_keyword') and channel.get('season')),
			))
			progress_state['candidate_count'] += len(candidates)
			playable, probes_before = [], progress_state.get('probed', 0)
			for program in candidates:
				if monitor and monitor.abortRequested():
					save_partial()
					return False
				if player and player.isPlayingVideo():
					save_partial()
					return False
				if _check_program_source(program, channel, progress_state):
					playable.append(program)
				if len(playable) >= 3 or progress_state.get('probed', 0) - probes_before >= MAX_GUIDE_SOURCE_PROBES_PER_CHANNEL:
					break
			programs[channel_id] = playable
			completed.add(channel_id)
			_channel_logo(channel)
			save_partial()
			if monitor and monitor.waitForAbort(0.05):
				return False
		except Exception as exc:
			kodi_utils.logger('TV Guide Preload', 'channel=%s failed=%s' % (channel_id, str(exc)))
			save_partial()
			return False
	if any(programs.values()):
		save_partial(complete=True)
	else:
		# Leave an incomplete empty snapshot so a manual open can retry with its
		# normal progress indicator instead of treating an empty boot result as warm.
		main_cache.set(cache_key, {
			'schema': SNAPSHOT_SCHEMA,
			'channels': channels,
			'favorites': favourites,
			'programs': {},
			'completed_channels': [],
			'complete': False,
			'updated_at': int(time()),
			'refresh_after': int(time()) + SNAPSHOT_RETRY_DELAY,
		}, expiration=SNAPSHOT_RETRY_DELAY / 3600.0)
	elapsed = perf_counter() - started
	kodi_utils.logger(
		'TV Guide Preload Profile',
		'snapshot=cold channels=%d rows=%d candidates=%d source_cache_hits=%d source_probes=%d '
		'catalog_s=%.3f source_s=%.3f total_s=%.3f' % (
			len(channels), sum(bool(programs.get(channel['id'])) for channel in channels),
			progress_state['candidate_count'], progress_state['source_cache_hits'],
			progress_state['source_probes'], progress_state['catalog_seconds'],
			progress_state['source_check_seconds'], elapsed,
		),
	)
	return True


def main(params=None):
	load_started = perf_counter()
	rss_before = _process_rss_mb()
	handle = int(sys.argv[1])
	day_offset = _guide_day_offset(params or {})
	start_time = (datetime.now() + timedelta(days=day_offset)).replace(second=0, microsecond=0)
	config_started = perf_counter()
	channels = _channels(start_time)
	channel_config_seconds = perf_counter() - config_started
	favourites_started = perf_counter()
	favourites = _get_kodi_favourites() if any(channel['id'] == 'favorites' for channel in channels) else []
	favourites_load_seconds = perf_counter() - favourites_started
	fanart_started = perf_counter()
	fanart = kodi_utils.get_addon_fanart()
	fanart_seconds = perf_counter() - fanart_started
	# A previously-selected sort mode can otherwise reorder the schedule using
	# the program titles. The guide is a fixed numbered channel lineup.
	kodi_utils.set_sort_method(handle, 'none')
	progress_state = _new_progress_state(len(channels) * 4)
	try:
		cache_enabled, cache_key, cached_programs = False, None, None
		completed_channels, complete_snapshot = set(), False
		try:
			from caches.main_cache import main_cache
			cache_key_started = perf_counter()
			cache_key = _guide_snapshot_cache_key(channels, favourites)
			progress_state['snapshot_key_seconds'] = perf_counter() - cache_key_started
			cache_started = perf_counter()
			snapshot = main_cache.get(cache_key)
			progress_state['snapshot_read_seconds'] = perf_counter() - cache_started
			cached_programs = snapshot.get('programs') if isinstance(snapshot, dict) and snapshot.get('schema') == SNAPSHOT_SCHEMA else None
			completed_channels = set(snapshot.get('completed_channels') or ()) if isinstance(snapshot, dict) else set()
			complete_snapshot = bool(isinstance(snapshot, dict) and snapshot.get('complete'))
			cache_enabled = True
			kodi_utils.set_property(SNAPSHOT_KEY_PROPERTY, cache_key)
		except Exception as exc:
			kodi_utils.logger('TV Guide', 'Snapshot cache unavailable; building a fresh guide: %s' % str(exc))
		progress_state['snapshot_hit'] = bool(complete_snapshot and isinstance(cached_programs, dict))
		updated_programs = {}
		for channel in channels:
			try:
				prevalidated = None
				if isinstance(cached_programs, dict):
					if progress_state['snapshot_hit'] or channel['id'] in completed_channels:
						prevalidated = cached_programs.get(channel['id'], [])
				programs = _channel_item(handle, channel, start_time, fanart, progress_state, prevalidated, favourites, day_offset)
				if programs:
					updated_programs[channel['id']] = programs
			except Exception as exc:
				kodi_utils.logger('TV Guide', 'Channel %s could not be rendered: %s' % (channel.get('id', 'unknown'), str(exc)))
		if cache_enabled and not progress_state['snapshot_hit'] and updated_programs:
			now = int(time())
			main_cache.set(cache_key, {
				'schema': SNAPSHOT_SCHEMA,
				'channels': channels,
				'favorites': favourites,
				'programs': updated_programs,
				'completed_channels': [channel['id'] for channel in channels],
				'complete': True,
				'updated_at': now,
				'refresh_after': now + SNAPSHOT_INITIAL_REFRESH_DELAY,
			}, expiration=SNAPSHOT_CACHE_HOURS)
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
		elapsed = perf_counter() - load_started
		rss_after = _process_rss_mb()
		kodi_utils.logger(
			'TV Guide Profile',
			'snapshot=%s channels=%d rows=%d candidates=%d feed_lookups=%d source_cache_hits=%d '
			'source_probes=%d config_s=%.3f favorites_s=%.3f fanart_s=%.3f catalog_s=%.3f '
			'source_s=%.3f logo_refs_s=%.3f items_s=%.3f cache_key_s=%.3f cache_read_s=%.3f '
			'total_s=%.3f kodi_process_rss_before_mb=%s kodi_process_rss_after_mb=%s' % (
				'warm' if progress_state.get('snapshot_hit') else 'cold',
				len(channels), progress_state['rows_added'], progress_state['candidate_count'],
				progress_state['catalog_feed_lookups'], progress_state['source_cache_hits'],
				progress_state['source_probes'], channel_config_seconds, favourites_load_seconds,
				fanart_seconds, progress_state['catalog_seconds'], progress_state['source_check_seconds'],
				progress_state['logo_reference_seconds'], progress_state['item_build_seconds'],
				progress_state.get('snapshot_key_seconds', 0.0),
				progress_state.get('snapshot_read_seconds', 0.0), elapsed,
				'unknown' if rss_before is None else rss_before,
				'unknown' if rss_after is None else rss_after,
			),
		)
	if kodi_utils.current_skin() == 'skin.pirate':
		# Complete view setup before this plugin invocation can be reused.
		_set_guide_view()


def _set_guide_view():
	# Wait until Kodi has opened this plugin folder, then select the guide layout.
	if _set_view_for_mode('tvguide.main', 58):
		# Remember that view 58 is guide-only. Internal episode/season updates
		# stay in this window, so the plugin consumes this marker after browsing.
		kodi_utils.set_property('fenlight.tvguide_view_active', 'true')
		kodi_utils.execute_builtin('SetProperty(PirateTVGuideView,1,Home)')


def _set_catalog_view():
	# Counterpart channel sublists use the skin's regular detail list.
	return _set_view_for_mode('tvguide.channel', 51)


def _set_view_for_mode(mode, view_id):
	from xbmc import Monitor
	from urllib.parse import parse_qs, urlparse
	monitor = Monitor()
	seen_target = False
	ready_checks = 0
	def at_target():
		return (kodi_utils.get_visibility('Window.IsActive(Videos)')
			and parse_qs(urlparse(kodi_utils.folder_path()).query).get('mode') == [mode])
	for unused in range(80):
		if monitor.abortRequested(): return False
		current = at_target()
		if seen_target and not current: return False
		seen_target = seen_target or current
		try:
			item_count = int(kodi_utils.get_infolabel('Container.NumItems') or '0')
		except (TypeError, ValueError):
			item_count = 0
		if current and item_count > 0 and not kodi_utils.get_visibility('Container.IsUpdating'):
			ready_checks += 1
			if ready_checks >= 2:
				kodi_utils.execute_builtin('Container.SetViewMode(%s)' % view_id)
				if monitor.waitForAbort(0.3) or not at_target(): return False
				if not kodi_utils.get_visibility('Control.IsVisible(%s)' % view_id):
					kodi_utils.execute_builtin('Container.SetViewMode(%s)' % view_id)
				return True
		else:
			ready_checks = 0
		if monitor.waitForAbort(0.1): return False
	return False


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
		# Complete view setup before this plugin invocation can be reused.
		_set_catalog_view()


def _scheduled_program_for_channel(channel_id, day_offset=0):
	"""Resolve the selected channel's on-now item from its validated snapshot."""
	day_offset = _guide_day_offset({'day_offset': day_offset})
	start_time = (datetime.now() + timedelta(days=day_offset)).replace(second=0, microsecond=0)
	channels = _channels(start_time)
	channel = next((item for item in channels if item.get('id') == channel_id), None)
	if not channel:
		return None
	favourites = _get_kodi_favourites() if any(item.get('id') == 'favorites' for item in channels) else []
	programs = []
	try:
		from caches.main_cache import main_cache
		cache_key = _guide_snapshot_cache_key(channels, favourites)
		snapshot = main_cache.get(cache_key)
		if isinstance(snapshot, dict) and snapshot.get('schema') == SNAPSHOT_SCHEMA:
			cached = snapshot.get('programs')
			if isinstance(cached, dict):
				programs = cached.get(channel_id) or []
	except Exception as exc:
		kodi_utils.logger('TV Guide', 'Playback snapshot unavailable: %s' % str(exc))

	if not programs:
		progress_state = _new_progress_state(MAX_GUIDE_SOURCE_PROBES_PER_CHANNEL, show_progress=False)
		candidates = _channel_programs(channel, favourites)
		for program in candidates:
			if _check_program_source(program, channel, progress_state):
				programs.append(program)
			if (len(programs) >= 3
					or progress_state.get('probed', 0) >= MAX_GUIDE_SOURCE_PROBES_PER_CHANNEL):
				break
	if not programs:
		return None

	schedule = _schedule_for_time(programs, channel, start_time, count=1)
	if not schedule:
		return None
	program = dict(schedule[0]['program'])
	if day_offset == 0:
		elapsed = int(max((start_time - schedule[0]['start']).total_seconds(), 0))
		if elapsed:
			program['_guide_join_seconds'] = elapsed
	return program

def _clear_guide_playback_logo():
	"""Clear the playback badge, including under lightweight Kodi test doubles."""
	clear_property = getattr(kodi_utils, 'clear_property', None)
	if callable(clear_property):
		clear_property('TVGuidePlaybackLogo')
	else:
		kodi_utils.set_property('TVGuidePlaybackLogo', '')


def play_channel(params):
	"""Play the current program: a random aired episode for shows, or the movie."""
	channel_id = str(params.get('channel') or '')
	channel = next((item for item in _channels() if item.get('id') == channel_id), None)
	if channel:
		try:
			kodi_utils.set_property('TVGuidePlaybackLogo', _channel_logo(channel))
		except Exception:
			_clear_guide_playback_logo()
	else:
		_clear_guide_playback_logo()
	favorite_index = params.get('favorite_index', '')
	if str(favorite_index).isdigit():
		_clear_guide_playback_logo()
		return play_favorite({'index': str(favorite_index)})
	tmdb_id = params.get('tmdb_id', '')
	media_type = params.get('media_type', 'tvshow')
	episode_params = dict(params)
	program = None
	guide_join_seconds = 0
	if not str(tmdb_id).isdigit():
		program = _scheduled_program_for_channel(
			params.get('channel', ''), params.get('day_offset', 0),
		)
		if program and str(program.get('favorite_index', '')).isdigit():
			_clear_guide_playback_logo()
			return play_favorite({'index': str(program['favorite_index'])})
		if program:
			tmdb_id = program.get('tmdb_id', '')
			media_type = program.get('media_type', media_type)
			try: guide_join_seconds = max(int(program.get('_guide_join_seconds', 0)), 0)
			except (TypeError, ValueError): guide_join_seconds = 0
			if media_type == 'tvshow':
				if not str(episode_params.get('season', '')).isdigit():
					episode_params['season'] = program.get('_guide_season')
				if not str(episode_params.get('episode', '')).isdigit():
					episode_params['episode'] = program.get('_guide_episode')
		if not str(tmdb_id).isdigit():
			_clear_guide_playback_logo()
			return kodi_utils.notification('No playable program is available in this channel.', 4000)
	try:
		from modules import metadata, settings
		from modules.utils import get_datetime
		if media_type == 'movie':
			meta = metadata.movie_meta('tmdb_id', tmdb_id, settings.tmdb_api_key(), settings.mpaa_region(), get_datetime())
			if not meta or meta.get('blank_entry'):
				_clear_guide_playback_logo()
				return kodi_utils.notification('Could not load the selected movie.', 4000)
			from modules.sources import Sources
			playback_key = settings.playback_key()
			playback_params = {'media_type': 'movie', 'tmdb_id': str(tmdb_id), playback_key: playback_key}
			if guide_join_seconds: playback_params['tv_guide_join_seconds'] = guide_join_seconds
			return Sources().playback_prep(playback_params)
		meta = metadata.tvshow_meta('tmdb_id', tmdb_id, settings.tmdb_api_key(), settings.mpaa_region(), get_datetime())
		if not meta or meta.get('blank_entry'):
			_clear_guide_playback_logo()
			return kodi_utils.notification('Could not load the selected series.', 4000)
		season, episode = episode_params.get('season'), episode_params.get('episode')
		if str(season or '').isdigit() and str(episode or '').isdigit():
			from modules.sources import Sources
			playback_key = settings.playback_key()
			playback_params = {
				'media_type': 'episode', 'tmdb_id': str(tmdb_id), 'season': int(season),
				'episode': int(episode), 'autoplay': 'true', playback_key: playback_key,
			}
			if guide_join_seconds: playback_params['tv_guide_join_seconds'] = guide_join_seconds
			return Sources().playback_prep(playback_params)
		from modules.episode_tools import EpisodeTools
		return EpisodeTools(meta).play_random()
	except Exception:
		_clear_guide_playback_logo()
		message = 'Could not play the selected movie.' if media_type == 'movie' else 'Could not play a random episode from this series.'
		return kodi_utils.notification(message, 4000)


def _channel_entries(channel):
	entries = []
	has_shows = bool(
		channel.get('tv_network_id') or channel.get('tv_candidate_titles')
		or (channel.get('season') and channel.get('tv_keyword'))
	)
	has_movies = bool(
		channel.get('movie_candidate_titles')
		or (channel.get('season') and channel.get('movie_keyword'))
	)
	if has_shows:
		entries.append((
			'%s TV Shows' % channel['name'],
			{'mode': 'tvguide.channel_programs', 'channel': channel['id'], 'media_type': 'tvshow'},
			channel['icon'],
		))
	if has_movies:
		entries.append((
			'%s Movies' % channel['name'],
			{'mode': 'tvguide.channel_programs', 'channel': channel['id'], 'media_type': 'movie'},
			channel['icon'],
		))
	return entries


def channel_programs(params):
	handle = int(sys.argv[1])
	channel_id = params.get('channel', '')
	media_type = params.get('media_type', '')
	channel = next((item for item in _channels() if item['id'] == channel_id), None)
	if not channel or media_type not in ('tvshow', 'movie'):
		return kodi_utils.end_directory(handle, cacheToDisc=False)
	progress_state = _new_progress_state(4, show_progress=False)
	error_state = {}
	candidates = _channel_programs(channel, [], error_state)
	items = []
	for program in candidates:
		if program.get('media_type') != media_type:
			continue
		if _check_program_source(program, channel, progress_state):
			items.append(program)
	for program in items:
		item = kodi_utils.make_listitem()
		item.setLabel(program['title'])
		item.setArt({'icon': program['thumb'], 'thumb': program['thumb'], 'poster': program['thumb'], 'fanart': program['fanart']})
		info = item.getVideoInfoTag(True)
		info.setTitle(program['title'])
		info.setPlot(program['plot'])
		info.setMediaType(program['media_type'])
		item.setProperty('IsPlayable', 'true')
		url_params = {
			'mode': 'tvguide.play_channel',
			'channel': channel_id,
			'tmdb_id': program['tmdb_id'],
			'media_type': media_type,
		}
		if program.get('_guide_season') is not None and program.get('_guide_episode') is not None:
			url_params.update({'season': program['_guide_season'], 'episode': program['_guide_episode']})
		kodi_utils.add_item(handle, kodi_utils.build_url(url_params), item, False)
	kodi_utils.set_content(handle, 'videos')
	kodi_utils.set_category(handle, params.get('name') or '%s %s' % (channel['name'], 'TV Shows' if media_type == 'tvshow' else 'Movies'))
	kodi_utils.end_directory(handle, cacheToDisc=False)

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

