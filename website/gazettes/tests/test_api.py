import json
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from gazettes.models import Gazette
from gazettes.services.storage import AssetStorage
from gazettes.tests.factories import (
    CENTRAL_XML,
    LEGALLAYOUT_HTML,
    PYMUPDF_HTML,
)

RELURL = 'central_extraordinary/2024-04-18/253767'
IDENTIFIER = 'in.gazette.central.e.2024-04-18.253767'
TOKEN = 'test-ingest-token'


class ApiTestCase(TestCase):
    def setUp(self):
        self.datadir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.datadir, ignore_errors=True)

        patcher = override_settings(
            GAZETTE_DATA_ROOTS=[self.datadir],
            GAZETTE_WRITE_ROOT=self.datadir,
            GAZETTE_INGEST_TOKENS=[TOKEN],
        )
        patcher.enable()
        self.addCleanup(patcher.disable)

        self.storage = AssetStorage(roots=[self.datadir],
                                    write_root=self.datadir)

    def auth(self, token=TOKEN):
        return {'HTTP_AUTHORIZATION': 'Bearer %s' % token}

    def payload(self, metatags=CENTRAL_XML, html=LEGALLAYOUT_HTML, **extra):
        data = {'relurl': RELURL}
        if metatags is not None:
            data['metatags'] = SimpleUploadedFile(
                'meta.xml', metatags.encode('utf-8'), 'application/xml'
            )
        if html is not None:
            data['html'] = SimpleUploadedFile(
                'doc.html', html.encode('utf-8'), 'text/html'
            )
        data.update(extra)
        return data

    def post(self, data, **kwargs):
        return self.client.post(reverse('gazettes:api_ingest'), data,
                                **{**self.auth(), **kwargs})


class AuthTests(ApiTestCase):
    def test_missing_token_is_rejected(self):
        response = self.client.post(reverse('gazettes:api_ingest'),
                                    self.payload())
        self.assertEqual(response.status_code, 401)
        self.assertFalse(Gazette.objects.exists())

    def test_wrong_token_is_rejected(self):
        response = self.client.post(
            reverse('gazettes:api_ingest'), self.payload(),
            **self.auth('not-the-token')
        )
        self.assertEqual(response.status_code, 401)
        self.assertFalse(Gazette.objects.exists())

    def test_x_ingest_token_header_also_works(self):
        response = self.client.post(
            reverse('gazettes:api_ingest'), self.payload(),
            HTTP_X_INGEST_TOKEN=TOKEN,
        )
        self.assertEqual(response.status_code, 200)

    @override_settings(GAZETTE_INGEST_TOKENS=[])
    def test_endpoint_is_closed_when_no_tokens_are_configured(self):
        response = self.post(self.payload())
        self.assertEqual(response.status_code, 503)

    def test_get_is_not_allowed(self):
        response = self.client.get(reverse('gazettes:api_ingest'),
                                   **self.auth())
        self.assertEqual(response.status_code, 405)

    def test_no_csrf_token_is_required(self):
        # The push tool authenticates with a bearer token, not a session.
        client = self.client_class(enforce_csrf_checks=True)
        response = client.post(reverse('gazettes:api_ingest'),
                               self.payload(), **self.auth())
        self.assertEqual(response.status_code, 200)


class IngestEndpointTests(ApiTestCase):
    def test_uploads_a_gazette(self):
        response = self.post(self.payload())

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['status'], 'created')
        self.assertEqual(body['identifier'], IDENTIFIER)

        self.assertTrue(Gazette.objects.filter(relurl=RELURL).exists())
        self.assertIsNotNone(self.storage.find('html', RELURL))
        self.assertIsNotNone(self.storage.find('metatags', RELURL))

    def test_uploads_optional_assets(self):
        response = self.post(self.payload(
            pymupdf=SimpleUploadedFile('p.html', PYMUPDF_HTML.encode(),
                                       'text/html'),
            raw=SimpleUploadedFile('g.pdf', b'%PDF-1.4 fake',
                                   'application/pdf'),
        ))

        self.assertEqual(response.status_code, 200)
        gazette = Gazette.objects.get(relurl=RELURL)
        self.assertTrue(gazette.has_pdf)
        self.assertTrue(gazette.has_pymupdf)
        self.assertTrue(self.storage.find('raw', RELURL).endswith('.pdf'))

    def test_repeat_upload_is_unchanged(self):
        self.post(self.payload())
        response = self.post(self.payload())
        self.assertEqual(response.json()['status'], 'unchanged')

    def test_force_reingests(self):
        self.post(self.payload())
        response = self.post(self.payload(force='1'))
        self.assertEqual(response.json()['status'], 'updated')

    def test_missing_html_is_skipped_not_crashed(self):
        response = self.post(self.payload(html=None))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'skipped')
        self.assertFalse(Gazette.objects.exists())

    def test_malformed_xml_is_a_4xx_so_the_pusher_does_not_retry(self):
        response = self.post(self.payload(metatags='<document><oops>'))
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['status'], 'error')

    def test_missing_relurl_is_a_400(self):
        response = self.post({'html': SimpleUploadedFile(
            'doc.html', LEGALLAYOUT_HTML.encode(), 'text/html')})
        self.assertEqual(response.status_code, 400)


