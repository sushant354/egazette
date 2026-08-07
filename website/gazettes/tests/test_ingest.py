import shutil
import tempfile

from django.test import TestCase, override_settings

from gazettes.models import Gazette
from gazettes.services.ingest import (
    CREATED,
    ERROR,
    SKIPPED,
    UNCHANGED,
    UPDATED,
    IngestService,
)
from gazettes.services.storage import AssetStorage
from gazettes.tests.factories import (
    CENTRAL_XML,
    LEGALLAYOUT_HTML,
    PYMUPDF_HTML,
    WBSL_XML,
    write_gazette,
)

RELURL = 'central_extraordinary/2024-04-18/253767'


class IngestTestCase(TestCase):
    def setUp(self):
        self.datadir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.datadir, ignore_errors=True)
        self.storage = AssetStorage(roots=[self.datadir],
                                    write_root=self.datadir)
        self.service = IngestService(storage=self.storage)


class LocalIngestTests(IngestTestCase):
    def test_creates_a_gazette_from_disk(self):
        write_gazette(self.datadir, RELURL)

        result = self.service.ingest(RELURL)

        self.assertEqual(result.status, CREATED)
        self.assertEqual(result.identifier,
                         'in.gazette.central.e.2024-04-18.253767')

        gazette = Gazette.objects.get(relurl=RELURL)
        self.assertEqual(gazette.ministry, 'Ministry of Railways')
        self.assertEqual(str(gazette.date), '2024-04-18')
        self.assertIn('inter cadre transfer', gazette.text)
        self.assertIsNotNone(gazette.search_vector)

    def test_creates_the_source_row_on_demand(self):
        write_gazette(self.datadir, RELURL)
        self.service.ingest(RELURL)

        gazette = Gazette.objects.get(relurl=RELURL)
        self.assertEqual(gazette.source.name, 'central_extraordinary')
        self.assertEqual(gazette.source.authority, 'Government of India')

    def test_html_is_required(self):
        # A gazette with no legallayout HTML has nothing to index; it is left
        # for a later run rather than half-recorded.
        write_gazette(self.datadir, RELURL, html=None)

        result = self.service.ingest(RELURL)

        self.assertEqual(result.status, SKIPPED)
        self.assertIn('legallayout', result.reason)
        self.assertFalse(Gazette.objects.exists())

    def test_metadata_is_required(self):
        write_gazette(self.datadir, RELURL, metatags=None)

        result = self.service.ingest(RELURL)

        self.assertEqual(result.status, SKIPPED)
        self.assertFalse(Gazette.objects.exists())

    def test_empty_html_is_skipped(self):
        write_gazette(self.datadir, RELURL, html='   \n  ')
        self.assertEqual(self.service.ingest(RELURL).status, SKIPPED)

    def test_unknown_source_is_skipped(self):
        write_gazette(self.datadir, 'notasource/2024-01-01/1')
        result = self.service.ingest('notasource/2024-01-01/1')
        self.assertEqual(result.status, SKIPPED)
        self.assertIn('unknown source', result.reason)

    def test_malformed_xml_is_a_client_error(self):
        write_gazette(self.datadir, RELURL, metatags='<document><oops>')
        result = self.service.ingest(RELURL)
        self.assertEqual(result.status, ERROR)
        # Retrying this payload unchanged can never succeed.
        self.assertTrue(result.client_error)

    def test_traversal_relurl_is_an_error_not_a_crash(self):
        result = self.service.ingest('../../etc/passwd')
        self.assertEqual(result.status, ERROR)
        self.assertTrue(result.client_error)


class ReingestTests(IngestTestCase):
    def test_unchanged_content_is_not_reindexed(self):
        write_gazette(self.datadir, RELURL)
        self.assertEqual(self.service.ingest(RELURL).status, CREATED)
        self.assertEqual(self.service.ingest(RELURL).status, UNCHANGED)

    def test_force_reindexes_unchanged_content(self):
        write_gazette(self.datadir, RELURL)
        self.service.ingest(RELURL)
        self.assertEqual(self.service.ingest(RELURL, force=True).status,
                         UPDATED)

    def test_changed_html_updates_the_record(self):
        write_gazette(self.datadir, RELURL)
        self.service.ingest(RELURL)

        write_gazette(self.datadir, RELURL,
                      html='<body><p>revised notification text</p></body>')
        self.assertEqual(self.service.ingest(RELURL).status, UPDATED)

        gazette = Gazette.objects.get(relurl=RELURL)
        self.assertIn('revised notification', gazette.text)
        self.assertNotIn('inter cadre', gazette.text)

    def test_optional_assets_appearing_later_are_picked_up(self):
        # The common case of a PDF being converted after the site first
        # ingested the gazette: content is unchanged, but the flags must move.
        write_gazette(self.datadir, RELURL)
        self.service.ingest(RELURL)
        self.assertFalse(Gazette.objects.get(relurl=RELURL).has_pymupdf)

        write_gazette(self.datadir, RELURL, pymupdf=PYMUPDF_HTML,
                      raw=b'%PDF-1.4 fake')
        result = self.service.ingest(RELURL)

        self.assertEqual(result.status, UNCHANGED)
        gazette = Gazette.objects.get(relurl=RELURL)
        self.assertTrue(gazette.has_pymupdf)
        self.assertTrue(gazette.has_pdf)
        self.assertEqual(gazette.pdf_bytes, len(b'%PDF-1.4 fake'))


