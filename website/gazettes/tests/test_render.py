from django.test import SimpleTestCase

from gazettes.services import render
from gazettes.tests.factories import LEGALLAYOUT_HTML


class SanitizeTests(SimpleTestCase):
    def test_keeps_structure_and_legallayout_classes(self):
        body = render.sanitize(LEGALLAYOUT_HTML)

        self.assertIn('<h4>NOTIFICATIONS BY GOVERNMENT</h4>', body)
        self.assertIn('<table>', body)
        # The site's stylesheet restyles these classes, so they must survive.
        self.assertIn('class="section"', body)
        self.assertIn('class="header-text"', body)

    def test_drops_the_documents_own_stylesheet(self):
        # legallayout's stylesheet sets `body` rules that would otherwise leak
        # out of the article and restyle the whole page.
        body = render.sanitize(LEGALLAYOUT_HTML)
        self.assertNotIn('<style', body)
        self.assertNotIn('line-height: 1.6', body)

    def test_strips_script_and_event_handlers(self):
        hostile = """
        <html><body>
          <script>alert('xss')</script>
          <p onclick="alert('xss')" onmouseover="steal()">text</p>
          <a href="javascript:alert('xss')">link</a>
          <iframe src="https://evil.example"></iframe>
          <img src="x" onerror="alert('xss')">
          <object data="evil.swf"></object>
          <form action="/evil"><input name="a"></form>
        </body></html>
        """
        body = render.sanitize(hostile)

        self.assertNotIn('script', body.lower())
        self.assertNotIn('onclick', body.lower())
        self.assertNotIn('onmouseover', body.lower())
        self.assertNotIn('onerror', body.lower())
        self.assertNotIn('javascript:', body.lower())
        self.assertNotIn('<iframe', body.lower())
        self.assertNotIn('<object', body.lower())
        self.assertNotIn('<form', body.lower())
        # The readable text is kept even where its wrapper was dropped.
        self.assertIn('text', body)

    def test_strips_inline_styles(self):
        # An inline style can position an element over the site's own chrome.
        body = render.sanitize(
            '<body><p style="position:fixed;top:0;left:0">x</p></body>'
        )
        self.assertNotIn('position:fixed', body)

    def test_keeps_safe_links(self):
        body = render.sanitize(
            '<body><a href="https://example.gov.in/x">source</a></body>'
        )
        self.assertIn('href="https://example.gov.in/x"', body)

    def test_handles_a_bare_fragment(self):
        body = render.sanitize('<p>no body tag</p>')
        self.assertIn('<p>no body tag</p>', body)

    def test_handles_bytes_and_bad_encoding(self):
        self.assertIn('caf', render.sanitize('<p>café</p>'.encode('utf-8')))
        # Undecodable bytes must not raise; the page still has to render.
        render.sanitize(b'<p>\xff\xfe broken</p>')


class ExtractTextTests(SimpleTestCase):
    def test_extracts_readable_text(self):
        text = render.extract_text(LEGALLAYOUT_HTML)
        self.assertIn('inter cadre transfer', text)
        self.assertIn('Land acquisition proceedings', text)

    def test_drops_stylesheet_content(self):
        text = render.extract_text(LEGALLAYOUT_HTML)
        self.assertNotIn('line-height', text)

    def test_separates_blocks_so_words_do_not_merge(self):
        # Without a separator 'one' and 'two' would index as 'onetwo'.
        text = render.extract_text('<body><p>one</p><p>two</p></body>')
        self.assertNotIn('onetwo', text)
        self.assertIn('one', text)
        self.assertIn('two', text)

    def test_collapses_ragged_pdf_whitespace(self):
        text = render.extract_text(
            '<body><p>a   b</p>\n\n\n\n<p>c</p></body>'
        )
        self.assertNotIn('   ', text)
        self.assertNotIn('\n\n\n', text)


class IndexTextTests(SimpleTestCase):
    def test_short_text_is_untouched(self):
        self.assertEqual(render.index_text('hello world', 1000),
                         'hello world')

    def test_truncates_by_encoded_bytes_not_characters(self):
        # Devanagari costs three bytes a character; a character-based limit
        # would let the tsvector blow past Postgres' 1MB ceiling.
        text = 'क' * 1000
        clipped = render.index_text(text, 300)
        self.assertLessEqual(len(clipped.encode('utf-8')), 300)

    def test_does_not_split_a_multibyte_character(self):
        clipped = render.index_text('क' * 100, 10)
        clipped.encode('utf-8').decode('utf-8')  # must not raise

    def test_truncate_text_reports_whether_it_cut(self):
        self.assertEqual(render.truncate_text('abcdef', 3), ('abc', True))
        self.assertEqual(render.truncate_text('abc', 10), ('abc', False))
