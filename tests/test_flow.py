"""Interactive-flow tests with a faked yt-dlp session (no network)."""
import contextlib
import unittest
from pathlib import Path
from unittest import mock

from yt_dlp.utils import DownloadError

from yt_essential import cli, config

ENTRIES = [{'title': f'Video {i}', 'url': f'https://x/{i}', 'ie_key': 'Youtube', '_type': 'url'} for i in range(1, 9)]
PLAYLIST = {'_type': 'playlist', 'title': 'My list', 'entries': ENTRIES, 'extractor': 'youtube:tab',
            'extractor_key': 'YoutubeTab', 'webpage_url': 'https://www.youtube.com/playlist?list=PL1'}


def run(answers, probe_results, cfg=None, download=None):
    cfg = cfg or dict(config.DEFAULTS, download_dir='/tmp/ytes-test-unused')
    calls = []

    def fake_download(self, url, plan, on_file=None):
        calls.append((url, plan))
        return [Path('/tmp/f.mp4')], []

    probe = mock.Mock(side_effect=probe_results)
    with mock.patch('builtins.input', side_effect=answers), \
            mock.patch('yt_essential.engine.Session.probe', probe), \
            mock.patch('yt_essential.engine.Session.download', download or fake_download), \
            mock.patch('yt_essential.cli.pick_base_dir', return_value=Path('/tmp/base')), \
            contextlib.redirect_stdout(open('/dev/null', 'w')):
        code = cli.run_download(cfg, PLAYLIST['webpage_url'] if 'list' in str(probe_results) else 'https://x.example/v')
    return code, calls, probe


class Playlist(unittest.TestCase):
    def test_pick_items(self):
        # choose "some", items "2, 4-5", quality: best
        code, calls, _ = run(['2', '2, 4-5', '1', '1', '1'], [PLAYLIST])
        self.assertEqual(code, 0)
        url, plan = calls[0]
        self.assertEqual(plan.items, '2,4-5')
        self.assertTrue(plan.is_playlist)
        self.assertEqual(plan.kind, 'video')

    def test_all_audio(self):
        code, calls, _ = run(['1', '2', '1', '1'], [PLAYLIST])
        self.assertEqual(code, 0)
        self.assertIsNone(calls[0][1].items)
        self.assertEqual(calls[0][1].kind, 'audio')

    def test_bad_items_reprompts(self):
        code, calls, _ = run(['2', '99', '0', '3-1', '1,2', '1', '1', '3'], [PLAYLIST])  # mp4, 720p
        self.assertEqual(calls[0][1].items, '1,2')
        self.assertEqual(calls[0][1].height, 720)
        self.assertEqual(calls[0][1].container, 'mp4')

    def test_channel_sections(self):
        channel = {'_type': 'playlist', 'title': 'Chan', 'extractor': 'youtube:tab', 'extractor_key': 'YoutubeTab',
                   'entries': [{'_type': 'url', 'ie_key': 'YoutubeTab', 'title': 'Chan - Videos', 'url': 'https://c/videos'},
                               {'_type': 'url', 'ie_key': 'YoutubeTab', 'title': 'Chan - Shorts', 'url': 'https://c/shorts'}]}
        videos = dict(PLAYLIST, title='Chan - Videos', webpage_url='https://c/videos')
        code, calls, _ = run(['1', '1', '1', '1', '1'], [channel, videos])   # section 1, everything, best
        self.assertEqual(calls[0][0], 'https://c/videos')


class Cookies(unittest.TestCase):
    def test_offer_and_retry(self):
        single = {'title': 'T', 'extractor': 'youtube', 'duration': 10,
                  'formats': [{'vcodec': 'avc1', 'acodec': 'none', 'height': 720, 'ext': 'mp4'}],
                  'webpage_url': 'https://x.example/v'}
        err = DownloadError("ERROR: [youtube] abc: Sign in to confirm you're not a bot")
        cfg = dict(config.DEFAULTS)
        with mock.patch('yt_essential.cli.config.save'), \
                mock.patch('yt_essential.cli.installed_browsers', return_value=['chrome', 'safari']):
            # yes offer, browser #1, then kind video, quality best, whole
            code, calls, probe = run(['y', '1', '1', '1', '1', '1'], [err, single], cfg=cfg)
        self.assertEqual(code, 0)
        self.assertEqual(cfg['cookies_browser'], 'chrome')
        self.assertEqual(probe.call_count, 2)

    def test_decline(self):
        err = DownloadError('ERROR: Private video. Sign in if you have been granted access')
        with mock.patch('yt_essential.cli.config.save'):
            code, calls, _ = run(['n'], [err])
        self.assertEqual(code, 1)
        self.assertEqual(calls, [])

    def test_unsupported(self):
        code, calls, _ = run([], [DownloadError('ERROR: Unsupported URL: https://x.example/v')])
        self.assertEqual(code, 1)


if __name__ == '__main__':
    unittest.main()
