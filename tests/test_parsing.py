import unittest

from yt_essential.parsing import (
    ItemsError, RangeError, format_duration, format_size, parse_items, parse_moment, parse_range)


class ParseItems(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(parse_items('1, 3, 5-8', 10), '1,3,5-8')

    def test_dashes_and_spaces(self):
        self.assertEqual(parse_items(' 2 – 4 ; 7 ', 10), '2-4,7')

    def test_single_range_collapses(self):
        self.assertEqual(parse_items('4-4', 10), '4')

    def test_open_range(self):
        self.assertEqual(parse_items('8-', 10), '8-10')

    def test_errors(self):
        for bad in ('', 'a', '5-2', '0', '11', '1-99'):
            with self.assertRaises(ItemsError, msg=bad):
                parse_items(bad, 10)


class ParseRange(unittest.TestCase):
    def test_user_examples(self):
        self.assertEqual(parse_range('00:00-1:00'), (0, 60))
        self.assertEqual(parse_range('0-1:00'), (0, 60))
        self.assertEqual(parse_range('0:00-1'), (0, 60))      # bare number = minutes
        self.assertEqual(parse_range('0:00-1:00'), (0, 60))
        self.assertEqual(parse_range('0-90'), (0, 90))        # no colon anywhere = seconds
        self.assertEqual(parse_range('0-1'), (0, 1))

    def test_more(self):
        self.assertEqual(parse_range(' 0:30 – 1:45 '), (30, 105))
        self.assertEqual(parse_range('1:02:30-1:05:00'), (3750, 3900))
        self.assertEqual(parse_range('2-2.5'), (2, 2.5))
        self.assertEqual(parse_range('1:00-'), (60, None))     # to the end
        self.assertEqual(parse_range('-0:30'), (0, 30))

    def test_clamped_to_duration(self):
        self.assertEqual(parse_range('0:10-9:00', 100), (10, 100))

    def test_errors(self):
        for bad in ('', '5', 'a-b', '1:75-2:00', '2:00-1:00', '1-2-3', '5:00-6:00', '30-1:45'):
            with self.assertRaises(RangeError, msg=bad):
                parse_range(bad, 120 if bad == '5:00-6:00' else None)

    def test_moment(self):
        self.assertEqual(parse_moment('1:30'), 90)
        self.assertEqual(parse_moment('1'), 60)
        self.assertIsNone(parse_moment('x'))


class Formatting(unittest.TestCase):
    def test_duration(self):
        self.assertEqual(format_duration(75), '1:15')
        self.assertEqual(format_duration(0), '0:00')
        self.assertEqual(format_duration(None), '?')
        self.assertEqual(format_duration(3750), '1:02:30')

    def test_size(self):
        self.assertEqual(format_size(2048), '2 KB')
        self.assertEqual(format_size(5 * 1024 ** 2), '5.0 MB')


if __name__ == '__main__':
    unittest.main()
