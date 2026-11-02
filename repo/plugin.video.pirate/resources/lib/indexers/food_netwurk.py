"""Channel 136's repeating Eastern dayparts and episode-level cable schedule."""
import calendar
import hashlib
import json
import os
from datetime import date, datetime, timedelta
from functools import lru_cache

# Selected shows use TMDb IDs. Hours refer to the New York broadcast day.
PRIMARY = ('2370','11294','40290','57755','2178','34549','129500','44470')
BLOCKS = (
    (6, 12, ('4086','17404','62595','4360','34549')),
    (12, 17, ('35358','44470','57022','4086','57755')),
    (17, 20, ('40290','129500','17404','4360','62595')),
    (20, 23, ('2370','11294','2178','44470','79679')),
    (23, 30, ('2370','11294','40290','44470','35358','4086')),
)
LABELS = {6:'morning',12:'afternoon',17:'evening',20:'primetime',23:'overnight'}

@lru_cache(maxsize=1)
def catalog():
    with open(os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'food_netwurk.json'), encoding='utf-8') as stream:
        return json.load(stream)

def seed(*parts):
    return int.from_bytes(hashlib.sha256('|'.join(map(str, parts)).encode()).digest()[:8], 'big')

def boundary(day, hour):
    # All boundaries are outside the ambiguous 1–2 AM transition hour.
    wall = datetime.combine(day, datetime.min.time()) + timedelta(hours=hour)
    yr = wall.year
    march = date(yr, 3, 8)
    november = date(yr, 11, 1)
    start = march + timedelta(days=(6 - march.weekday()) % 7)
    end = november + timedelta(days=(6 - november.weekday()) % 7)
    summer = datetime.combine(start, datetime.min.time()) + timedelta(hours=2) <= wall < datetime.combine(end, datetime.min.time()) + timedelta(hours=2)
    return calendar.timegm(wall.timetuple()) + (4 if summer else 5) * 3600

def episode(show, index):
    season, number, name, runtime = show['episodes'][index % len(show['episodes'])]
    return dict(show, episodes=None, title=show['title'] + ' - ' + name,
                _guide_season=season, _guide_episode=number, duration_minutes=runtime)

