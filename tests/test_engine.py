import unittest
from pathlib import Path

from yt_essential import cli, formats
from yt_essential.engine import Plan, build_download_opts, needs_cookies, pretty_platform


class Opts(unittest.TestCase):
    def test_video_best(self):
        o = build_download_opts(Plan(outdir=Path('/x')))
        self.assertEqual(o['paths']['home'], '/x/video')
        self.assertEqual(o['format'], 'bv*+ba/b')
        self.assertEqual(o['merge_output_format'], 'mp4')
        self.assertEqual(o['postprocessors'][0], {'key': 'FFmpegVideoRemuxer', 'preferedformat': 'mp4'})
        self.assertTrue(o['noplaylist'])

    def test_video_height(self):
        o = build_download_opts(Plan(outdir=Path('/x'), height=720))
        self.assertIn('height<=720', o['format'])

    def test_containers(self):
        mkv = build_download_opts(Plan(outdir=Path('/x'), container='mkv'))
        self.assertEqual(mkv['merge_output_format'], 'mkv')
        webm = build_download_opts(Plan(outdir=Path('/x'), container='webm'))
        self.assertEqual(webm['merge_output_format'], 'webm')
        self.assertNotIn('FFmpegVideoRemuxer', [p['key'] for p in webm['postprocessors']])

    def test_audio_quality(self):
        o = build_download_opts(Plan(outdir=Path('/x'), kind='audio', audio_fmt='mp3', audio_quality='192'))
        self.assertEqual(o['postprocessors'][0]['preferredquality'], '192')
        o = build_download_opts(Plan(outdir=Path('/x'), kind='audio', audio_fmt='m4a'))
        self.assertNotIn('preferredquality', o['postprocessors'][0])      # best: keep the source stream
        o = build_download_opts(Plan(outdir=Path('/x'), kind='audio', audio_fmt='mp3'))
        self.assertEqual(o['postprocessors'][0]['preferredquality'], '0')

    def test_audio(self):
        o = build_download_opts(Plan(outdir=Path('/x'), kind='audio', audio_fmt='m4a'))
        self.assertEqual(o['paths']['home'], '/x/audio')
        self.assertEqual(o['postprocessors'][0]['preferredcodec'], 'm4a')

    def test_playlist(self):
        o = build_download_opts(Plan(outdir=Path('/x'), is_playlist=True, items='1,3-5'))
        self.assertEqual(o['playlist_items'], '1,3-5')
        self.assertFalse(o['noplaylist'])
        self.assertIn('playlist_index', o['outtmpl']['default'])

    def test_fragment(self):
        o = build_download_opts(Plan(outdir=Path('/x'), fragment=(10, 20)))
        self.assertTrue(o['force_keyframes_at_cuts'])
        self.assertIn('[10-20s]', o['outtmpl']['default'])
        ranges = list(o['download_ranges']({'id': 'a', 'duration': 100}, None))
        self.assertEqual(ranges, [{'start_time': 10, 'end_time': 20}])


class Detection(unittest.TestCase):
    def test_cookie_hints(self):
        self.assertTrue(needs_cookies("Sign in to confirm you're not a bot. Use --cookies-from-browser"))
        self.assertTrue(needs_cookies('Private video. Sign in if you were granted access'))
        self.assertFalse(needs_cookies('HTTP Error 404: Not Found'))

    def test_platform(self):
        self.assertEqual(pretty_platform({'extractor': 'youtube:tab'}), 'YouTube')
        self.assertEqual(pretty_platform({'extractor': 'twitter'}), 'X (Twitter)')
        self.assertEqual(pretty_platform({'extractor': 'somesite'}), 'Somesite')

    def test_normalize_url(self):
        self.assertEqual(cli.normalize_url('youtu.be/abc'), 'https://youtu.be/abc')
        self.assertIsNone(cli.normalize_url('hello world'))
        self.assertIsNone(cli.normalize_url('hello'))
        self.assertTrue(cli.video_and_list('https://www.youtube.com/watch?v=a&list=b'))


class Qualities(unittest.TestCase):
    INFO = {'formats': [
        {'vcodec': 'vp09.00', 'acodec': 'none', 'height': 1080, 'ext': 'webm', 'tbr': 3000, 'filesize': 100},
        {'vcodec': 'avc1.64', 'acodec': 'none', 'height': 1080, 'ext': 'mp4', 'tbr': 2000, 'filesize': 90, 'fps': 60},
        {'vcodec': 'avc1.4d', 'acodec': 'none', 'height': 720, 'ext': 'mp4', 'tbr': 1000, 'filesize': 50},
        {'vcodec': 'none', 'acodec': 'mp4a', 'ext': 'm4a', 'filesize': 10},
    ]}

    def test_list(self):
        q = formats.video_qualities(self.INFO)
        self.assertEqual([x.height for x in q], [1080, 720])
        self.assertEqual(q[0].codec, 'h264')          # h264 preferred, like the real selector
        self.assertEqual(q[0].size, 100)              # 90 video + 10 audio
        self.assertIn('60fps', q[0].label())

    def test_audio_only(self):
        self.assertFalse(formats.has_video({'formats': [{'vcodec': 'none', 'acodec': 'mp3'}]}))
        self.assertTrue(formats.has_video({}))


if __name__ == '__main__':
    unittest.main()
