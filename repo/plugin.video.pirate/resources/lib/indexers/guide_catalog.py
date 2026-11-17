"""Editorial catalog and exact-item eligibility; no GUI or player ownership."""
import hashlib
import json
import re
import unicodedata
from datetime import datetime
from time import time, monotonic
from urllib.parse import quote_plus

# Editions confirmed against the local TMDb search cache, not stream evidence.
TITLE_HINTS = {'Modern Family': ('2009', 'US'), 'The Office (US)': ('2005', 'US'),
               'The Challenge': ('1998', 'US'), 'Jeopardy!': ('1984', 'US')}

VERIFIED = ('verified-source', 'playback-verified')
ALIASES = {"The Paw Patrol Movie": "PAW Patrol: The Movie", "Pokémon: The First Movie": "Pokémon: The First Movie - Mewtwo Strikes Back", "The Wonder Pets!": "Wonder Pets!", "The Great British Bake Off": "The Great British Baking Show"}


def canonical(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(text)).casefold() if c.isalnum())


def specification(title):
    match = re.search(r' \((\d{4}|US|UK)\)$', title)
    qualifier = match.group(1) if match else ''
    name = title[:match.start()] if match else title
    return name, qualifier


def select_match(title, results, movie=False):
    name, qualifier = specification(title)
    hint_year, hint_country = TITLE_HINTS.get(title, ('', ''))
    expected = {canonical(name), canonical(ALIASES.get(name, name))}
    matches = []
    for result in results:
        names = {canonical(result.get(k, '')) for k in ('title', 'name', 'original_title', 'original_name')}
        # TMDb sometimes retains the edition in the display name.
        names.update(canonical(specification(result.get(k, ''))[0]) for k in ('title', 'name'))
        if not expected.intersection(names): continue
        year = str(result.get('release_date' if movie else 'first_air_date', ''))[:4]
        if qualifier.isdigit() and year != qualifier: continue
        if hint_year and year != hint_year: continue
        if hint_country and hint_country not in result.get('origin_country', []): continue
        if qualifier in ('US', 'UK') and ('GB' if qualifier == 'UK' else 'US') not in result.get('origin_country', []): continue
        matches.append(result)
    # A remake/edition ambiguity needs a year, never the first popularity result.
    ids = {str(r['id']) for r in matches if r.get('id')}
    return matches[0] if len(ids) == 1 else None


def source_context():
    from modules import settings
    # Hash account/filter values; never persist tokens, usernames or stream URLs.
    get = getattr(settings, 'get_setting', lambda key, default='': default)
    names = ('rd.token','ad.token','pm.token','tb.token','easynews_user','easynews_password',
             'provider.external','external_scraper.module','filter_audio','results.filter_size_method',
             'results.movie_size_min','results.movie_size_max','results.episode_size_min','results.episode_size_max',
             'results.size_unknown','filter.hevc','filter.hdr','filter.dv','filter.3d','filter.include_prerelease',
             'filter.sort_to_top','filter.preferred_filters','filter.hevc.max_autoplay_quality',
             'filter.hevc.max_quality','easynews.filter_lang','easynews.lang_filters',
             'results.folders_ignore_filters','results.line_speed')
    profile = hashlib.sha256(json.dumps([get('fenlight.'+key,'') for key in names],default=str).encode()).hexdigest()
    # Include the external add-on's enabled-provider settings when available.
    try:
        import os
        from modules import kodi_utils
        folder = settings.external_scraper_info()[0]
        path = kodi_utils.translate_path('special://profile/addon_data/%s/settings.xml' % folder)
        with open(path,'rb') as config: scraper = hashlib.sha256(config.read()).hexdigest()
    except (AttributeError, ImportError, OSError): scraper = ''
    # The playback key is a per-startup invocation guard, not a source setting.
    # Including it here discarded every saved schedule on each Kodi restart.
    return {'profile':profile, 'scraper_settings':scraper, 'providers': sorted(settings.active_internal_scrapers()),
            'episode_quality': settings.quality_filter('autoplay_quality_episode'),
            'movie_quality': settings.quality_filter('%s_quality_movie' % ('autoplay' if settings.auto_play('movie') else 'results'))}