class PathSafetyTests(ApiTestCase):
    def test_traversal_relurl_is_rejected(self):
        for bad in ('../../../etc/passwd',
                    'central_extraordinary/../../../etc/passwd',
                    '/etc/passwd',
                    'a/../../b'):
            with self.subTest(relurl=bad):
                response = self.post(self.payload() | {'relurl': bad})
                self.assertIn(response.status_code, (400, 200))
                if response.status_code == 200:
                    # Anything that parses as a relurl must at least belong to
                    # a known source, and none of these do.
                    self.assertEqual(response.json()['status'], 'skipped')
                self.assertFalse(Gazette.objects.exists())

    def test_hostile_raw_extension_is_rejected(self):
        response = self.post(self.payload(
            raw=SimpleUploadedFile('x.pdf', b'%PDF', 'application/pdf'),
            raw_extension='.php',
        ))
        self.assertEqual(response.status_code, 400)

    def test_extension_with_a_path_separator_is_rejected(self):
        response = self.post(self.payload(
            raw=SimpleUploadedFile('x.pdf', b'%PDF', 'application/pdf'),
            raw_extension='./../x',
        ))
        self.assertEqual(response.status_code, 400)

    @override_settings(GAZETTE_MAX_UPLOAD_BYTES=10)
    def test_oversized_upload_is_rejected(self):
        response = self.post(self.payload())
        self.assertEqual(response.status_code, 413)


class StatusEndpointTests(ApiTestCase):
    def url(self):
        return reverse('gazettes:api_ingest_status')

    def test_reports_what_the_site_holds(self):
        self.post(self.payload())

        response = self.client.post(
            self.url(),
            data=json.dumps({'relurls': [RELURL, 'andhra/2018-01-01/1']}),
            content_type='application/json',
            **self.auth(),
        )

        self.assertEqual(response.status_code, 200)
        known = response.json()['gazettes']
        # The pusher uses these hashes to skip unchanged gazettes.
        self.assertIn(RELURL, known)
        self.assertEqual(known[RELURL]['identifier'], IDENTIFIER)
        self.assertTrue(known[RELURL]['html_sha256'])
        self.assertNotIn('andhra/2018-01-01/1', known)

    def test_requires_authentication(self):
        response = self.client.post(
            self.url(), data=json.dumps({'relurls': []}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 401)

    def test_rejects_bad_json(self):
        response = self.client.post(
            self.url(), data='not json', content_type='application/json',
            **self.auth(),
        )
        self.assertEqual(response.status_code, 400)

    def test_rejects_a_non_list(self):
        response = self.client.post(
            self.url(), data=json.dumps({'relurls': 'nope'}),
            content_type='application/json', **self.auth(),
        )
        self.assertEqual(response.status_code, 400)

    def test_caps_the_batch_size(self):
        response = self.client.post(
            self.url(),
            data=json.dumps({'relurls': ['a/b/%d' % i for i in range(3000)]}),
            content_type='application/json', **self.auth(),
        )
        self.assertEqual(response.status_code, 400)

    def test_ignores_malformed_relurls_in_the_batch(self):
        response = self.client.post(
            self.url(),
            data=json.dumps({'relurls': ['../../etc/passwd', RELURL]}),
            content_type='application/json', **self.auth(),
        )
        self.assertEqual(response.status_code, 200)
