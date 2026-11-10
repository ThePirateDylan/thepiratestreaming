"""Temporary diagnostic. Never inspect frame locals, arguments or URLs."""
import threading
import itertools
import os
import time
import traceback
from uuid import uuid4

_session = uuid4().hex[:8]
_sequence = itertools.count(1)

def event(name, stack=False):
    try:
        import xbmc
        # INFO is intentional: DEBUG-only markers were absent in crash logs.
        # No frame locals, source lines, thread names, URLs or media metadata.
        message = '[PirateGuideTrace:v2] session=%s seq=%s mono=%.6f native=%s %s' % (
            _session, next(_sequence), time.monotonic(), threading.get_native_id(), name)
        if stack:
            frames = traceback.extract_stack(limit=10)[:-1]
            message += ' stack=' + ' > '.join('%s:%s:%s' % (
                os.path.basename(f.filename), f.lineno, f.name) for f in frames)
        xbmc.log(message, xbmc.LOGINFO)
    except Exception:
        pass  # Diagnostics must not interrupt callbacks or teardown.

def window_unloaded():
    # This notification runs in the service interpreter. Do not retain frames
    # from other Kodi invocations while those interpreters can be destroyed.
    event('guide-unload received')

event('instrumentation loaded')
