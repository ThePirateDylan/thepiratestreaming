#!/usr/bin/python
# coding: utf8

import xbmc
import xbmcaddon
import xbmcgui              
import xbmcvfs
import os
import simplejson

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
    return value.replace('\\', '\\\\').replace(',', '\\,').replace(')', '\\)')

def _set_custom_search_term(value):
    if value:
        xbmc.executebuiltin('Skin.SetString(CustomSearchTerm,%s)' % _escape_builtin_parameter(value))
    else:
        xbmc.executebuiltin('Skin.Reset(CustomSearchTerm)')
    xbmcgui.Window(10000).setProperty('CustomSearch', '1')

def searchbackspace(params):
    """Update the skin keyboard directly instead of depending on VirtualKeyboard."""
    _set_custom_search_term(xbmc.getInfoLabel('Skin.String(CustomSearchTerm)')[:-1])

def searchspace(params):
    """Update the skin keyboard directly instead of depending on VirtualKeyboard."""
    _set_custom_search_term(xbmc.getInfoLabel('Skin.String(CustomSearchTerm)') + ' ')

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

