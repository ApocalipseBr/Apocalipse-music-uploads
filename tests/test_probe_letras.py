import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location(
    "probe_letras", Path(__file__).resolve().parents[1] / "tools/probe_letras.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class ProbeTests(unittest.TestCase):
    def test_nested_paragraphs_and_breaks_keep_bounded_preview(self):
        parser = probe.PagePreview()
        parser.feed('<title>Sample - Artist</title><div class="lyric-original">'
                    '<p>one two<br/>three four<br>five six</p>'
                    '<p>seven eight nine ten eleven twelve</p></div>'
                    '<p>outside content</p>')
        self.assertEqual(parser.lyric_word_count, 12)
        self.assertEqual(parser.preview, 'one two three four five six seven eight nine ten'.split())
        self.assertEqual(parser.title, 'Sample - Artist')

    def test_filename_qualifiers_and_collaborators(self):
        result = probe.identity(Path('Artist ft. Guest - Song (Remix).ogg'))
        self.assertEqual(result['title'], 'Song')
        self.assertEqual(result['qualifiers'], ['Remix'])
        self.assertTrue(result['needs_artist_review'])

    def test_only_letras_https_urls(self):
        probe.validate_url('https://www.letras.mus.br/artist/song/')
        for url in ('https://example.com/', 'http://www.letras.mus.br/',
                    'https://www.letras.mus.br.evil.example/'):
            with self.assertRaises(ValueError):
                probe.validate_url(url)


if __name__ == '__main__':
    unittest.main()
