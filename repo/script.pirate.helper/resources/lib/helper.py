#!/usr/bin/python
# coding: utf8

import xbmc
import xbmcaddon
import xbmcgui              
import xbmcvfs
import os
import re
import simplejson
from urllib.parse import parse_qs, urlparse

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')

INFO = xbmc.LOGINFO
WARNING = xbmc.LOGWARNING
DEBUG = xbmc.LOGDEBUG
LOG_ENABLED = True if ADDON.getSetting('log') == 'true' else False
DEBUGLOG_ENABLED = True if ADDON.getSetting('debuglog') == 'true' else False


def get_kodiversion():
    build = xbmc.getInfoLabel('System.BuildVersion')
    return int(build[:2])

def log(txt,loglevel=INFO,force=False):
    if ((loglevel == INFO or loglevel == WARNING) and LOG_ENABLED) or (loglevel == DEBUG and DEBUGLOG_ENABLED) or force:

        # Python 2 requires to decode stuff at first
        try:
            if isinstance(txt, str):
                txt = txt
        except AttributeError:
            pass

        message = '[ %s ] %s' % (ADDON_ID,txt)

        try:
            xbmc.log(msg=message.encode('utf-8'), level=loglevel) # Python 2
        except TypeError:
            xbmc.log(msg=message, level=loglevel)

def visible(condition):
    return xbmc.getCondVisibility(condition)

def _escape_builtin_parameter(value):
    # Kodi strips unquoted trailing spaces from built-in parameters. Keep the
    # value quoted so the search-space key survives on TV remotes.
    return value.replace('\\', '\\\\').replace('"', '\\"')

def _set_custom_search_term(value):
    if value:
        xbmc.executebuiltin('Skin.SetString(CustomSearchTerm,"%s")' % _escape_builtin_parameter(value), True)
    else:
        xbmc.executebuiltin('Skin.Reset(CustomSearchTerm)', True)
    xbmcgui.Window(10000).setProperty('CustomSearch', '1')

def searchbackspace(params):
    """Update the skin keyboard directly instead of depending on VirtualKeyboard."""
    _set_custom_search_term(xbmc.getInfoLabel('Skin.String(CustomSearchTerm)')[:-1])

def searchspace(params):
    """Update the skin keyboard directly instead of depending on VirtualKeyboard."""
    _set_custom_search_term(xbmc.getInfoLabel('Skin.String(CustomSearchTerm)') + ' ')

def _positive_numeric_id(value):
    value = str(value or '').strip()
    return value if value.isdigit() and int(value) > 0 else ''