def exact_key(program):
    media = program.get('media_type')
    season = program.get('_guide_season', program.get('season'))
    episode = program.get('_guide_episode', program.get('episode'))
    if media in ('tvshow', 'episode') and (season is None or episode is None):
        return None
    data = {'context': source_context(), 'media': 'movie' if media == 'movie' else 'episode',
            'id': str(program['tmdb_id']), 'season': int(season) if season is not None else None, 'episode': int(episode) if episode is not None else None,
            'release': program.get('_guide_release', '')}
    return 'guide_exact_v2_' + hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def outcome(program, cache, now=None):
    key = exact_key(program)
    record = cache.get(key) if key else None
    if isinstance(record, dict) and record.get('until', 0) > (time() if now is None else now):
        return record['status']
    return 'unverified'


def record(program, status, cache):
    key = exact_key(program)
    if not key: return
    hours = 168 if status == 'playback-verified' else 6 if status == 'verified-source' else 1/6
    cache.set(key, {'status': status, 'at': time(), 'until': time()+hours*3600}, expiration=hours)
    channel=program.get('_guide_channel')
    if channel:
        cache.set('guide_schedule_dirty_'+channel,True,expiration=24)
        from modules import kodi_utils
        kodi_utils.set_property('fenlight.tvguide_prepare_day','0')


def catalog_jobs(channel):
    return [(media, title, held) for media, field, held in
            [('tvshow','tv_candidate_titles',False), ('movie','movie_candidate_titles',False), ('tvshow','hold_candidate_titles',True)]
            for title in channel.get(field, ())]


def candidates(channel, api, make_record, icon, state=None, limit=None, previous=()):
    """One bounded title batch per channel; callers persist the cursor/results."""
    from modules import kodi_utils, metadata, settings
    from modules.utils import get_datetime
    state = {} if state is None else state
    jobs = catalog_jobs(channel)
    cursor = int(state.get('cursor', 0))
    selected = jobs[cursor:cursor+limit] if limit else jobs
    programs = {(p['media_type'],str(p['tmdb_id'])):dict(p) for p in previous}
    state.setdefault('unmatched', [])
    state.setdefault('errors', [])
    for media, title, held in selected:
        if kodi_utils.kodi_monitor().abortRequested(): raise InterruptedError('Guide catalog stopped')
        name, qualifier = specification(title)
        lookup = api.tmdb_movies_search if media == 'movie' else api.tmdb_tv_search
        advance=True
        try:
            response = lookup(quote_plus(name),1)
            if not isinstance(response,dict) or 'results' not in response:
                raise ValueError('metadata_response')
            result = select_match(title,response['results'],media=='movie')
            if not result:
                if title not in state['unmatched']: state['unmatched'].append(title)
                continue
            p = make_record(result,media,icon)
            if not p: raise ValueError('metadata_record')
            p.update(_editorial_title=title,_hold=held,source_status='unverified')
            meta_func = metadata.movie_meta if media=='movie' else metadata.tvshow_meta
            meta=meta_func('tmdb_id',p['tmdb_id'],settings.tmdb_api_key(),settings.mpaa_region(),get_datetime())
            if not meta or meta.get('blank_entry'): raise ValueError('metadata_details')
            p['_guide_mpaa']=meta.get('mpaa') or ''
            p['_guide_release']=str(meta.get('year') or '')
            key=(media,str(p['tmdb_id']))
            if media=='movie':
                p['duration_minutes']=max(1,int((meta.get('duration') or 6600)/60))
            else:
                today = datetime.now().strftime('%Y-%m-%d')
                # Future/announced seasons can be last in TMDb's list. They
                # must not hide the show's already-aired seasons.
                seasons=sorted({int(v['season_number']) for v in meta.get('season_data',[])
                                if int(v.get('season_number',0))>0
                                and v.get('episode_count',1) != 0
                                and (not v.get('air_date') or v['air_date'] <= today)})
                if not seasons: raise ValueError('metadata_seasons')
                # Increment a persisted season cursor on each catalog refresh.
                # Retain earlier episodes so verified seasons are never discarded.
                season_state=state.setdefault('seasons',{})
                index=int(season_state.get(str(p['tmdb_id']),len(seasons)-1))%len(seasons)
                season=seasons[index]
                if kodi_utils.kodi_monitor().abortRequested(): raise InterruptedError('Guide catalog stopped')
                episodes={(e['_guide_season'],e['_guide_episode']):e for e in programs.get(key,{}).get('_episodes',[])}
                for ep in metadata.episodes_meta(season,meta) or []:
                    aired=ep.get('premiered')
                    if not aired or aired>datetime.now().strftime('%Y-%m-%d'):continue
                    e=dict(_guide_season=ep['season'],_guide_episode=ep['episode'],
                           _guide_release='%s:%s:%s' % (meta.get('year',''),aired,ep.get('episode_id','')),
                           duration_minutes=max(1,int((ep.get('duration') or 1800)/60)),
                           episode_title=ep.get('title',''),premiered=aired)
                    episodes[(e['_guide_season'],e['_guide_episode'])]=e
                season_state[str(p['tmdb_id'])]=(index+1)%len(seasons)
                p['_episodes']=list(episodes.values())
                if not episodes: raise ValueError('metadata_aired_episodes')
            programs[key]=p
        except InterruptedError:
            advance=False
            raise
        except Exception as exc:
            state['errors']=(state['errors']+[{'title':title,'type':type(exc).__name__}])[-25:]
            kodi_utils.logger('TV Guide catalog','channel=%s title=%s error=%s' % (channel['id'],title,type(exc).__name__))
        finally:
            if advance: state['cursor']=min(len(jobs),int(state.get('cursor',0))+1)
    state['total']=len(jobs)
    state['complete']=state['cursor']>=len(jobs)
    return list(programs.values())