class UploadIngestTests(IngestTestCase):
    def test_uploaded_payload_is_written_and_indexed(self):
        # Nothing on disk to begin with: this is the push-to-endpoint path.
        result = self.service.ingest(
            RELURL,
            metatags=CENTRAL_XML.encode('utf-8'),
            html=LEGALLAYOUT_HTML.encode('utf-8'),
            pymupdf=PYMUPDF_HTML.encode('utf-8'),
            raw=b'%PDF-1.4 fake',
        )

        self.assertEqual(result.status, CREATED)
        self.assertIsNotNone(self.storage.find('metatags', RELURL))
        self.assertIsNotNone(self.storage.find('html', RELURL))
        self.assertIsNotNone(self.storage.find('pymupdf', RELURL))
        self.assertIsNotNone(self.storage.find('raw', RELURL))

        gazette = Gazette.objects.get(relurl=RELURL)
        self.assertTrue(gazette.has_pdf)
        self.assertTrue(gazette.has_pymupdf)

    def test_optional_assets_may_be_omitted(self):
        result = self.service.ingest(
            RELURL,
            metatags=CENTRAL_XML.encode('utf-8'),
            html=LEGALLAYOUT_HTML.encode('utf-8'),
        )
        self.assertEqual(result.status, CREATED)

        gazette = Gazette.objects.get(relurl=RELURL)
        self.assertFalse(gazette.has_pdf)
        self.assertFalse(gazette.has_pymupdf)


class UndatedSourceTests(IngestTestCase):
    def test_a_gazette_with_only_a_year_is_ingested(self):
        relurl = 'wbsl/calcutta/1885'
        write_gazette(self.datadir, relurl, metatags=WBSL_XML)

        result = self.service.ingest(relurl)

        self.assertEqual(result.status, CREATED)
        gazette = Gazette.objects.get(relurl=relurl)
        self.assertIsNone(gazette.date)
        self.assertEqual(gazette.year, 1885)
        self.assertEqual(gazette.identifier, 'wbsl.WB00123')
        self.assertEqual(gazette.display_date, '1885')


class IdentifierCollisionTests(IngestTestCase):
    def test_two_relurls_claiming_one_identifier_is_reported(self):
        # wbsl identifiers come from the bookid, so two different paths
        # carrying the same bookid collide.
        write_gazette(self.datadir, 'wbsl/a/1', metatags=WBSL_XML)
        write_gazette(self.datadir, 'wbsl/b/2', metatags=WBSL_XML)

        self.assertEqual(self.service.ingest('wbsl/a/1').status, CREATED)
        result = self.service.ingest('wbsl/b/2')

        self.assertEqual(result.status, ERROR)
        self.assertIn('already used by', result.reason)
        self.assertTrue(result.client_error)
        # The first gazette is untouched.
        self.assertEqual(Gazette.objects.count(), 1)


@override_settings(GAZETTE_MAX_TEXT_CHARS=200, GAZETTE_MAX_INDEX_BYTES=100)
class TruncationTests(IngestTestCase):
    def test_long_text_is_capped_and_flagged(self):
        long_html = '<body><p>%s</p></body>' % ('notification ' * 500)
        write_gazette(self.datadir, RELURL, html=long_html)

        service = IngestService(storage=self.storage)
        self.assertEqual(service.ingest(RELURL).status, CREATED)

        gazette = Gazette.objects.get(relurl=RELURL)
        self.assertTrue(gazette.text_truncated)
        self.assertLessEqual(len(gazette.text), 200)
        # It is still findable despite the cap.
        self.assertIsNotNone(gazette.search_vector)
