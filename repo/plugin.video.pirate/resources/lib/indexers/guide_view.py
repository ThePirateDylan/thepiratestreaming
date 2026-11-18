"""Small, atomically published guide listings prepared by the existing worker."""
import hashlib
import json
from datetime import datetime


def cache_key(snapshot_key, now):
    from indexers.guide_catalog import source_context
    context = json.dumps(source_context(), sort_keys=True, default=str)
    revision = hashlib.sha256(context.encode('utf-8')).hexdigest()[:16]
    return 'guide_view_v1_%s_%s_%s' % (snapshot_key, revision, now.date().isoformat())


def read(cache, key, channels, now):
    view = cache.get(key)
    if not isinstance(view, dict) or view.get('channels') != [c['id'] for c in channels]:
        return None
    if view.get('state') != 'ready':
        return view
    try:
        if not view['starts'] <= now.isoformat() < view['valid_until']:
            return None
        rows = {}
        for channel in channels:
            slots = [dict(slot, start=datetime.fromisoformat(slot['start']),
                          end=datetime.fromisoformat(slot['end']))
                     for slot in view['rows'][channel['id']]]
            if sum(slot['end'] > now for slot in slots) < 3:
                return None
            rows[channel['id']] = slots
        return dict(view, rows=rows)
    except (KeyError, TypeError, ValueError):
        return None


def publish(cache, key, channels, programs, states, now):
    """Read published schedules only; never fetch metadata, scrape or start playback."""
    from indexers.guide_rotation import schedule
    axis = now.replace(minute=(now.minute // 30) * 30, second=0, microsecond=0)
    rows, missing = {}, []
    for channel in channels:
        cid = channel['id']
        slots = schedule(programs.get(cid, []), channel, axis, 9, cache, cache_only=True)
        if sum(slot['end'] > now for slot in slots) < 3:
            missing.append(cid)
            continue
        rows[cid] = [dict(slot, start=slot['start'].isoformat(), end=slot['end'].isoformat())
                     for slot in slots]
    exhausted = any(states.get(cid, {}).get('complete') for cid in missing)
    state = 'ready' if not missing and channels else 'failed' if exhausted else 'loading'
    view = dict(state=state, channels=[c['id'] for c in channels],
                prepared=len(rows), total=len(channels), missing=missing)
    if state == 'ready':
        view.update(rows=rows, starts=max(slots[0]['start'] for slots in rows.values()),
                    valid_until=min(slots[-3]['end'] for slots in rows.values()))
    # Do not publish a partial grid. Until every channel is ready, retain only
    # progress/error information for the loading page.
    cache.set(key, view, expiration=6)
    return view