def _resolve_moreepisodes_target(params):
    """Resolve the selected show's episode list without reusing a stale container."""
    params = params or {}
    dbtype = str(params.get('dbtype') or params.get('propertydbtype', '')).strip().lower()
    media_type = str(params.get('media_type', '')).strip().lower()
    dbid = _positive_numeric_id(params.get('dbid'))
    tvshowid = _positive_numeric_id(params.get('tvshowid'))
    tmdb_id = _positive_numeric_id(params.get('tmdb_id'))
    show_tmdb_id = _positive_numeric_id(params.get('show_tmdb_id'))
    uniqueid = _positive_numeric_id(params.get('uniqueid'))
    season = str(params.get('season', '')).strip()
    folderpath = str(params.get('folderpath', '')).strip()
    lower_path = folderpath.lower()

    if media_type in ('tv', 'tvshow', 'show', 'series'):
        dbtype = 'tvshow'
    elif media_type == 'episode':
        dbtype = 'episode'
    elif media_type == 'season':
        dbtype = 'season'

    # A TV Guide row points at a schedule entry rather than a browsable show.
    # Reject it instead of guessing from metadata belonging to the current slot.
    if 'mode=tvguide.' in lower_path:
        return ''
    catalog_context = lower_path.startswith('plugin://')

    # An add-on item's own URL identifies its show more reliably than a numeric
    # list-item DBID, which may be a catalog ID rather than a Kodi library ID.
    if lower_path.startswith('plugin://plugin.video.pirate/'):
        path_tmdb = re.search(r'[?&]tmdb_id=(\d+)(?:&|$)', lower_path)
        if path_tmdb:
            tmdb_id = _positive_numeric_id(path_tmdb.group(1)) or tmdb_id
        if 'mode=build_episode_list' in lower_path:
            path_season = re.search(r'[?&]season=(all|\d+)(?:&|$)', lower_path)
            if path_tmdb and path_season:
                return folderpath
        if 'mode=build_season_list' in lower_path and path_tmdb:
            return 'plugin://plugin.video.pirate/?mode=build_episode_list&tmdb_id=%s&season=all' % tmdb_id
        if dbtype == 'season':
            path_season = re.search(r'[?&]season=(\d+)(?:&|$)', lower_path)
            if not season and path_season:
                season = path_season.group(1)
            show_id = tmdb_id or show_tmdb_id or uniqueid
            if show_id and season.isdigit():
                return 'plugin://plugin.video.pirate/?mode=build_episode_list&tmdb_id=%s&season=%s' % (show_id, int(season))
        if dbtype in ('tvshow', 'episode'):
            show_id = tmdb_id or show_tmdb_id or uniqueid
            if show_id:
                return 'plugin://plugin.video.pirate/?mode=build_episode_list&tmdb_id=%s&season=all' % show_id

    # A selected season has its own folder route; preserve it instead of
    # falling through to the blank all-episodes destination.
    if dbtype == 'season':
        if re.match(r'^videodb://tvshows/titles/\d+/(?:\d+|-2)/?$', lower_path):
            return folderpath
        show_id = show_tmdb_id or tmdb_id or uniqueid
        if show_id and season.isdigit():
            return 'plugin://plugin.video.pirate/?mode=build_episode_list&tmdb_id=%s&season=%s' % (show_id, int(season))
        return ''

    if dbtype == 'tvshow':
        show_id = show_tmdb_id or tmdb_id or uniqueid
        if catalog_context and show_id:
            return 'plugin://plugin.video.pirate/?mode=build_episode_list&tmdb_id=%s&season=all' % show_id
        if dbid:
            return 'videodb://tvshows/titles/%s/-2/' % dbid
        if show_id:
            return 'plugin://plugin.video.pirate/?mode=build_episode_list&tmdb_id=%s&season=all' % show_id
    elif dbtype == 'episode':
        show_id = show_tmdb_id or tmdb_id or uniqueid
        if catalog_context and show_id:
            return 'plugin://plugin.video.pirate/?mode=build_episode_list&tmdb_id=%s&season=all' % show_id
        if tvshowid:
            return 'videodb://tvshows/titles/%s/-2/' % tvshowid
        if show_id:
            return 'plugin://plugin.video.pirate/?mode=build_episode_list&tmdb_id=%s&season=all' % show_id

    if lower_path.startswith('videodb://tvshows/titles/'):
        match = re.match(r'^videodb://tvshows/titles/(\d+)/-2/?$', lower_path)
        if match and _positive_numeric_id(match.group(1)):
            return folderpath

    # Accept only a recognized add-on episode list; arbitrary paths can point
    # back to a search or TV Guide container.
    if lower_path.startswith('plugin://plugin.video.pirate/') and 'mode=build_episode_list' in lower_path:
        tmdb_match = re.search(r'[?&]tmdb_id=(\d+)(?:&|$)', lower_path)
        season_match = re.search(r'[?&]season=(all|\d+)(?:&|$)', lower_path)
        if tmdb_match and season_match:
            return folderpath
    return ''


def _same_episode_route(current_path, target):
    """Return True only when Kodi reached the requested show/season episode folder."""
    try:
        current = urlparse(str(current_path or '').strip())
        expected = urlparse(str(target or '').strip())
        if (current.scheme.lower() != expected.scheme.lower()
                or current.netloc.lower() != expected.netloc.lower()
                or current.path.rstrip('/').lower() != expected.path.rstrip('/').lower()):
            return False

        if expected.scheme.lower() == 'plugin' and expected.netloc.lower() == 'plugin.video.pirate':
            current_query = parse_qs(current.query, keep_blank_values=True)
            expected_query = parse_qs(expected.query, keep_blank_values=True)
            for key in ('mode', 'tmdb_id', 'season'):
                expected_values = [value.strip().lower() for value in expected_query.get(key, [])]
                current_values = [value.strip().lower() for value in current_query.get(key, [])]
                if expected_values and current_values != expected_values:
                    return False
            return True

        return current.query.strip().lower() == expected.query.strip().lower()
    except Exception:
        return False


