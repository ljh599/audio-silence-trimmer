import unittest

from app.audio_processor import intervals_to_keep


class IntervalTests(unittest.TestCase):
    def test_keeps_padding_around_middle_silence(self):
        self.assertEqual(intervals_to_keep([(2, 5)], 10, 0.1), [(0, 2.1), (4.9, 10)])

    def test_handles_silence_at_both_edges(self):
        self.assertEqual(intervals_to_keep([(0, 2), (8, 10)], 10, 0.1), [(1.9, 8.1)])

    def test_short_silence_is_not_removed_when_padding_overlaps(self):
        self.assertEqual(intervals_to_keep([(2, 2.1)], 5, 0.1), [(0, 5)])

    def test_merges_overlapping_intervals(self):
        self.assertEqual(intervals_to_keep([(1, 3), (2.5, 4)], 5, 0), [(0, 1), (4, 5)])


if __name__ == "__main__":
    unittest.main()
