import json
import os
import tempfile
import time
import unittest
from unittest import mock

from yt_essential import updates


class Versions(unittest.TestCase):
    def test_compare(self):
        self.assertTrue(updates.is_newer('2026.10.15', '2026.08.19'))
        self.assertFalse(updates.is_newer('2026.08.19', '2026.08.19'))
        self.assertFalse(updates.is_newer('2026.08.19', '2026.10.15'))
        self.assertTrue(updates.is_newer('2026.08.19.123456', '2026.08.19'))
        self.assertFalse(updates.is_newer('', '2026.08.19'))


class SelfUpdate(unittest.TestCase):
    def test_reads_version_from_github_file(self):
        self.assertEqual(updates.parse_self_version("__version__ = '1.2.0'\nREPO = 'a/b'"), '1.2.0')
        self.assertIsNone(updates.parse_self_version('nothing here'))

    def test_self_is_first_package(self):
        self.assertEqual(updates.PACKAGES[0][0], 'yt-dlp-essential')
        self.assertIn('/archive/refs/heads/main.zip', updates.PACKAGES[0][1])


class Latest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        p = mock.patch.dict(os.environ, {'YTES_CONFIG_DIR': self.tmp})
        p.start()
        self.addCleanup(p.stop)

    def test_fetch_then_cache(self):
        with mock.patch.object(updates, 'fetch_latest', return_value='2030.01.01') as f:
            self.assertEqual(updates.latest_version('yt-dlp'), '2030.01.01')
            self.assertEqual(updates.latest_version('yt-dlp'), '2030.01.01')   # served from cache
            self.assertEqual(f.call_count, 1)
            updates.latest_version('gallery-dl')                              # separate cache entry
            self.assertEqual(f.call_count, 2)
            updates.latest_version('yt-dlp', force=True)
            self.assertEqual(f.call_count, 3)

    def test_stale_cache_refetches(self):
        with open(os.path.join(self.tmp, 'update-check.json'), 'w') as fh:
            json.dump({'yt-dlp': {'checked': time.time() - 10 * 3600, 'latest': '2000.01.01'}}, fh)
        with mock.patch.object(updates, 'fetch_latest', return_value='2031.01.01'):
            self.assertEqual(updates.latest_version(), '2031.01.01')

    def test_offline_is_none(self):
        with mock.patch.object(updates, 'fetch_latest', return_value=None):
            self.assertIsNone(updates.latest_version())

    def test_checker_reports_once(self):
        with mock.patch.object(updates, 'latest_version', return_value='2099.01.01'):
            c = updates.UpdateCheck()
            c.current = {'yt-dlp-essential': None, 'yt-dlp': '2026.08.19', 'gallery-dl': '1.0.0'}
            c.run()
        self.assertEqual(c.updates['yt-dlp'], ('2026.08.19', '2099.01.01'))
        self.assertIn('gallery-dl', c.updates)
        self.assertTrue(c.changed())
        self.assertFalse(c.changed())

    def test_checker_up_to_date(self):
        c = updates.UpdateCheck()
        c.current = {'yt-dlp-essential': None, 'yt-dlp': '2026.08.19', 'gallery-dl': None}      # gallery-dl not installed: skipped
        with mock.patch.object(updates, 'latest_version', return_value='2026.08.19'):
            c.run()
        self.assertFalse(c.available)
        self.assertFalse(c.changed())


if __name__ == '__main__':
    unittest.main()
