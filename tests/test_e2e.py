"""End-to-end: drive the real interactive flow against a local HTTP server (needs ffmpeg)."""
import contextlib
import functools
import os
import http.server
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from yt_essential import cli, config, gallery


@unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg not installed')
class EndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.web = cls.tmp / 'web'
        cls.web.mkdir()
        subprocess.run(
            ['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=size=320x240:rate=25:duration=6',
             '-f', 'lavfi', '-i', 'sine=frequency=440:duration=6', '-c:v', 'libx264', '-c:a', 'aac',
             '-shortest', '-movflags', '+faststart', '-y', str(cls.web / 'clip.mp4')], check=True)
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(cls.web))
        handler.log_message = lambda *a, **k: None
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f'http://127.0.0.1:{cls.server.server_address[1]}/clip.mp4'

    def setUp(self):
        # ffmpeg ignores NO_PROXY; make sure it can reach 127.0.0.1 directly
        env = {k: v for k, v in os.environ.items() if 'proxy' not in k.lower()}
        p = mock.patch.dict(os.environ, env, clear=True)
        p.start()
        self.addCleanup(p.stop)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_flow(self, answers, name):
        out = self.tmp / name
        cfg = dict(config.DEFAULTS, download_dir=str(out), ask_dir_each_time=False)
        with mock.patch('builtins.input', side_effect=answers), contextlib.redirect_stdout(open('/dev/null', 'w')):
            code = cli.run_download(cfg, self.url)
        return code, out

    def test_video_whole(self):
        code, out = self.run_flow(['1', '1', '1'], 'v')     # video, mp4, whole
        self.assertEqual(code, 0)
        self.assertEqual(len(list((out / 'video').glob('*.mp4'))), 1)
        self.assertFalse((out / 'audio').exists())

    def test_audio_mp3(self):
        code, out = self.run_flow(['2', '1', '1'], 'a')  # audio, mp3, best  (no fragment question for audio)
        self.assertEqual(code, 0)
        self.assertEqual(len(list((out / 'audio').glob('*.mp3'))), 1)

    def test_fragment(self):
        code, out = self.run_flow(['1', '1', '2', '0:01-0:03'], 'f')  # video, mp4, fragment
        self.assertEqual(code, 0)
        f = next((out / 'video').glob('*.mp4'))
        self.assertIn('[1-3s]', f.name)
        dur = float(subprocess.check_output(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(f)]))
        self.assertAlmostEqual(dur, 2.0, delta=0.6)

    def test_bad_url_message(self):
        with mock.patch('builtins.input', side_effect=['not a link']), contextlib.redirect_stdout(open('/dev/null', 'w')):
            self.assertEqual(cli.run_download(dict(config.DEFAULTS)), 1)

    def test_new_folder_is_saved_as_default(self):
        custom = self.tmp / 'custom'
        cfg = dict(config.DEFAULTS, download_dir=str(self.tmp / 'ignored'), ask_dir_each_time=True)
        with mock.patch('builtins.input', side_effect=['1', '1', '1', '2', str(custom)]), \
                mock.patch('yt_essential.cli.config.save') as save, \
                contextlib.redirect_stdout(open('/dev/null', 'w')):
            self.assertEqual(cli.run_download(cfg, self.url), 0)
        self.assertEqual(len(list((custom / 'video').glob('*.mp4'))), 1)
        self.assertEqual(cfg['download_dir'], str(custom))        # the menu will now show it
        save.assert_called()

    def test_keep_current_folder(self):
        cur = self.tmp / 'current'
        cfg = dict(config.DEFAULTS, download_dir=str(cur), ask_dir_each_time=True)
        with mock.patch('builtins.input', side_effect=['1', '1', '1', '1']), \
                contextlib.redirect_stdout(open('/dev/null', 'w')):
            self.assertEqual(cli.run_download(cfg, self.url), 0)
        self.assertEqual(len(list((cur / 'video').glob('*.mp4'))), 1)


@unittest.skipUnless(shutil.which('ffmpeg') and gallery.available(), 'needs ffmpeg and gallery-dl')
class GalleryFallback(unittest.TestCase):
    """A direct image link is unsupported by yt-dlp, so the gallery-dl path handles it."""

    def test_image_goes_to_gallery_subfolder(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        web = tmp / 'web'
        web.mkdir()
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=size=64x64:duration=1',
                        '-frames:v', '1', '-y', str(web / 'pic.jpg')], check=True)
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(web))
        handler.log_message = lambda *a, **k: None
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        url = f'http://127.0.0.1:{server.server_address[1]}/pic.jpg'
        env = {k: v for k, v in os.environ.items() if 'proxy' not in k.lower()}
        cfg = dict(config.DEFAULTS, download_dir=str(tmp / 'out'), ask_dir_each_time=False)
        with mock.patch.dict(os.environ, env, clear=True), mock.patch('builtins.input', side_effect=[]), \
                contextlib.redirect_stdout(open('/dev/null', 'w')):
            code = cli.run_download(cfg, url)
        self.assertEqual(code, 0)
        files = list((tmp / 'out' / 'gallery').rglob('*.jpg'))
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].parent, tmp / 'out' / 'gallery')     # flat: no site/author folders
        self.assertFalse((tmp / 'out' / 'video').exists())


if __name__ == '__main__':
    unittest.main()
