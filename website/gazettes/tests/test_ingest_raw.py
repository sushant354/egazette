"""Tests for ``manage.py ingest_raw_gazettes``.

The conversion engines themselves are exercised by
``tools/tests/test_pdf2html.py``; here ``pdf2html.convert_one`` is stubbed out
so the tests can assert *what* the command asks to be converted, and that the
gazette lands in the index afterwards, without running legallayout.
"""

import datetime
import os
import shutil
import tempfile
from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from gazettes.management.commands.ingest_raw_gazettes import (
    iter_raw_relurls,
    window_from_days,
)
from gazettes.models import Gazette
from gazettes.services.storage import AssetStorage
from gazettes.tests.factories import (
    LEGALLAYOUT_HTML,
    PYMUPDF_HTML,
    write_gazette,
)

RELURL = 'central_extraordinary/2024-04-18/253767'
OTHER_RELURL = 'central_extraordinary/2024-04-19/253768'

CONVERT_ONE = 'egazette.tools.pdf2html.convert_one'


def set_mtime(path, when):
    stamp = when.timestamp()
    os.utime(path, (stamp, stamp))


class RawIngestTestCase(TestCase):
    def setUp(self):
        self.datadir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.datadir, ignore_errors=True)
        self.storage = AssetStorage(roots=[self.datadir],
                                    write_root=self.datadir)

    def run_command(self, *args, **options):
        out, err = StringIO(), StringIO()
        options.setdefault('stdout', out)
        options.setdefault('stderr', err)
        call_command('ingest_raw_gazettes', '-D', self.datadir, *args,
                     **options)
        return out.getvalue(), err.getvalue()


def fake_convert(html=LEGALLAYOUT_HTML, pymupdf=PYMUPDF_HTML):
    """A convert_one stub that writes the rendering the real one would."""
    contents = {'legallayout': html, 'pymupdf': pymupdf}

    def convert_one(outdir, engine, legallayout_dir, relurl, pdf_path,
                    overwrite, public_base_url=None, server_root=None):
        content = contents[engine]
        if content is None:
            return 'failed'
        out_path = os.path.join(outdir, '%s.html' % relurl)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'w') as handle:
            handle.write(content)
        return 'converted'

    return convert_one


class WindowTests(TestCase):
    def test_days_window_runs_2am_to_2am(self):
        start, end = window_from_days(3)

        today = datetime.date.today()
        self.assertEqual(end, datetime.datetime(today.year, today.month,
                                                today.day, 2, 0, 0))
        self.assertEqual(end - start, datetime.timedelta(days=3))
        self.assertEqual(start.hour, 2)

    def test_days_and_explicit_timestamps_are_alternatives(self):
        with self.assertRaises(CommandError):
            call_command('ingest_raw_gazettes', '-l', '1',
                         '--start-ts', '2026-01-01')

    def test_end_before_start_is_rejected(self):
        with self.assertRaises(CommandError):
            call_command('ingest_raw_gazettes', '--start-ts', '2026-02-01',
                         '--end-ts', '2026-01-01')

    def test_unparseable_timestamp_is_rejected(self):
        with self.assertRaises(CommandError):
            call_command('ingest_raw_gazettes', '--start-ts', '01-02-2026')


