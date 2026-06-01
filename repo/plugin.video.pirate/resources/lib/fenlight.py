# -*- coding: utf-8 -*-
import sys
from modules.router import routing, sys_exit_check
# from modules.kodi_utils import logger

def init_settings():
    settings_cache['fenlight.playback_key'] = jsonrpc_get_system_setting('fenlight.playback_key', '8029')

routing(sys)
if sys_exit_check(): sys.exit(1)

