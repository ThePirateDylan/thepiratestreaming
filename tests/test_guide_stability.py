"""Offline regression tests for the guide's cross-interpreter and skin lifecycle."""
import importlib.util
import multiprocessing
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / 'repo/plugin.video.pirate/resources/lib'


def load(name):
    spec = importlib.util.spec_from_file_location(name, LIB / 'indexers' / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def setup_kodi(profile):
    props = {}
    return types.SimpleNamespace(addon_profile=lambda: profile, addon_path=lambda: str(LIB.parent.parent),
        get_visibility=lambda condition: False, set_property=props.__setitem__, clear_property=lambda key: props.pop(key, None),
        get_property=lambda key: props.get(key, ''), logger=Mock(), current_skin=lambda: 'estuary')


def contender(profile, queue):
    with patch.dict(sys.modules, {'modules': types.SimpleNamespace(kodi_utils=setup_kodi(profile))}):
        with load('tv_guide_guard').operation('tune') as db:
            queue.put(db is not None)


class StabilityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.kodi = setup_kodi(tmp.name)
        patcher = patch.dict(sys.modules, {'modules': types.SimpleNamespace(kodi_utils=self.kodi)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.guard = load('tv_guide_guard')
        sys.modules['indexers.tv_guide_guard'] = self.guard
        self.guide = load('tv_guide')

    def test_independent_interpreter_cannot_tune_while_resolving(self):
        queue = multiprocessing.Queue()
        with self.guard.tuning_request() as acquired:
            self.assertTrue(acquired)
            process = multiprocessing.Process(target=contender, args=(self.kodi.addon_profile(), queue))
            process.start()
            process.join(10)
            self.assertEqual(process.exitcode, 0)
            self.assertFalse(queue.get(timeout=1))
            self.guard.playback_started()
            with self.guard.tuning_request() as next_channel:
                self.assertTrue(next_channel)
        self.assertFalse(self.kodi.get_property('fenlight.tvguide_tuning'))
        queue.close()

    def test_tune_error_releases_slot_for_next_selection(self):
        with patch.object(self.guide, '_play_channel', side_effect=ValueError):
            with self.assertRaises(ValueError):
                self.guide.play_channel({})
        with patch.object(self.guide, '_play_channel', return_value='played'):
            self.assertEqual(self.guide.play_channel({}), 'played')

    def test_contention_renders_without_writing_and_cleans_loading_marker(self):
        with self.guard.operation('snapshot'):
            with patch.object(self.guide, '_build_directory') as build:
                self.guide.main({})
                self.assertFalse(build.call_args.args[1])
            with patch.object(self.guide, '_refresh_snapshot_for_key') as refresh:
                self.assertFalse(self.guide.refresh_snapshot_for_key('key'))
                refresh.assert_not_called()
        with patch.object(self.guide, '_build_directory', side_effect=ValueError):
            with self.assertRaises(ValueError):
                self.guide.main({})
        self.assertFalse(self.kodi.get_property('fenlight.tvguide_loading'))

    def test_canceled_directory_does_not_select_view_or_write_snapshot(self):
        from contextlib import ExitStack
        channels = [dict(id=str(i), name='channel') for i in range(2)]
        self.kodi.get_addon_fanart = Mock(return_value='')
        self.kodi.set_sort_method = Mock()
        self.kodi.end_directory = Mock()
        self.kodi.current_skin = lambda: 'skin.pirate'
        cache = types.SimpleNamespace(get=lambda key: None, set=Mock())
        with ExitStack() as stack:
            stack.enter_context(patch.object(sys, 'argv', ['plugin://plugin.video.pirate', '7']))
            stack.enter_context(patch.dict(sys.modules, {'caches.main_cache': types.SimpleNamespace(main_cache=cache)}))
            stack.enter_context(patch.object(self.guide, '_channels', return_value=channels))
            stack.enter_context(patch.object(self.guide, '_guide_snapshot_cache_key', return_value='key'))
            row = stack.enter_context(patch.object(self.guide, '_channel_item', return_value=False))
            view = stack.enter_context(patch.object(self.guide, '_set_guide_view'))
            self.guide.main()
        row.assert_called_once()
        cache.set.assert_not_called()
        view.assert_not_called()
        self.kodi.end_directory.assert_called_once_with(7, cacheToDisc=False, succeeded=False)

    def test_refresh_only_runs_for_idle_guide(self):
        self.kodi.execute_builtin = Mock()
        self.kodi.folder_path = lambda: 'plugin://plugin.video.pirate/?mode=tvguide.main'
        visible = {'Window.IsActive(Videos)'}
        self.kodi.get_visibility = visible.__contains__
        self.assertTrue(self.guide.refresh_visible_guide())
        for blocked in ['Container.IsUpdating','Window.IsModalDialogTopmost']:
            visible.add(blocked)
            self.assertFalse(self.guide.refresh_visible_guide())
            visible.remove(blocked)
        self.kodi.set_property('fenlight.tvguide_tuning','true')
        self.assertFalse(self.guide.refresh_visible_guide())
        self.kodi.clear_property('fenlight.tvguide_tuning')
        self.kodi.folder_path = lambda: 'plugin://another.addon/?mode=tvguide.main'
        self.assertFalse(self.guide.refresh_visible_guide())
        self.kodi.execute_builtin.assert_called_once_with('Container.Refresh')

    def test_resolver_cleanup_releases_owned_dialog_once(self):
        stubs = {'modules.sources': types.SimpleNamespace(Sources=object),
                 'modules.player': types.SimpleNamespace(FenLightPlayer=object)}
        with patch.dict(sys.modules, stubs):
            src = load('tv_guide_player').GuideSources()
            dialog = src.progress_dialog = Mock()
            worker = src.progress_thread = Mock()
            src._kill_progress_dialog()
            src._kill_progress_dialog()
            dialog.close.assert_called_once()
            worker.join.assert_called_once()
            self.assertIsNone(src.progress_dialog)
            self.assertIsNone(src.progress_thread)

    def test_end_and_stop_callbacks_preserve_player_handoff(self):
        class Player:
            def __init__(self):
                self.stops = 0

            def run(self, url, obj):
                self.sources_object = obj
                self.play(url)
                obj(self)

            def play(self, url):
                pass

            def stop(self):
                self.stops += 1

            def clear_playback_properties(self):
                pass

        stubs = {'modules.sources': types.SimpleNamespace(Sources=object),
                 'modules.player': types.SimpleNamespace(FenLightPlayer=Player)}
        with patch.dict(sys.modules, stubs):
            player_class = load('tv_guide_player').GuidePlayer
            for n in range(25):
                player = player_class()
                # A different attempt can emit events before this player starts.
                player.onPlayBackError()
                player.onPlayBackStopped()
                self.assertFalse(player._ended.is_set())
                self.assertFalse(player._failed)
                def finish(p):
                    if n % 2:
                        p.onPlayBackEnded()
                    else:
                        p.onPlayBackStopped()
                    p.stop()
                    p.stop()
                player.run('fixture', finish)
                self.assertEqual(player.stops, 0)
                self.assertFalse(self.kodi.get_property(player.owner_key))
                self.assertIsNone(player.sources_object)
                player.onPlayBackError()
                self.assertFalse(player._failed)
            def handoff(p):
                self.kodi.set_property(p.owner_key, 'new session')
                p.onPlayBackStopped()
                p.stop()
            old = player_class()
            old.run('fixture', handoff)
            self.assertEqual(old.stops, 0)
            self.assertEqual(self.kodi.get_property(old.owner_key), 'new session')

    def test_source_attempt_owns_player_only_after_resolution(self):
        import ast
        import weakref
        from unittest.mock import MagicMock

        filename = LIB / 'modules/sources.py'
        cls = next(n for n in ast.parse(filename.read_text(encoding='utf8')).body
                   if getattr(n, 'name', None) == 'Sources')
        method = next(n for n in cls.body if getattr(n, 'name', None) == 'play_file')
        for succeed in (True, False):
            events, live = [], []
            class Player:
                def __init__(self):
                    events.append('registered')
                    live.append(weakref.ref(self))

                def run(self, url, obj):
                    events.append(url)
                    obj.playback_successful = url == 'last' and succeed

                def stop(self):
                    events.append('stop')

            resolved_while_registered = []
            def resolve(item):
                if any(ref() is not None for ref in live):
                    resolved_while_registered.append(item['name'])
                events.append('resolve:' + item['name'])
                return None if item['name'] == 'miss' else item['name']

            ku = MagicMock()
            ku.kodi_monitor.return_value.abortRequested.return_value = False
            ns = dict(kodi_utils=ku, settings=MagicMock(), FenLightPlayer=Player)
            exec(compile(ast.Module(body=[method], type_ignores=[]), str(filename), 'exec'), ns)
            src = MagicMock()
            src.progress_dialog.iscanceled.return_value = False
            src.background = src.limit_resolve = False
            src.player_class = Player
            src.resolve_sources.side_effect = resolve
            rows = [dict(name=n, display_name=n, scrape_provider='folders', source='local',
                         quality='SD', size_label='', extraInfo='') for n in ('miss','first','last')]
            ns['play_file'](src, rows)
            self.assertEqual(events, ['resolve:miss','resolve:first','registered','first',
                                      'resolve:last','registered','last'] + ([] if succeed else ['stop']))
            self.assertFalse(resolved_while_registered)
            self.assertFalse(any(ref() is not None for ref in live))

    def test_progress_dialog_has_no_native_player_to_release_on_worker(self):
        import ast
        sources = LIB / 'windows/sources.py'
        base = LIB / 'windows/base_window.py'
        ns = dict(xbmcgui=types.SimpleNamespace(WindowXMLDialog=type('Dialog', (),
                      {'__init__': lambda self, *args: None})), kodi_utils=Mock())
        for path, classname in ((base,'BaseDialog'),(sources,'SourcesPlayback')):
            tree = ast.parse(path.read_text(encoding='utf8'))
            node = next(n for n in tree.body if getattr(n, 'name', None) == classname)
            exec(compile(ast.Module(body=[node], type_ignores=[]),str(path),'exec'), ns)
        with patch.object(ns['SourcesPlayback'],'enable_scraper'):
            ns['addon_fanart'] = lambda: ''
            dialog = ns['SourcesPlayback']('sources_playback.xml',meta={})
            self.assertIsNone(dialog.player)
            dialog.clear_modals()
            ns['kodi_utils'].kodi_player.assert_not_called()
            normal = ns['BaseDialog']('other.xml')
            self.assertIs(normal.player, ns['kodi_utils'].kodi_player.return_value)

    def test_skin_uses_same_panel_for_foreground_busy_and_preload(self):
        skin = ROOT / 'repo/skin.pirate/1080i'
        for name in ('DialogBusy','MyVideoNav'):
            xml = ET.parse(skin / (name+'.xml'))
            self.assertIn('PirateGuideLoadingOverlay',[e.text for e in xml.iter('include')])
        view = ET.parse(skin / 'View_58_TVGuide.xml')
        self.assertIsNotNone(view.find("include[@name='PirateGuideLoadingPanel']"))
        overlay = view.find("include[@name='PirateGuideLoadingOverlay']")
        self.assertEqual(len(overlay.findall(".//include[@content='PirateGuideLoadingPanel']")), 2)
        self.assertIn('tvguide.refresh',next(e.text for e in view.iter('onfocus') if 'PirateTVGuideRefresh' in (e.text or '')))

if __name__ == '__main__':
    unittest.main()