class EnumerationTests(RawIngestTestCase):
    def test_only_raw_files_inside_the_window_are_yielded(self):
        old = write_gazette(self.datadir, RELURL, html=None, raw=b'%PDF-old')
        new = write_gazette(self.datadir, OTHER_RELURL, html=None,
                            raw=b'%PDF-new')

        set_mtime(old['raw'], datetime.datetime(2026, 1, 1, 3, 0, 0))
        set_mtime(new['raw'], datetime.datetime(2026, 1, 5, 3, 0, 0))

        relurls = list(iter_raw_relurls(
            self.storage, [], datetime.datetime(2026, 1, 4),
            datetime.datetime(2026, 1, 6),
        ))

        self.assertEqual(relurls, [OTHER_RELURL])

    def test_the_end_of_the_window_is_exclusive(self):
        written = write_gazette(self.datadir, RELURL, html=None,
                                raw=b'%PDF-1.4')
        boundary = datetime.datetime(2026, 1, 5, 2, 0, 0)
        set_mtime(written['raw'], boundary)

        before = list(iter_raw_relurls(self.storage, [], None, boundary))
        after = list(iter_raw_relurls(self.storage, [], boundary, None))

        self.assertEqual(before, [])
        self.assertEqual(after, [RELURL])

    def test_half_written_uploads_are_ignored(self):
        write_gazette(self.datadir, RELURL, html=None, raw=b'%PDF-1.4')
        tmp = os.path.join(self.datadir, 'raw', RELURL + '.pdf.tmp.4242')
        with open(tmp, 'w') as handle:
            handle.write('half a pdf')

        self.assertEqual(list(iter_raw_relurls(self.storage, [], None, None)),
                         [RELURL])

    def test_a_source_filter_limits_the_walk(self):
        write_gazette(self.datadir, RELURL, html=None, raw=b'%PDF-1.4')

        self.assertEqual(
            list(iter_raw_relurls(self.storage, ['andhra'], None, None)), [])


