"""Cached guide programming. No player, GUI, scraping or background workers."""
import hashlib
import json
import math
from datetime import datetime, timedelta
from time import time


def seed(*parts):
    return int(hashlib.sha256('|'.join(map(str, parts)).encode('utf-8')).hexdigest()[:16], 16)


def identity(program):
    return '%s:%s' % (program['media_type'], program['tmdb_id'])


def daypart(hour):
    return 'daytime' if 6 <= hour < 17 else 'prime_time' if 17 <= hour < 23 else 'overnight'


def _minutes(program):
    try:
        minutes = float(program.get('duration_minutes', 0))
        if not 15 <= minutes <= 360:
            raise ValueError()
    except (TypeError, ValueError):
        minutes = 110 if program['media_type'] == 'movie' else 30
    return int(math.ceil(minutes / 30.0)) * 30


def build_day(programs, channel, day, recent=(), scores=None):
    """Half-hour broadcast blocks, with longer slots for longer programs."""
    scores = scores or {}
    pool = list({identity(p): p for p in programs}.values())
    if not pool:
        return []
    cursor = datetime(day.year, day.month, day.day)
    limit = cursor + timedelta(days=1)
    anchors = {}
    if day.weekday() < 5:
        for clock, title in channel.get('weekday_anchors', {}).items():
            match = next((p for p in pool if p.get('_editorial_title', p['title']).casefold() == title.casefold() and (not channel.get('editorial_catalog') or any(e.get('source_status') in ('verified-source', 'playback-verified') for e in p.get('_episodes', [])))), None)
            if channel.get('editorial_catalog'):
                # Daily game-show anchors require an exact verified episode.
                # A verified same-channel alternative may use the slot instead;
                # its real title/episode is published, never the requested label.
                alternatives = [dict(p, _episodes=[e for e in p.get('_episodes', [])
                                if e.get('source_status') in ('verified-source', 'playback-verified')
                                and e.get('duration_minutes', 30) <= 30]) for p in pool]
                alternatives = [p for p in alternatives if p['_episodes']]
                if match:
                    match = next((p for p in alternatives if identity(p)==identity(match)), None)
                if not match and alternatives:
                    match = max(alternatives, key=lambda p: seed(channel['id'],day,clock,identity(p)))
            if match:
                hour, minute = map(int, clock.split(':'))
                anchors[cursor.replace(hour=hour, minute=minute)] = match
    counts, slots, history = {}, [], list(recent)[-50:]
    episode_history = list(recent)
    while cursor < limit:
        block = daypart(cursor.hour)
        deadline = min([t for t in anchors if t > cursor] + [limit])
        remaining = (deadline - cursor).total_seconds() / 60
        anchored = anchors.get(cursor)
        candidates = [p for p in pool if _minutes(p) <= remaining]
        if anchored:
            candidates = [anchored]
        if not candidates:
            # Keep the last broadcast on screen until the next fixed boundary;
            # never start a film that would be cut off by the next program.
            if slots: slots[-1]['end'] = deadline.isoformat()
            cursor = deadline
            continue
        preferred = channel.get('program_blocks', {}).get(block, ())
        def rank(p):
            key = identity(p)
            good, bad = scores.get(key, (0, 0))
            affinity = p['title'] in preferred if preferred else (
                p['media_type'] == ('movie' if block == 'prime_time' else 'tvshow'))
            # Variety wins over source history; success only breaks comparable
            # choices, so a previously playable show cannot monopolize a day.
            return (-counts.get(key, 0), -history[-max(1, min(len(pool)-1, 12)):].count(key),
                    int(affinity), (good + 1) / (good + bad + 2),
                    seed(channel['id'], day, block, cursor.hour, key))
        chosen = max(candidates, key=rank)
        length = min(30 if anchored else _minutes(chosen), remaining)
        end = cursor + timedelta(minutes=length)
        from indexers.guide_catalog import assign_episode
        assigned = assign_episode(chosen, '%s:%s' % (channel['id'],cursor), episode_history)
        slots.append({'program': assigned, 'start': cursor.isoformat(),
                      'end': end.isoformat(), 'daypart': block})
        key = identity(chosen)
        counts[key] = counts.get(key, 0) + 1
        history.append(key)
        cursor = end
    return slots


