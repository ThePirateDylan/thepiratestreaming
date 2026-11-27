"""Apply the Pirate skin's navigation and first-use sound defaults."""

import json

import xbmc
import xbmcgui


def _rpc(method, **params):
    response = json.loads(xbmc.executeJSONRPC(json.dumps({
        'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params,
    })))
    if 'error' in response:
        raise RuntimeError('%s: %s' % (method, response['error']))
    return response['result']


def _set_setting(setting, value):
    if _rpc('Settings.GetSettingValue', setting=setting)['value'] == value:
        return
    if not _rpc('Settings.SetSettingValue', setting=setting, value=value):
        raise RuntimeError('Kodi did not accept setting %s' % setting)
    if _rpc('Settings.GetSettingValue', setting=setting)['value'] != value:
        raise RuntimeError('Kodi did not retain setting %s' % setting)


def apply_defaults():
    if xbmc.getSkinDir() != 'skin.pirate':
        return
    home = xbmcgui.Window(10000)
    if home.getProperty('PirateSkinDefaultsApplied') == '1':
        return
    try:
        # This is Kodi's native ".." item, not an add-on or remote Back action.
        # Apply once per session so upgrades also cover profiles that skipped
        # the original first-run wizard.
        _set_setting('filelists.showparentdiritems', False)
        if not xbmc.getCondVisibility('Skin.HasSetting(PirateSoundsConfigured)'):
            addon_id = 'resource.uisounds.pirate'
            details = _rpc('Addons.GetAddonDetails', addonid=addon_id,
                           properties=['enabled'])['addon']
            if not details['enabled']:
                _rpc('Addons.SetAddonEnabled', addonid=addon_id, enabled=True)
            mode = _rpc('Settings.GetSettingValue',
                        setting='audiooutput.guisoundmode')['value']
            if mode == 0:
                _set_setting('audiooutput.guisoundmode', 1)
            _set_setting('lookandfeel.soundskin', addon_id)
            # Only mark success after Kodi accepts the sound pack. A missing
            # dependency or failed setting can retry on the next Home load.
            xbmc.executebuiltin('Skin.SetBool(PirateSoundsConfigured)', True)
        home.setProperty('PirateSkinDefaultsApplied', '1')
        xbmc.log('The Pirate: navigation and sound defaults applied', xbmc.LOGINFO)
    except Exception as error:
        xbmc.log('The Pirate: unable to apply skin defaults: %s' % error,
                 xbmc.LOGWARNING)
