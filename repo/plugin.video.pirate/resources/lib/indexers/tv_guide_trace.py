"""Temporary diagnostic. Never inspect frame locals, arguments or URLs."""
import threading

def event(name):
    try:
        import xbmc
        xbmc.log('[PirateGuideTrace] %s ident=%s native=%s' %
                 (name, threading.get_ident(), threading.get_native_id()), xbmc.LOGDEBUG)
    except Exception:
        pass  # Diagnostics must not interrupt callbacks or teardown.

def window_unloaded():
    # This notification runs in the service interpreter. Do not retain frames
    # from other Kodi invocations while those interpreters can be destroyed.
    event('guide-unload received')
