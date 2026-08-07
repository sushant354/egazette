import shutil
import tempfile

from django.test import TestCase

from gazettes.models import Gazette
from gazettes.services.ingest import IngestService
from gazettes.services.search import (
    HL_START,
    HL_STOP,
    SearchCriteria,
    SearchService,
    archive_stats,
    render_highlight,
)
from gazettes.services.storage import AssetStorage
from gazettes.tests.factories import write_gazette


def gazette_xml(day, month, year, subject, ministry='Ministry of Railways'):
    return """<?xml version="1.0" encoding="utf-8"?>
<document>
<date><day>%d</day><month>%d</month><year>%d</year></date>
<ministry>%s</ministry>
<subject>%s</subject>
</document>""" % (day, month, year, ministry, subject)


def page_html(body):
    return '<html><body>%s</body></html>' % body


class SearchTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.datadir = tempfile.mkdtemp()
        storage = AssetStorage(roots=[cls.datadir], write_root=cls.datadir)
        service = IngestService(storage=storage)

        write_gazette(
            cls.datadir, 'central_extraordinary/2024-04-18/1',
            metatags=gazette_xml(18, 4, 2024, 'Land acquisition for railways'),
            html=page_html(
                '<p>Acquisition of land in Dawanpur village for the railway '
                'project under the Railways Amendment Act.</p>'
            ),
        )
        write_gazette(
            cls.datadir, 'central_extraordinary/2023-01-05/2',
            metatags=gazette_xml(5, 1, 2023, 'Inter cadre transfer of officer',
                                 'Ministry of Personnel'),
            html=page_html(
                '<p>Notification of the inter cadre transfer of an officer '
                'to the Andhra Pradesh cadre.</p>'
            ),
        )
        write_gazette(
            cls.datadir, 'andhra/2022-06-10/3',
            metatags=gazette_xml(10, 6, 2022, 'Municipal upgradation'),
            html=page_html('<p>Upgradation of the municipal corporation.</p>'),
        )

        for relurl in ('central_extraordinary/2024-04-18/1',
                       'central_extraordinary/2023-01-05/2',
                       'andhra/2022-06-10/3'):
            result = service.ingest(relurl)
            assert result.ok, result.reason

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.datadir, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.service = SearchService()


class QueryTests(SearchTestCase):
    def test_finds_words_in_the_body_text(self):
        results = self.service.search(SearchCriteria(q='Dawanpur'))
        self.assertEqual([g.relurl for g in results],
                         ['central_extraordinary/2024-04-18/1'])

    def test_finds_words_in_the_metadata(self):
        results = self.service.search(SearchCriteria(q='Personnel'))
        self.assertEqual([g.relurl for g in results],
                         ['central_extraordinary/2023-01-05/2'])

    def test_stemming_matches_word_forms(self):
        # 'acquisition' should reach 'Acquisition of land'.
        results = self.service.search(SearchCriteria(q='acquisitions'))
        self.assertTrue(results.exists())

    def test_phrase_search(self):
        exact = self.service.search(SearchCriteria(q='"inter cadre transfer"'))
        self.assertEqual(exact.count(), 1)

        # The same words out of order should not match as a phrase.
        scrambled = self.service.search(SearchCriteria(q='"transfer cadre inter"'))
        self.assertEqual(scrambled.count(), 0)

    def test_or_and_exclusion(self):
        either = self.service.search(SearchCriteria(q='railway OR municipal'))
        self.assertEqual(either.count(), 2)

        excluded = self.service.search(
            SearchCriteria(q='notification -cadre')
        )
        self.assertNotIn('central_extraordinary/2023-01-05/2',
                         [g.relurl for g in excluded])

    def test_no_query_returns_everything_newest_first(self):
        results = list(self.service.search(SearchCriteria()))
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].relurl, 'central_extraordinary/2024-04-18/1')

    def test_nonsense_query_returns_nothing(self):
        self.assertEqual(
            self.service.search(SearchCriteria(q='zzzzqqqxyzzy')).count(), 0
        )