def _wait_for_episode_folder(target, cycles):
    """Wait for a populated, settled destination; stop if the user leaves."""
    folder_path = folder_content = ''
    monitor = xbmc.Monitor()
    seen_target = False
    ready_checks = 0
    for unused in range(cycles):
        if monitor.abortRequested():
            return False, folder_path, folder_content
        folder_path = xbmc.getInfoLabel('Container.FolderPath') or ''
        folder_content = (xbmc.getInfoLabel('Container.Content') or '').strip().lower()
        at_target = (xbmc.getCondVisibility('Window.IsActive(Videos)')
                     and _same_episode_route(folder_path, target))
        if seen_target and not at_target:
            return False, folder_path, folder_content
        seen_target = seen_target or at_target
        try:
            count = int(xbmc.getInfoLabel('Container.NumItems') or '0')
        except (TypeError, ValueError):
            count = 0
        if (at_target and folder_content == 'episodes' and count > 0
                and not xbmc.getCondVisibility('Container.IsUpdating')):
            ready_checks += 1
            if ready_checks >= 2:
                return True, folder_path, folder_content
        else:
            ready_checks = 0
        if monitor.waitForAbort(0.1):
            break
    return False, folder_path, folder_content


def moreepisodes(params):
    """Open a show's selected episode folder and verify Kodi loaded that exact list."""
    params = params or {}
    target = _resolve_moreepisodes_target(params)
    if not target:
        dbtype = str(params.get('dbtype') or params.get('propertydbtype', '')).strip().lower()
        dbid = str(params.get('dbid', '')).strip()
        log('More Episodes: no safe show route found (type=%s, dbid=%s)' % (dbtype, dbid), WARNING, True)
        xbmcgui.Dialog().notification('The Pirate', 'Could not identify this show\'s episode list', 'DefaultIconWarning.png', 5000, False)
        return

    try:
        log('More Episodes: opening %s' % target, DEBUG, True)
        xbmcgui.Window(10000).setProperty('MoreEpisodesLoading', '1')
        # This action can originate in Kodi's info dialog or TMDb helper's custom dialog.
        xbmc.executebuiltin('Dialog.Close(1190,true)', True)
        xbmc.executebuiltin('Dialog.Close(movieinformation,true)', True)
        xbmc.executebuiltin('CancelAlarm(loadinfo,silent)', True)
        xbmc.sleep(350)
        for property_name in ('BaseWindow', 'FadeFanart', 'NoFadeOut', 'AnimationRight', 'EpisodesAnimation', 'CloseInfoDialog'):
            xbmc.executebuiltin('ClearProperty(%s,Home)' % property_name, True)

        escaped_target = _escape_builtin_parameter(target)
        if xbmc.getCondVisibility('Window.IsActive(Videos)'):
            xbmc.executebuiltin('Container.Update("%s",replace)' % escaped_target, True)
        else:
            xbmc.executebuiltin('ActivateWindow(Videos,"%s",return)' % escaped_target, True)
        loaded, folder_path, folder_content = _wait_for_episode_folder(target, 150)

        if not loaded:
            videos_active = xbmc.getCondVisibility('Window.IsActive(Videos)')
            same_folder_loading = (
                videos_active
                and _same_episode_route(folder_path, target)
                and xbmc.getCondVisibility('Container.IsUpdating')
            )
            if same_folder_loading:
                log('More Episodes: target folder is still updating; allowing more time', DEBUG, True)
                loaded, folder_path, folder_content = _wait_for_episode_folder(target, 150)

        if xbmc.Monitor().abortRequested():
            return

        if not loaded:
            log('More Episodes: destination did not load (expected=%s; current=%s; content=%s; videos_active=%s)'
                    % (target, folder_path, folder_content,
                       xbmc.getCondVisibility('Window.IsActive(Videos)')), WARNING, True)
            xbmcgui.Dialog().notification('The Pirate', 'Episode list did not load. Check Kodi log.', 'DefaultIconWarning.png', 6000, False)
            return

        current_view_mode = xbmc.getInfoLabel('Container.Viewmode') or ''
        guide_view_active = (
            xbmc.getCondVisibility('Control.IsVisible(58)')
            or current_view_mode.strip().lower() == 'tv guide'
            or xbmcgui.Window(10000).getProperty('PirateTVGuideView') == '1'
        )
        pirate_skin = xbmc.getSkinDir().strip().lower() == 'skin.pirate'
        if pirate_skin or guide_view_active:
            # A valid episode folder must leave the TV Guide or any stale view
            # and use the skin's episode layout. Do this even if the guide's
            # temporary view marker has already been cleared.
            view_id = 525 if pirate_skin else 50
            xbmc.executebuiltin('Container.SetViewMode(%s)' % view_id, True)
            xbmc.sleep(300)
        if guide_view_active:
            xbmcgui.Window(10000).clearProperty('fenlight.tvguide_view_active')
            xbmc.executebuiltin('ClearProperty(PirateTVGuideView,Home)', True)

        log('More Episodes: loaded Videos folder %s (content=%s)' % (folder_path, folder_content), DEBUG, True)
    except Exception as error:
        log('More Episodes: unable to open episode list: %s' % error, WARNING, True)
        xbmcgui.Dialog().notification('The Pirate', 'Episode list did not load. Check Kodi log.', 'DefaultIconWarning.png', 6000, False)
    finally:
        xbmcgui.Window(10000).clearProperty('MoreEpisodesLoading')

