import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from gazettes.models import Bookmark, Gazette
from gazettes.services import sources as sources_service
from gazettes.services.ingest import IngestService
from gazettes.services.storage import AssetStorage
from gazettes.tests.factories import PYMUPDF_HTML, goa_xml, write_gazette

RELURL = 'central_extraordinary/2024-04-18/253767'
IDENTIFIER = 'in.gazette.central.e.2024-04-18.253767'


class ViewTestCase(TestCase):
    def setUp(self):
        self.datadir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.datadir, ignore_errors=True)

        # Point the site's storage at the temporary tree for the whole test.
        patcher = override_settings(
            GAZETTE_DATA_ROOTS=[self.datadir],
            GAZETTE_WRITE_ROOT=self.datadir,
        )
        patcher.enable()
        self.addCleanup(patcher.disable)

        self.storage = AssetStorage(roots=[self.datadir],
                                    write_root=self.datadir)
        self.service = IngestService(storage=self.storage)

    def ingest(self, relurl=RELURL, **kwargs):
        write_gazette(self.datadir, relurl, **kwargs)
        result = self.service.ingest(relurl)
        assert result.ok, result.reason
        sources_service.refresh_counts()
        return Gazette.objects.get(relurl=relurl)


class PageTests(ViewTestCase):
    def test_home_renders_with_content(self):
        self.ingest()
        response = self.client.get(reverse('gazettes:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Extrordinary Gazette of India')

    def test_home_renders_when_the_archive_is_empty(self):
        response = self.client.get(reverse('gazettes:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'archive is empty')

    def test_search_page(self):
        self.ingest()
        response = self.client.get(reverse('gazettes:search'),
                                   {'q': 'inter cadre transfer'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, IDENTIFIER)

    def test_search_with_no_matches(self):
        self.ingest()
        response = self.client.get(reverse('gazettes:search'),
                                   {'q': 'zzzqqqxyzzy'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No gazettes matched')

    def test_search_survives_a_bad_date(self):
        self.ingest()
        response = self.client.get(reverse('gazettes:search'),
                                   {'q': 'land', 'from_date': 'not-a-date'})
        self.assertEqual(response.status_code, 200)

    def test_source_pages(self):
        self.ingest()
        self.assertEqual(
            self.client.get(reverse('gazettes:source_list')).status_code, 200
        )
        response = self.client.get(
            reverse('gazettes:source_detail', args=['central_extraordinary'])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, IDENTIFIER)

    def test_unknown_source_is_404(self):
        response = self.client.get(
            reverse('gazettes:source_detail', args=['nosuchsource'])
        )
        self.assertEqual(response.status_code, 404)

    def test_about_page(self):
        self.assertEqual(
            self.client.get(reverse('gazettes:about')).status_code, 200
        )


class DetailTests(ViewTestCase):
    def test_detail_shows_the_gazette_text_and_metadata(self):
        self.ingest()
        response = self.client.get(reverse('gazettes:detail', args=[IDENTIFIER]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'NOTIFICATIONS BY GOVERNMENT')
        self.assertContains(response, 'Ministry of Railways')
        self.assertContains(response, 'gazette-document')

    def test_detail_does_not_leak_the_documents_stylesheet(self):
        self.ingest()
        response = self.client.get(reverse('gazettes:detail', args=[IDENTIFIER]))
        body = response.content.decode()
        # The site's own stylesheet is a <link>; the gazette's inline <style>
        # must not have survived sanitisation.
        self.assertNotIn('<style', body)

    def test_unknown_identifier_is_404(self):
        response = self.client.get(
            reverse('gazettes:detail', args=['in.gazette.nope.1'])
        )
        self.assertEqual(response.status_code, 404)

    def test_detail_reports_missing_html_rather_than_blanking(self):
        gazette = self.ingest()
        import os

        os.unlink(self.storage.find('html', gazette.relurl))

        response = self.client.get(reverse('gazettes:detail', args=[IDENTIFIER]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not available on this server')

    def test_pymupdf_view_is_offered_only_when_it_exists(self):
        self.ingest()
        response = self.client.get(reverse('gazettes:detail', args=[IDENTIFIER]))
        self.assertNotContains(response, 'Alternate rendering')

        self.assertEqual(
            self.client.get(
                reverse('gazettes:detail_pymupdf', args=[IDENTIFIER])
            ).status_code,
            404,
        )

    def test_pymupdf_view_when_present(self):
        self.ingest(pymupdf=PYMUPDF_HTML)

        response = self.client.get(reverse('gazettes:detail', args=[IDENTIFIER]))
        self.assertContains(response, 'Alternate rendering')

        response = self.client.get(
            reverse('gazettes:detail_pymupdf', args=[IDENTIFIER])
        )
        self.assertEqual(response.status_code, 200)
        # It is framed, never inlined, and kept out of the search index.
        self.assertContains(response, '<iframe')
        self.assertContains(response, 'noindex')

    def test_pymupdf_frame_is_served_with_a_restrictive_policy(self):
        self.ingest(pymupdf=PYMUPDF_HTML)
        response = self.client.get(
            reverse('gazettes:pymupdf_frame', args=[IDENTIFIER])
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("default-src 'none'",
                      response['Content-Security-Policy'])
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')

    def test_pdf_is_served_when_held_locally(self):
        self.ingest(raw=b'%PDF-1.4 fake pdf')
        response = self.client.get(
            reverse('gazettes:gazette_pdf', args=[IDENTIFIER])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')

        # Close the underlying file directly rather than calling
        # response.close(): that fires request_finished, which closes the
        # database connection this TestCase's transaction is still using.
        handle = response.file_to_stream
        self.assertEqual(b''.join(response.streaming_content),
                         b'%PDF-1.4 fake pdf')
        if handle is not None and not handle.closed:
            handle.close()

    def test_pdf_falls_back_to_the_internet_archive(self):
        # Most deployments will not hold 658GB of PDFs.
        self.ingest()
        response = self.client.get(
            reverse('gazettes:gazette_pdf', args=[IDENTIFIER])
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(IDENTIFIER, response['Location'])
        self.assertIn('archive.org', response['Location'])

    @override_settings(GAZETTE_USE_X_ACCEL=True,
                       GAZETTE_X_ACCEL_PREFIX='/protected/')
    def test_x_accel_redirect_names_the_root_the_file_was_found_in(self):
        self.ingest(raw=b'%PDF-1.4 fake pdf')
        response = self.client.get(
            reverse('gazettes:gazette_pdf', args=[IDENTIFIER])
        )

        self.assertEqual(
            response['X-Accel-Redirect'],
            '/protected/0/raw/%s.pdf' % RELURL,
        )
        self.assertNotIn('..', response['X-Accel-Redirect'])


class DocumentDetailTests(ViewTestCase):
    """Goa puts several gazettes into one Internet Archive item."""

    ITEM = 'in.goa.egaz.2223-28.SI'

    def setUp(self):
        super().setUp()
        self.og = self.ingest('goa/2022-10-13/2223-28-SI-OG-0',
                              metatags=goa_xml())
        self.sug = self.ingest('goa/2022-10-13/2223-28-SI-SUG-1',
                               metatags=goa_xml('SUG', '1'))

    def test_each_document_has_its_own_page(self):
        url = reverse('gazettes:detail', args=[self.ITEM, '2223-28-SI-SUG-1'])
        self.assertEqual(self.sug.get_absolute_url(), url)

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['gazette'], self.sug)
        self.assertContains(
            response, 'archive.org/details/%s/2223-28-SI-SUG-1' % self.ITEM)

    def test_bare_identifier_redirects_to_the_first_document(self):
        response = self.client.get(reverse('gazettes:detail', args=[self.ITEM]))
        self.assertRedirects(response, self.og.get_absolute_url())

    def test_unknown_document_is_404(self):
        response = self.client.get(
            reverse('gazettes:detail', args=[self.ITEM, '2223-28-SI-OG-9'])
        )
        self.assertEqual(response.status_code, 404)

    def test_pdf_falls_back_to_the_document_in_the_archive_item(self):
        response = self.client.get(self.sug.get_pdf_url())
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].endswith(
            '/%s/2223-28-SI-SUG-1' % self.ITEM))

    def test_bookmarking_a_document(self):
        user = get_user_model().objects.create_user('reader', password='x')
        self.client.force_login(user)

        response = self.client.post(self.sug.get_bookmark_url(),
                                    {'action': 'add'})

        self.assertRedirects(response, self.sug.get_absolute_url())
        self.assertEqual(
            list(Bookmark.objects.values_list('gazette', flat=True)),
            [self.sug.pk],
        )