class FilterTests(SearchTestCase):
    def test_filter_by_source(self):
        results = self.service.search(SearchCriteria(sources=['andhra']))
        self.assertEqual([g.relurl for g in results], ['andhra/2022-06-10/3'])

    def test_filter_by_date_range(self):
        results = self.service.search(SearchCriteria(
            from_date='2023-01-01', to_date='2023-12-31'
        ))
        self.assertEqual([g.relurl for g in results],
                         ['central_extraordinary/2023-01-05/2'])

    def test_filter_by_year(self):
        self.assertEqual(
            self.service.search(SearchCriteria(year=2022)).count(), 1
        )

    def test_filters_combine_with_a_query(self):
        results = self.service.search(
            SearchCriteria(q='notification', sources=['central_extraordinary'])
        )
        for gazette in results:
            self.assertEqual(gazette.source.name, 'central_extraordinary')

    def test_ordering(self):
        oldest = list(self.service.search(SearchCriteria(order='oldest')))
        self.assertEqual(oldest[0].relurl, 'andhra/2022-06-10/3')

        newest = list(self.service.search(SearchCriteria(order='newest')))
        self.assertEqual(newest[0].relurl, 'central_extraordinary/2024-04-18/1')


class HeadlineTests(SearchTestCase):
    def test_marks_the_matching_words(self):
        criteria = SearchCriteria(q='Dawanpur')
        results = list(self.service.search(criteria))
        headlines = self.service.headlines(results, criteria)

        headline = headlines[results[0].pk]
        self.assertIn('<mark>', headline)
        self.assertIn('Dawanpur', headline)

    def test_no_headlines_without_a_query(self):
        self.assertEqual(self.service.headlines([], SearchCriteria()), {})

    def test_headline_escapes_markup_in_the_gazette_text(self):
        # ts_headline does not escape the document it highlights, so gazette
        # text containing markup must not reach the page as live HTML.
        datadir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, datadir, ignore_errors=True)

        storage = AssetStorage(roots=[datadir], write_root=datadir)
        write_gazette(
            datadir, 'andhra/2021-01-01/9',
            metatags=gazette_xml(1, 1, 2021, 'Hostile subject'),
            html=page_html(
                '<p>The notice reads &lt;script&gt;alert("xss")&lt;/script&gt; '
                'and concerns peculiarword in the district.</p>'
            ),
        )
        result = IngestService(storage=storage).ingest('andhra/2021-01-01/9')
        self.assertTrue(result.ok, result.reason)

        # The literal tag survived extraction, which is what makes the
        # escaping below load-bearing.
        gazette = Gazette.objects.get(relurl='andhra/2021-01-01/9')
        self.assertIn('<script>', gazette.text)

        criteria = SearchCriteria(q='peculiarword')
        results = list(self.service.search(criteria))
        headline = self.service.headlines(results, criteria)[results[0].pk]

        self.assertNotIn('<script>', headline)
        self.assertIn('<mark>peculiarword</mark>', headline)


class RenderHighlightTests(TestCase):
    """The escaping step ts_headline's output goes through before display."""

    def test_escapes_markup_but_keeps_the_marks(self):
        raw = '%sfound%s in <b>bold</b> & <script>alert(1)</script>' % (
            HL_START, HL_STOP
        )
        rendered = render_highlight(raw)

        self.assertIn('<mark>found</mark>', rendered)
        self.assertIn('&lt;b&gt;', rendered)
        self.assertIn('&lt;script&gt;', rendered)
        self.assertIn('&amp;', rendered)
        self.assertNotIn('<script>', rendered)
        self.assertNotIn('<b>', rendered)

    def test_empty_headline(self):
        self.assertEqual(render_highlight(''), '')
        self.assertEqual(render_highlight(None), '')


class FacetTests(SearchTestCase):
    def test_source_facets_count_the_result_set(self):
        facets = {
            row['name']: row['total']
            for row in self.service.source_facets(SearchCriteria())
        }
        self.assertEqual(facets['central_extraordinary'], 2)
        self.assertEqual(facets['andhra'], 1)

    def test_source_facets_ignore_the_source_filter(self):
        # Otherwise picking one series would hide every alternative.
        facets = self.service.source_facets(SearchCriteria(sources=['andhra']))
        names = {row['name'] for row in facets}
        self.assertIn('central_extraordinary', names)
        self.assertTrue(
            next(row for row in facets if row['name'] == 'andhra')['selected']
        )

    def test_year_facets(self):
        years = {row['year']: row['total']
                 for row in self.service.year_facets(SearchCriteria())}
        self.assertEqual(years, {2024: 1, 2023: 1, 2022: 1})


class StatsTests(SearchTestCase):
    def test_archive_stats(self):
        stats = archive_stats()
        self.assertEqual(stats['total'], 3)
        self.assertEqual(str(stats['earliest']), '2022-06-10')
        self.assertEqual(str(stats['latest']), '2024-04-18')