def _resolve_nextpage_target(params):
    """Accept a numeric Next Page URL generated by the Pirate plugin."""
    params = params or {}
    target = str(params.get('folderpath') or params.get('path') or '').strip()
    if not target:
        return None

    try:
        parsed = urlparse(target)
        if parsed.scheme.lower() != 'plugin' or parsed.netloc.lower() != 'plugin.video.pirate':
            return None
        query = parse_qs(parsed.query, keep_blank_values=True)
    except Exception:
        return None

    mode = (query.get('mode') or [''])[0].strip().lower()
    page = (query.get('new_page') or [''])[0].strip()
    if not mode or not page.isdigit() or int(page) < 2:
        return None

    # Keyword search uses a separate navigator route; it needs its query key
    # to distinguish this page from another search at the same page number.
    if mode == 'navigator.keyword_results' and not (query.get('key_id') or [''])[0].strip():
        return None

    # Home widgets can display Next Page entries from several Pirate list
    # indexers. Preserve the route's identifying query parameters while ignoring
    # display-only labels that Kodi may normalize in Container.FolderPath.
    display_parameters = ('category_name', 'name', 'iconImage')
    route_query = dict((key, values) for key, values in query.items() if key not in display_parameters)
    content = {'build_movie_list': 'movies', 'build_tvshow_list': 'tvshows'}.get(mode)
    return target, content, int(page), mode, route_query


def _wait_for_next_page(expected_page, expected_mode, expected_query, expected_content, cycles):
    """Wait until Videos reaches the requested Pirate results page."""
    current_path = ''
    current_content = ''
    for unused in range(cycles):
        if xbmc.getCondVisibility('Window.IsActive(Videos)'):
            current_path = xbmc.getInfoLabel('Container.FolderPath') or ''
            current_content = (xbmc.getInfoLabel('Container.Content') or '').strip().lower()
            try:
                current_query = parse_qs(urlparse(current_path).query, keep_blank_values=True)
                current_page = (current_query.get('new_page') or [''])[0].strip()
                current_mode = (current_query.get('mode') or [''])[0].strip().lower()
                route_matches = all(current_query.get(key, []) == values for key, values in expected_query.items())
            except Exception:
                current_page, current_mode, route_matches = '', '', False
            if (current_page == str(expected_page)
                    and current_mode == expected_mode
                    and route_matches
                    and (expected_content is None or current_content == expected_content)):
                return True, current_path, current_content
        xbmc.sleep(100)
    return False, current_path, current_content