def eligible_pool(programs, cache, verified_only=False):
    result = []
    for p in programs:
        p = dict(p)
        if p['media_type']=='movie':
            state = outcome(p,cache)
            if state=='miss' or ((p.get('_hold') or verified_only) and state not in VERIFIED): continue
            p['source_status']=state
        else:
            episodes = []
            for ep in p.get('_episodes',[]):
                state = outcome(dict(p,**ep),cache)
                if state=='miss' or ((p.get('_hold') or verified_only) and state not in VERIFIED): continue
                episodes.append(dict(ep,source_status=state))
            if p.get('_episodes') is not None:
                if not episodes: continue
                p['_episodes']=episodes
                p['duration_minutes']=max(ep['duration_minutes'] for ep in episodes)
            elif p.get('_hold') or verified_only: continue
        result.append(p)
    return result


def assign_episode(program, slot, recent):
    if not program.get('_episodes'): return dict(program)
    from indexers.guide_rotation import seed
    def identity(e): return '%s:%s:%s' % (program['tmdb_id'], e['_guide_season'],e['_guide_episode'])
    pool=program['_episodes']
    positions,counts={},{}
    for i,key in enumerate(recent):
        positions[key]=i
        counts[key]=counts.get(key,0)+1
    def rank(e):
        key=identity(e)
        last=positions.get(key,-1)
        return (int(last==-1), -last, -counts.get(key,0),int(e.get('source_status') in VERIFIED),seed(slot,key))
    ep=max(pool,key=rank)
    recent.append(identity(ep))
    p={k:v for k,v in program.items() if k!='_episodes'}
    p.update(ep)
    p['title'] = '%s — S%s E%s%s' % (program['title'],ep['_guide_season'],ep['_guide_episode'], ' · '+ep['episode_title'] if ep.get('episode_title') else '')
    return p