class ConversionTests(RawIngestTestCase):
    def test_missing_renderings_are_generated_and_the_gazette_indexed(self):
        write_gazette(self.datadir, RELURL, html=None, raw=b'%PDF-1.4')

        with mock.patch(CONVERT_ONE, side_effect=fake_convert()) as convert:
            out, _err = self.run_command()

        self.assertEqual(sorted(call.args[1] for call in convert.call_args_list),
                         ['legallayout', 'pymupdf'])

        self.assertTrue(os.path.exists(
            os.path.join(self.datadir, 'html', RELURL + '.html')))
        self.assertTrue(os.path.exists(
            os.path.join(self.datadir, 'pymupdf', RELURL + '.html')))

        gazette = Gazette.objects.get(relurl=RELURL)
        self.assertEqual(gazette.identifier,
                         'in.gazette.central.e.2024-04-18.253767')
        self.assertIn('inter cadre transfer', gazette.text)
        self.assertTrue(gazette.has_pdf)
        self.assertTrue(gazette.has_pymupdf)
        self.assertIn('created', out)

    def test_existing_renderings_are_not_rebuilt(self):
        write_gazette(self.datadir, RELURL, html=LEGALLAYOUT_HTML,
                      pymupdf=PYMUPDF_HTML, raw=b'%PDF-1.4')

        with mock.patch(CONVERT_ONE, side_effect=fake_convert()) as convert:
            self.run_command()

        convert.assert_not_called()
        self.assertTrue(Gazette.objects.filter(relurl=RELURL).exists())

    def test_only_the_missing_rendering_is_built(self):
        write_gazette(self.datadir, RELURL, html=LEGALLAYOUT_HTML,
                      raw=b'%PDF-1.4')

        with mock.patch(CONVERT_ONE, side_effect=fake_convert()) as convert:
            self.run_command()

        self.assertEqual([call.args[1] for call in convert.call_args_list],
                         ['pymupdf'])

    def test_no_pymupdf_skips_the_alternate_rendering(self):
        write_gazette(self.datadir, RELURL, html=None, raw=b'%PDF-1.4')

        with mock.patch(CONVERT_ONE, side_effect=fake_convert()) as convert:
            self.run_command('--no-pymupdf')

        self.assertEqual([call.args[1] for call in convert.call_args_list],
                         ['legallayout'])
        self.assertFalse(os.path.exists(
            os.path.join(self.datadir, 'pymupdf', RELURL + '.html')))

    def test_a_gazette_without_metadata_is_never_converted(self):
        # legallayout is expensive; a gazette ingest would skip anyway is not
        # worth converting.
        write_gazette(self.datadir, RELURL, metatags=None, html=None,
                      raw=b'%PDF-1.4')

        with mock.patch(CONVERT_ONE, side_effect=fake_convert()) as convert:
            self.run_command()

        convert.assert_not_called()
        self.assertFalse(Gazette.objects.exists())

    def test_a_non_pdf_raw_file_is_not_converted(self):
        write_gazette(self.datadir, RELURL, html=None)
        path = os.path.join(self.datadir, 'raw', RELURL + '.zip')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as handle:
            handle.write('not a pdf')

        with mock.patch(CONVERT_ONE, side_effect=fake_convert()) as convert:
            self.run_command()

        convert.assert_not_called()
        self.assertFalse(Gazette.objects.exists())

    def test_a_failed_conversion_is_reported_and_exits_nonzero(self):
        write_gazette(self.datadir, RELURL, html=None, raw=b'%PDF-1.4')

        with mock.patch(CONVERT_ONE,
                        side_effect=fake_convert(html=None, pymupdf=None)):
            with self.assertRaises(SystemExit):
                self.run_command()

        self.assertFalse(Gazette.objects.exists())

    def test_dry_run_writes_nothing(self):
        write_gazette(self.datadir, RELURL, html=None, raw=b'%PDF-1.4')

        with mock.patch(CONVERT_ONE, side_effect=fake_convert()) as convert:
            out, _err = self.run_command('--dry-run')

        convert.assert_not_called()
        self.assertFalse(Gazette.objects.exists())
        self.assertIn(RELURL, out)
        self.assertIn('html', out)

    def test_renderings_land_next_to_the_pdf(self):
        # The site's write root is elsewhere, but the writable data root
        # holding the PDF is where pdf2html would have written the HTML, so
        # that is where it goes -- and the ingest still finds it there.
        write_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, write_root, ignore_errors=True)
        write_gazette(self.datadir, RELURL, html=None, raw=b'%PDF-1.4')

        with override_settings(GAZETTE_DATA_ROOTS=[self.datadir],
                               GAZETTE_WRITE_ROOT=write_root):
            with mock.patch(CONVERT_ONE, side_effect=fake_convert()):
                out, err = StringIO(), StringIO()
                call_command('ingest_raw_gazettes', stdout=out, stderr=err)

        self.assertTrue(os.path.exists(
            os.path.join(self.datadir, 'html', RELURL + '.html')))
        self.assertFalse(os.path.exists(
            os.path.join(write_root, 'html', RELURL + '.html')))
        self.assertTrue(Gazette.objects.filter(relurl=RELURL).exists())

    def test_outdir_overrides_where_renderings_are_written(self):
        outdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, outdir, ignore_errors=True)
        write_gazette(self.datadir, RELURL, html=None, raw=b'%PDF-1.4')

        with mock.patch(CONVERT_ONE, side_effect=fake_convert()):
            self.run_command('--outdir', outdir)

        self.assertFalse(os.path.exists(
            os.path.join(self.datadir, 'html', RELURL + '.html')))
        self.assertTrue(os.path.exists(
            os.path.join(outdir, 'html', RELURL + '.html')))
        # The override directory is searched too, so the gazette is indexed.
        self.assertTrue(Gazette.objects.filter(relurl=RELURL).exists())

    def test_relurls_bypass_the_window(self):
        written = write_gazette(self.datadir, RELURL, html=None,
                                raw=b'%PDF-1.4')
        set_mtime(written['raw'], datetime.datetime(2019, 1, 1))

        with mock.patch(CONVERT_ONE, side_effect=fake_convert()):
            self.run_command('--relurl', RELURL, '-l', '1')

        self.assertTrue(Gazette.objects.filter(relurl=RELURL).exists())

    def test_an_unknown_source_is_rejected(self):
        with self.assertRaises(CommandError):
            self.run_command('-s', 'nosuchsource')