def nextpage(params):
    """Open a Pirate paginated directory and verify that Videos reached that page."""
    route = _resolve_nextpage_target(params)
    if not route:
        target = str((params or {}).get('folderpath') or (params or {}).get('path') or '')
        log('Next Page: rejected invalid Pirate page URL: %s' % target, WARNING, True)
        xbmcgui.Dialog().notification('The Pirate', 'Could not open this results page', 'DefaultIconWarning.png', 5000, False)
        return

    target, expected_content, expected_page, expected_mode, expected_query = route
    window = xbmcgui.Window(10000)
    window.setProperty('PirateNextPageLoading', '1')
    try:
        log('Next Page: opening page %s (%s)' % (expected_page, expected_mode), DEBUG, True)
        escaped_target = _escape_builtin_parameter(target)
        # A Home widget is outside Videos. Open the exact plugin URL as a directory.
        xbmc.executebuiltin('ActivateWindow(Videos,"%s",return)' % escaped_target, True)
        reached_page, current_path, current_content = _wait_for_next_page(
            expected_page, expected_mode, expected_query, expected_content, 100)

        if not reached_page and xbmc.getCondVisibility('Window.IsActive(Videos)') and xbmc.getCondVisibility('Container.IsUpdating'):
            log('Next Page: target is still updating; allowing Kodi more time', DEBUG, True)
            reached_page, current_path, current_content = _wait_for_next_page(
                expected_page, expected_mode, expected_query, expected_content, 150)

        if not reached_page:
            log('Next Page: first handoff missed target; retrying Videos navigation', WARNING, True)
            if xbmc.getCondVisibility('Window.IsActive(Videos)'):
                xbmc.executebuiltin('Container.Update("%s",replace)' % escaped_target, True)
            else:
                xbmc.executebuiltin('ActivateWindow(Videos,"%s",return)' % escaped_target, True)
            reached_page, current_path, current_content = _wait_for_next_page(
                expected_page, expected_mode, expected_query, expected_content, 150)

        if reached_page:
            log('Next Page: Videos reached page %s (%s)' % (expected_page, expected_content or expected_mode), INFO, True)
        else:
            log('Next Page: destination did not load (expected page=%s mode=%s content=%s; current=%s content=%s)'
                    % (expected_page, expected_mode, expected_content, current_path, current_content), WARNING, True)
            xbmcgui.Dialog().notification('The Pirate', 'That results page did not load. Check Kodi log.', 'DefaultIconWarning.png', 6000, False)
    except Exception as error:
        log('Next Page: unable to open results page: %s' % error, WARNING, True)
        xbmcgui.Dialog().notification('The Pirate', 'Could not open this results page', 'DefaultIconWarning.png', 5000, False)
    finally:
        window.clearProperty('PirateNextPageLoading')

def _read_vfs_file(path):
    file_handle = xbmcvfs.File(path, 'r')
    try:
        return file_handle.read()
    finally:
        file_handle.close()

def installpauseosdkeymap(params):
    """Install the skin-owned fullscreen keymap and reload it when it changes."""
    installation_property = 'PiratePauseOSDKeymapInstalled'
    home_window = xbmcgui.Window(10000)
    try:
        source = xbmcvfs.translatePath(os.path.join(ADDON.getAddonInfo('path'), 'resources', 'keymaps', 'script.pirate.helper.pause-osd.xml'))
        keymaps_directory = xbmcvfs.translatePath('special://profile/keymaps/')
        destination = os.path.join(keymaps_directory, 'script.pirate.helper.pause-osd.xml')
        if not xbmcvfs.exists(keymaps_directory):
            xbmcvfs.mkdirs(keymaps_directory)
        if not xbmcvfs.exists(source):
            raise RuntimeError('Bundled pause/OSD keymap is missing')
        if not xbmcvfs.exists(destination) or _read_vfs_file(source) != _read_vfs_file(destination):
            with xbmcvfs.File(destination, 'w') as destination_file:
                destination_file.write(_read_vfs_file(source))
            xbmc.executebuiltin('Action(reloadkeymaps)')
        home_window.setProperty(installation_property, ADDON.getAddonInfo('version'))
    except Exception as error:
        log('Unable to install pause/OSD keymap: %s' % error, WARNING, True)

def get_first_youtube_video(query):
    for media in get_youtube_listing('%s' % query, limit=5):
        if media["filetype"] != "directory":
            return media["file"]
    return ""

def get_youtube_listing(searchquery, limit=None):
    """get items from youtube plugin by query"""
    lib_path = u"plugin://plugin.video.youtube/kodion/search/query/?q=%s&search_type=videos" % searchquery
    files_query = json_call('Files.GetDirectory',
                              params={'directory': lib_path},
                              limit=limit)
    result = []
    if 'result' in files_query:
        for key, value in files_query['result'].items():
            if not key == "limits" and (isinstance(value, list) or isinstance(value, dict)):
                result = value
    return result

def json_call(method,properties=None,sort=None,query_filter=None,limit=None,params=None,item=None):

    json_string = {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': {}}

    if properties is not None:
        json_string['params']['properties'] = properties

    if limit is not None:
        json_string['params']['limits'] = {'start': 0, 'end': limit}

    if sort is not None:
        json_string['params']['sort'] = sort

    if query_filter is not None:
        json_string['params']['filter'] = query_filter

    if item is not None:
        json_string['params']['item'] = item

    if params is not None:
        json_string['params'].update(params)

    json_string = simplejson.dumps(json_string)

    result = xbmc.executeJSONRPC(json_string)

    # Python 2 compatibility
    try:
        result = unicode(result, 'utf-8', errors='ignore')
    except NameError:
        pass

    result = simplejson.loads(result)

    log('json-string: %s' % json_string, DEBUG)
    log('json-result: %s' % result, DEBUG)

    return result

