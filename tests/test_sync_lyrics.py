import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "sync_lyrics", Path(__file__).resolve().parents[1] / "tools/sync_lyrics.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class TimingTests(unittest.TestCase):
    def test_lrc_offset_repeated_lines_and_explicit_gap(self):
        cues = sync.lrc_cues('[offset:500]\n[00:01.00][00:10.000]sample words\n[00:03.00]\n', 20)
        self.assertEqual(cues, [
            {'at': 1.5, 'untilTime': 3.5, 'text': 'sample words'},
            {'at': 10.5, 'untilTime': 14.5, 'text': 'sample words'}])

    def test_asr_groups_preserve_word_ends_and_instrumental_gaps(self):
        words = [{'word': 'sample', 'start': 12.3, 'end': 12.8},
                 {'word': 'words', 'start': 12.9, 'end': 13.2},
                 {'word': 'later', 'start': 20, 'end': 20.5}]
        self.assertEqual(sync.word_cues(words, 30), [
            {'at': 12.3, 'untilTime': 13.2, 'text': 'sample words'},
            {'at': 20, 'untilTime': 20.5, 'text': 'later'}])

    def test_invalid_word_times_and_lrc_seconds(self):
        self.assertEqual(sync.word_cues([{'word': 'bad', 'start': 2, 'end': 2}], 10), [])
        with self.assertRaises(ValueError):
            sync.lrc_entries('[00:75]invalid')

    def test_simultaneous_lrc_lines_do_not_discard_text(self):
        self.assertEqual(sync.lrc_cues('[00:01]one\n[00:01]two', 10),
                         [{'at': 1.0, 'untilTime': 5.0, 'text': 'one / two'}])


if __name__ == '__main__':
    unittest.main()