def schedule(programs, channel, now, count, cache, cache_only=False):
    # Freeze each published day. A metadata refresh or reopening cannot shuffle
    # its slots; only a channel-definition change invalidates that day's plan.
    from indexers.guide_catalog import eligible_pool, source_context, outcome, VERIFIED, assign_episode
    context = source_context() if channel.get('editorial_catalog') else {}
    revision = hashlib.sha256(json.dumps([channel, context], sort_keys=True, default=str).encode()).hexdigest()[:16]
    def key(day):
        return 'guide_day_v3_%s_%s_%s' % (channel['id'], revision, day.isoformat())
    result = []
    day = now.date()
    for _ in range(3):
        slots = cache.get(key(day))
        if not slots:
            if cache_only: return result
            pool = eligible_pool(programs, cache, verified_only=channel.get('require_verified_sources', False)) if channel.get('editorial_catalog') else programs
            if not pool: return result
            previous = [s for days in range(14,0,-1) for s in (cache.get(key(day - timedelta(days=days))) or [])]
            recent = [identity(s['program']) for s in previous]
            recent += ['%s:%s:%s' % (s['program']['tmdb_id'],s['program'].get('_guide_season'),s['program'].get('_guide_episode')) for s in previous]
            played = cache.get('guide_history_v3_' + channel['id']) or []
            recent += [e['episode'] for e in played if e['at'] > time()-14*86400 and e['context']==context]
            scores = cache.get('guide_rotation_scores_v1_' + channel['id']) or {}
            slots = build_day(pool, channel, day, recent, scores)
            # Keep visited past/future days through the supported guide range.
            cache.set(key(day), slots, expiration=24 * 80)
        dirty = False
        for slot in slots:
            start, end = datetime.fromisoformat(slot['start']), datetime.fromisoformat(slot['end'])
            if end <= now: continue
            old = slot['program']
            status = outcome(old, cache) if channel.get('editorial_catalog') else 'unverified'
            old['source_status'] = status
            if channel.get('editorial_catalog') and (status == 'miss' or ((old.get('_hold') or channel.get('require_verified_sources')) and status not in VERIFIED)):
                duration = (datetime.fromisoformat(slot['end'])-datetime.fromisoformat(slot['start'])).total_seconds()/60
                replacements = []
                for candidate in ([] if cache_only else eligible_pool(programs, cache, verified_only=channel.get('require_verified_sources', False))):
                    if candidate.get('_episodes'):
                        candidate = dict(candidate, _episodes=[e for e in candidate['_episodes'] if e.get('source_status') in VERIFIED and e['duration_minutes'] <= duration])
                        if not candidate['_episodes']: continue
                    elif outcome(candidate,cache) not in VERIFIED or _minutes(candidate)>duration: continue
                    replacement = assign_episode(candidate,slot['start'],[])
                    if _minutes(replacement)<=duration: replacements.append(replacement)
                if replacements:
                    slot['program']=max(replacements,key=lambda p:seed(slot['start'],identity(p)))
                    dirty=True
                else:
                    slot['program']=dict(old, _guide_unavailable=True)
            elif old.get('_guide_unavailable'):
                slot['program']={k:v for k,v in old.items() if k!='_guide_unavailable'}
            start, end = datetime.fromisoformat(slot['start']), datetime.fromisoformat(slot['end'])
            if end <= now:
                continue
            item = dict(slot, program=dict(slot['program']), start=start, end=end,
                        duration_minutes=int((end-start).total_seconds() // 60))
            item['program']['_rotation_slot'] = key(day) + '_' + slot['start']
            result.append(item)
            if len(result) >= count:
                if dirty: cache.set(key(day), slots, expiration=24*80)
                return result
        if dirty: cache.set(key(day), slots, expiration=24*80)
        day += timedelta(days=1)
    return result


def choose_episode(episodes, state, slot, now=None):
    """Choose from already-filtered aired episodes; no metadata or source calls."""
    now = time() if now is None else now
    choices = {'%s:%s' % (e['season'], e['episode']): e for e in episodes}
    outcomes = state.get('outcomes', {})
    choices = {key: e for key, e in choices.items()
               if not (outcomes.get(key, {}).get('status') == 'miss'
                       and outcomes[key].get('until', 0) > now)}
    if not choices:
        return None
    if state.get('slot') == slot and state.get('pick') in choices:
        return choices[state['pick']]
    history = state.get('recent', [])
    unused = {key: e for key, e in choices.items() if key not in history}
    pool = unused or choices
    def rank(key):
        last = max((i for i, v in enumerate(history) if v == key), default=-1)
        played = outcomes.get(key, {}).get('status') == 'played'
        return (-last, int(played), seed(slot, key))
    return pool[max(pool, key=rank)]


def episode_params(meta, channel_id, slot):
    """Retain random guide playback, with persisted per-channel episode history."""
    from caches.main_cache import main_cache
    from modules import metadata, settings
    from modules.utils import adjust_premiered_date, get_datetime
    from indexers.tv_guide import _source_check_cache_key
    from indexers.guide_catalog import source_context
    context = hashlib.sha256(json.dumps([str(meta['tmdb_id']), source_context()], sort_keys=True).encode()).hexdigest()
    state_key = 'guide_episode_v1_%s_%s' % (channel_id, context)
    state = main_cache.get(state_key) or {}
    current, offset = get_datetime(), settings.date_offset()
    aired = []
    for episode in metadata.all_episodes_meta(meta) or []:
        premiered = episode.get('premiered')
        if not premiered:
            continue
        date = adjust_premiered_date(premiered, offset)[0]
        if date and date <= current:
            aired.append(episode)
    # Direct catalog tuning has no broadcast slot and intentionally picks afresh.
    slot = slot or str(time())
    chosen = choose_episode(aired, state, slot)
    if not chosen:
        return None
    state.update(slot=slot, pick='%s:%s' % (chosen['season'], chosen['episode']))
    main_cache.set(state_key, state, expiration=24 * 30)
    playback_key = settings.playback_key()
    return {'media_type': 'episode', 'tmdb_id': str(meta['tmdb_id']),
            'season': int(chosen['season']), 'episode': int(chosen['episode']),
            'random': 'true', 'autoplay': 'true', playback_key: playback_key,
            '_guide_history_key': state_key, '_guide_channel': channel_id}


def movie_key(program):
    from indexers.tv_guide import _source_check_cache_key
    return 'guide_movie_outcome_v1_' + _source_check_cache_key(program)


def remember(params, success):
    from caches.main_cache import main_cache
    now = time()
    from indexers.guide_catalog import record
    record(params, 'playback-verified' if success else 'miss', main_cache)
    if params['media_type'] == 'movie':
        main_cache.set(movie_key(params), 'played' if success else 'miss', expiration=168 if success else 1/6)
    state_key = params.get('_guide_history_key')
    if state_key:
        state = main_cache.get(state_key) or {}
        pick = '%s:%s' % (params['season'], params['episode'])
        outcomes = {k: v for k, v in state.get('outcomes', {}).items() if v.get('until', 0) > now}
        outcomes[pick] = {'status': 'played' if success else 'miss', 'until': now + (7*86400 if success else 600)}
        # Bound persisted state on long-running daily series.
        state['outcomes'] = dict(sorted(outcomes.items(), key=lambda x: x[1]['until'])[-200:])
        if success:
            state['recent'] = (state.get('recent', []) + [pick])[-50:]
        else:
            state.pop('pick', None)
        main_cache.set(state_key, state, expiration=24 * 30)
    channel = params.get('_guide_channel')
    if channel and success:
        from indexers.guide_catalog import source_context
        history_key = 'guide_history_v3_' + channel
        history = [e for e in (main_cache.get(history_key) or []) if e['at'] > now-14*86400]
        history.append({'episode': '%s:%s:%s' % (params['tmdb_id'],params.get('season'),params.get('episode')), 'at':now, 'context':source_context()})
        main_cache.set(history_key,history,expiration=24*15)
    if channel:
        score_key = 'guide_rotation_scores_v1_' + channel
        scores = main_cache.get(score_key) or {}
        key = '%s:%s' % ('tvshow' if params['media_type'] == 'episode' else 'movie', params['tmdb_id'])
        good, bad = scores.get(key, (0, 0))
        scores[key] = (good * .95 + int(success), bad * .95 + int(not success))
        main_cache.set(score_key, scores, expiration=24 * 30)
