"""Ingest gazettes straight from the raw PDF directory, converting as needed.

``ingest_gazettes`` walks ``html/`` and can therefore only index what
``pdf2html -e legallayout`` has already converted. This command starts from
``raw/`` instead: a PDF whose legallayout HTML or pymupdf rendering is missing
is converted first -- through the same ``egazette.tools.pdf2html`` functions
the standalone tool uses -- and then handed to the same IngestService. A
gazette therefore goes from downloaded PDF to indexed record in one pass.

Which PDFs are considered is decided by *file* timestamps rather than gazette
dates, because a gazette published in 2019 may only have been downloaded last
night::

    manage.py ingest_raw_gazettes -l 1
    manage.py ingest_raw_gazettes -l 7 -s central_extraordinary
    manage.py ingest_raw_gazettes --start-ts '2026-01-01 00:00:00' \
                                  --end-ts '2026-02-01 00:00:00'
    manage.py ingest_raw_gazettes --relurl central_extraordinary/2026-01-01/269031

``-l N`` is the form a nightly cron wants: every raw file written between 2AM
N days ago and 2AM today, on the machine's own clock. The end of the window is
exclusive, so consecutive daily runs neither miss a file nor redo one.

A generated rendering is written alongside the PDF it came from -- into the
same data root, exactly where ``pdf2html`` would have put it -- so the
converted tree stays the one the crawler and the site share. A data root
mounted read-only falls back to ``GAZETTE_WRITE_ROOT``; ``--outdir`` overrides
both.
"""

import datetime
import os
import sys

from django.core.management.base import BaseCommand, CommandError

from egazette.tools import pdf2html

from gazettes.services import sources as sources_service
from gazettes.services import storage as storage_service
from gazettes.services.ingest import (
    CREATED,
    ERROR,
    SKIPPED,
    UPDATED,
    IngestService,
    IngestStats,
)

# Hour of the day the -l window is anchored to, chosen to sit after the
# scraper's own nightly run.
WINDOW_HOUR = 2

# Renderings this command will produce, as (asset kind, pdf2html engine). The
# legallayout HTML is what gets indexed; the pymupdf rendering is the
# alternate view and is cheap enough to build in the same pass.
RENDERINGS = (('html', 'legallayout'), ('pymupdf', 'pymupdf'))

TS_FORMATS = ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d')


def to_ts(value):
    for fmt in TS_FORMATS:
        try:
            return datetime.datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise CommandError(
        '%s is not a timestamp; use YYYY-MM-DD HH:MM:SS' % value
    )


def window_from_days(days):
    """The (start, end) datetimes ``-l N`` stands for."""
    today = datetime.date.today()
    end = datetime.datetime(today.year, today.month, today.day, WINDOW_HOUR)
    return end - datetime.timedelta(days=days), end


def in_window(path, start_ts, end_ts):
    """Was this file last written inside the timestamp window?

    Naive datetimes are compared in the local timezone, which is the clock
    file mtimes are recorded against.
    """
    if start_ts is None and end_ts is None:
        return True

    mtime = os.path.getmtime(path)
    if start_ts is not None and mtime < start_ts.timestamp():
        return False
    if end_ts is not None and mtime >= end_ts.timestamp():
        return False
    return True


def iter_raw_relurls(storage, srcs, start_ts, end_ts):
    """Yield every relurl with a raw file written inside the window."""
    seen = set()

    for root in storage.roots:
        rawdir = os.path.join(root, 'raw')
        if not os.path.isdir(rawdir):
            continue

        candidates = srcs or sorted(os.listdir(rawdir))
        for src in candidates:
            srcdir = os.path.join(rawdir, src)
            if not os.path.isdir(srcdir):
                continue

            for dirpath, _dirnames, filenames in os.walk(srcdir):
                for filename in sorted(filenames):
                    # AssetStorage.save() renames through '<name>.tmp.<pid>';
                    # a half-written upload is not a gazette yet.
                    if '.tmp.' in filename:
                        continue

                    path = os.path.join(dirpath, filename)
                    if not in_window(path, start_ts, end_ts):
                        continue

                    relurl = os.path.splitext(
                        os.path.relpath(path, rawdir))[0]
                    if relurl in seen:
                        continue
                    seen.add(relurl)
                    yield relurl