def _build_day(day, scores):
    shows = {s['tmdb_id']: s for s in catalog()}
    cursor, limit = boundary(day,6), boundary(day,30)
    used, counts = {}, {}
    primary_seconds = 0
    previous = None
    day_seed = day.toordinal()
    slots = []
    # Adjust the target gradually, with a neutral 70% starting share.
    def rating(k):
        good, bad = scores.get(k, (0,0))
        return (good + 4) / (good + bad + 8)
    a = sum(rating(k) for k in PRIMARY) / len(PRIMARY)
    b = sum(rating(k) for k in shows if k not in PRIMARY) / (len(shows)-len(PRIMARY))
    target = min(.82,max(.57,.70 + .45*(a-b)))
    while cursor < limit:
        lo, hi, pool = next(block for block in BLOCKS if cursor < boundary(day,block[1]))
        remaining = limit-cursor
        candidates = []
        for k in pool:
            show = shows[k]
            index = day_seed*5 + counts.get(k,0)
            # Pick an episode that fits before the end of this broadcast day.
            for step in range(len(show['episodes'])):
                pick = (index+step) % len(show['episodes'])
                minutes = max(1, show['episodes'][pick][3])
                length = 1800 * ((minutes+29)//30)
                if length <= remaining:
                    candidates.append((k,pick,length))
                    break
        if not candidates:
            # An unusually short final gap belongs to the previous slot.
            slots[-1][1] = limit
            break
        elapsed = cursor-boundary(day,6)
        prefer_a = primary_seconds < (elapsed+1800)*target
        def rank(entry):
            k = entry[0]
            variety = seed(day_seed,cursor,k) % 1000 / 1000
            # Weekends can run consecutive episodes of the same show.
            repeat = .15 if day.weekday() >= 5 else 1.5
            return (int((k in PRIMARY)==prefer_a),
                    rating(k)*2 + variety - used.get((lo,k),0)*.85 - repeat*(previous==k))
        k,pick,length = max(candidates,key=rank)
        slots.append([cursor,cursor+length,k,pick,lo])
        primary_seconds += length*(k in PRIMARY)
        used[(lo,k)] = used.get((lo,k),0)+1
        counts[k] = counts.get(k,0)+1
        cursor += length
        previous = k
    return slots

def schedule(now, count, overrides=None):
    from caches.main_cache import main_cache
    stamp = now.timestamp()
    day = datetime.utcfromtimestamp(stamp).date()
    if stamp < boundary(day,6):
        day -= timedelta(days=1)
    shows = {s['tmdb_id']:s for s in catalog()}
    result = []
    while len(result) < count:
        key = 'food136_published_v2_' + day.isoformat()
        slots = main_cache.get(key)
        if not slots:
            slots = _build_day(day, main_cache.get('food136_show_scores_v2') or {})
            main_cache.set(key, slots, expiration=24*90)
        for cursor,end,k,pick,lo in slots:
            if end <= stamp:continue
            program = episode(shows[k],pick)
            program.update(_food_slot=cursor,_food_block=lo,_food_pick=pick)
            if overrides:
                saved = overrides(cursor)
                if saved:program.update(saved)
            result.append(dict(program=program,start=datetime.fromtimestamp(cursor),
                               end=datetime.fromtimestamp(end),duration_minutes=(end-cursor)//60,daypart=LABELS[lo]))
            if len(result)==count:return result
        day += timedelta(days=1)

def slot_key(stamp):
    return 'food136_airing_v2_%s' % stamp

def alternatives(program):
    shows = {s['tmdb_id']: s for s in catalog()}
    pool = next((p for lo, hi, p in BLOCKS if lo == program.get('_food_block')), (program['tmdb_id'],))
    pick = program['_food_pick']
    yield program
    yield episode(shows[program['tmdb_id']], pick + 1)
    for offset in range(1,len(pool)):
        other = pool[(pool.index(program['tmdb_id']) + offset) % len(pool)]
        yield episode(shows[other], pick + offset)

def tune(program, logo):
    from caches.main_cache import main_cache
    from modules import settings, kodi_utils
    from indexers.tv_guide_player import GuidePlayer, GuideSources
    from indexers.tv_guide import _source_check_cache_key
    class FoodSources(GuideSources):
        unavailable = False
        def _process_post_results(self):
            return self._no_results()
        def _no_results(self):
            self.unavailable = True
            self._kill_progress_dialog()
        def playback_failed_action(self):
            self.unavailable = True
            self._kill_progress_dialog()
    class FoodPlayer(GuidePlayer):
        def playback_started(self):
            # Called only after Kodi reports started video with a valid duration.
            remember(True)
            if program.get('_food_slot') is not None:
                main_cache.set(slot_key(program['_food_slot']), {k:candidate[k] for k in
                    ('title','plot','thumb','fanart','tmdb_id','_guide_season','_guide_episode')}, expiration=24)
    def remember(success):
        scores = main_cache.get('food136_show_scores_v2') or {}
        good, bad = scores.get(candidate['tmdb_id'], (0,0))
        scores[candidate['tmdb_id']] = (good*.95 + int(success), bad*.95 + int(not success))
        main_cache.set('food136_show_scores_v2', scores, expiration=24*30)
        main_cache.set(key, 'played' if success else 'miss', expiration=24*7 if success else 6)
    seen = set()
    options = list(alternatives(program))
    def status_key(c):
        return "%s_food136_v2_%s_%s" % (_source_check_cache_key(c), c["_guide_season"], c["_guide_episode"])
    options[1:] = sorted(options[1:], key=lambda c: main_cache.get(status_key(c)) != "played")
    for candidate in options:
        if kodi_utils.kodi_monitor().abortRequested():return
        season, number = candidate['_guide_season'], candidate['_guide_episode']
        key = status_key(candidate)
        if key in seen or main_cache.get(key) == 'miss':continue
        seen.add(key)
        params = dict(media_type='episode', tmdb_id=candidate['tmdb_id'], season=season, episode=number,
                      autoplay='true', tv_guide_channel_logo=logo, tv_guide_join_seconds=program.get('_guide_join_seconds',0))
        playback_key = settings.playback_key()
        params[playback_key] = playback_key
        sources = FoodSources()
        sources.player_class = FoodPlayer
        sources.playback_prep(params)
        if not sources.unavailable:return
        remember(False)
    kodi_utils.notification('Food Netwurk: no playable episode found in this programming block.', 4000)