class Command(BaseCommand):
    help = ('Convert raw gazette PDFs to HTML where needed and ingest them, '
            'selected by when the raw file was downloaded')

    def add_arguments(self, parser):
        parser.add_argument(
            '-D', '--datadir', action='append', dest='datadirs', default=[],
            help='gazette data directory to read (repeatable); defaults to '
                 'EGAZETTE_DATA_ROOTS',
        )
        parser.add_argument(
            '-s', '--src', action='append', dest='srcs', default=[],
            help='gazette source to ingest (repeatable); all if omitted',
        )
        parser.add_argument(
            '--relurl', action='append', dest='relurls', default=[],
            help='ingest a single relurl (repeatable); ignores the window',
        )
        parser.add_argument(
            '-l', '--days', type=int, default=None,
            help='raw files written between 2AM this many days ago and 2AM '
                 'today',
        )
        parser.add_argument(
            '--start-ts', type=to_ts, default=None,
            help='start of the window, YYYY-MM-DD [HH:MM:SS] (inclusive)',
        )
        parser.add_argument(
            '--end-ts', type=to_ts, default=None,
            help='end of the window, YYYY-MM-DD [HH:MM:SS] (exclusive)',
        )
        parser.add_argument(
            '-r', '--force', action='store_true', default=False,
            help='reindex even when the content hash is unchanged',
        )
        parser.add_argument(
            '--no-pymupdf', action='store_true', default=False,
            help='only build the legallayout HTML, not the pymupdf rendering',
        )
        parser.add_argument('--limit', type=int, default=None,
                            help='stop after this many gazettes')
        parser.add_argument(
            '--dry-run', action='store_true', default=False,
            help='list what would be converted and ingested, writing nothing',
        )
        parser.add_argument(
            '--progress-every', type=int, default=200,
            help='log a running total every N gazettes (0 to disable)',
        )
        parser.add_argument(
            '--outdir', default=None,
            help='data directory to write generated renderings into; '
                 'defaults to the root the PDF was found in',
        )
        parser.add_argument(
            '--legallayout-dir', default=pdf2html.DEFAULT_LEGALLAYOUT_DIR,
            help='path to the legallayout checkout (parent of source/)',
        )
        parser.add_argument(
            '--public-base-url', default=None,
            help='public base URL for the IIIF manifest legallayout writes',
        )
        parser.add_argument(
            '--server-root', default=None,
            help='local directory served as the web root, used to turn the '
                 'output path into a URL path under --public-base-url',
        )

    def handle(self, *args, **options):
        for src in options['srcs']:
            if not sources_service.is_known_source(src):
                raise CommandError(
                    'unknown source %r; see egazette/srcs/datasrcs_info.py' % src
                )

        start_ts, end_ts = self.window(options)

        roots = options['datadirs'] or None
        write_root = roots[0] if roots else None
        self.storage = storage_service.AssetStorage(roots=roots,
                                                    write_root=write_root)

        # Whatever directory a rendering is written to has to be searched as
        # well, or the ingest that follows the conversion would not find the
        # HTML the conversion just produced.
        for root in (options['outdir'], self.storage.write_root):
            if root and root not in self.storage.roots:
                self.storage.roots.append(root)

        service = IngestService(storage=self.storage)

        self.renderings = [
            (kind, engine) for kind, engine in RENDERINGS
            if not (kind == 'pymupdf' and options['no_pymupdf'])
        ]

        if options['relurls']:
            relurls = iter(options['relurls'])
        else:
            relurls = iter_raw_relurls(self.storage, options['srcs'],
                                       start_ts, end_ts)

        stats = IngestStats()
        converted = {kind: 0 for kind, _engine in self.renderings}
        conversion_failures = []
        processed = 0
        failures = []

        for relurl in relurls:
            if options['limit'] is not None and processed >= options['limit']:
                break
            processed += 1

            missing = self.plan(relurl)

            if options['dry_run']:
                self.stdout.write('%-40s %s' % (
                    relurl,
                    'convert ' + ','.join(missing) if missing else 'no conversion',
                ))
                continue

            for kind, engine in self.renderings:
                if kind not in missing:
                    continue
                if self.convert(relurl, kind, engine, options):
                    converted[kind] += 1
                else:
                    conversion_failures.append((relurl, kind))
                    self.stderr.write(self.style.ERROR(
                        'convert   %s: %s conversion failed' % (relurl, engine)
                    ))

            result = service.ingest(relurl, force=options['force'])
            stats.add(result)

            if result.status in (CREATED, UPDATED):
                self.stdout.write('%-9s %s' % (result.status, result.identifier))
            elif result.status == ERROR:
                failures.append(result)
                self.stderr.write(self.style.ERROR(
                    'error     %s: %s' % (relurl, result.reason)
                ))
            elif result.status == SKIPPED and self.verbosity(options) > 1:
                self.stdout.write('skipped   %s: %s' % (relurl, result.reason))

            every = options['progress_every']
            if every and processed % every == 0:
                self.stderr.write('… %d processed (%s)' % (processed, stats))

        if options['dry_run']:
            self.stdout.write(self.style.SUCCESS(
                '%d gazette(s) would be ingested' % processed
            ))
            return

        # Counters back the browse pages, so refresh them once at the end
        # rather than on every row.
        sources_service.refresh_counts()

        summary = '%d processed: %s%s' % (
            processed, stats, self.conversion_summary(converted,
                                                      conversion_failures),
        )
        if failures or conversion_failures:
            self.stdout.write(self.style.WARNING(summary))
            sys.exit(1)
        self.stdout.write(self.style.SUCCESS(summary))

    # -- selection ---------------------------------------------------------

    def window(self, options):
        """The timestamp window, from -l or from --start-ts/--end-ts."""
        if options['days'] is not None:
            if options['start_ts'] or options['end_ts']:
                raise CommandError(
                    '-l/--days and --start-ts/--end-ts are alternatives'
                )
            if options['days'] < 0:
                raise CommandError('-l/--days must not be negative')
            return window_from_days(options['days'])

        start_ts, end_ts = options['start_ts'], options['end_ts']
        if start_ts and end_ts and end_ts < start_ts:
            raise CommandError('--end-ts is before --start-ts')
        return start_ts, end_ts

    # -- conversion --------------------------------------------------------

    def plan(self, relurl):
        """Which renderings this relurl needs built, in RENDERINGS order.

        Nothing is planned for a gazette that ingest would skip anyway --
        metadata is required, and a raw file that is not a PDF has no
        converter -- so a missing metatags file never costs a legallayout run.
        """
        try:
            relurl = storage_service.validate_relurl(relurl)
        except storage_service.InvalidRelurl:
            return []

        if self.storage.find('metatags', relurl) is None:
            return []

        pdf_path = self.storage.find('raw', relurl)
        if pdf_path is None or not pdf_path.lower().endswith('.pdf'):
            return []

        return [kind for kind, _engine in self.renderings
                if self.storage.find(kind, relurl) is None]

    def output_root(self, pdf_path, options):
        """The data directory a rendering built from this PDF belongs in.

        Alongside the PDF by default, so a converted gazette lands in the tree
        the crawler and the site already share rather than in a second copy of
        it. A read-only archive root falls back to the site's write root.
        """
        if options['outdir']:
            return options['outdir']

        for root in self.storage.roots:
            rawdir = os.path.join(root, 'raw') + os.sep
            if pdf_path.startswith(rawdir) and os.access(root, os.W_OK):
                return root

        return self.storage.write_root

    def convert(self, relurl, kind, engine, options):
        """Build one rendering. True if the file now exists."""
        pdf_path = self.storage.find('raw', relurl)
        outdir = os.path.join(self.output_root(pdf_path, options),
                              pdf2html.OUTPUT_SUBDIR[engine])

        result = pdf2html.convert_one(
            outdir, engine, options['legallayout_dir'], relurl, pdf_path,
            overwrite=False, public_base_url=options['public_base_url'],
            server_root=options['server_root'],
        )
        return result != 'failed'

    def conversion_summary(self, converted, conversion_failures):
        parts = ['%s+%d' % (kind, count)
                 for kind, count in sorted(converted.items()) if count]
        if conversion_failures:
            parts.append('conversion-failed=%d' % len(conversion_failures))
        if not parts:
            return ''
        return ' (%s)' % ' '.join(parts)

    @staticmethod
    def verbosity(options):
        return int(options.get('verbosity', 1))
