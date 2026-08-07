"""Ingest gazettes from a data directory the site can read directly.

This is the local half of the update path -- use it when the site shares a
host with the scraper's data. When it does not, run ``tools/push_gazettes.py``
on the scraper host instead; it posts the same gazettes to /api/ingest/ and
they land in the same IngestService.

    manage.py ingest_gazettes                        everything available
    manage.py ingest_gazettes -s andhra              one source
    manage.py ingest_gazettes -t 01-01-2024 -T 31-01-2024
    manage.py ingest_gazettes --relurl andhra/2018-05-04/2758

Enumeration walks ``html/`` rather than ``raw/``, because a gazette without
legallayout HTML is not ingested and ``raw/`` holds two orders of magnitude
more files than ``html/`` does.
"""

import datetime
import os
import re
import sys

from django.core.management.base import BaseCommand, CommandError

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

DATE_RE = re.compile(r'(\d{4})-(\d{2})-(\d{2})')


def relurl_date(relurl):
    match = DATE_RE.search(relurl)
    if not match:
        return None
    try:
        return datetime.date(*(int(x) for x in match.groups()))
    except ValueError:
        return None


def in_daterange(relurl, fromdate, todate):
    if fromdate is None and todate is None:
        return True
    date = relurl_date(relurl)
    if date is None:
        # Undated sources (archival scans) are only included when the caller
        # did not ask for a date range.
        return False
    if fromdate is not None and date < fromdate:
        return False
    if todate is not None and date > todate:
        return False
    return True


def to_date(datestr):
    nums = re.findall(r'\d+', datestr)
    if len(nums) != 3:
        raise CommandError('%s is not in DD-MM-YYYY format' % datestr)
    day, month, year = (int(x) for x in nums)
    return datetime.date(year, month, day)


def iter_html_relurls(storage, srcs, fromdate, todate):
    """Yield every relurl that has legallayout HTML in some data root."""
    seen = set()

    for root in storage.roots:
        htmldir = os.path.join(root, 'html')
        if not os.path.isdir(htmldir):
            continue

        candidates = srcs or sorted(os.listdir(htmldir))
        for src in candidates:
            srcdir = os.path.join(htmldir, src)
            if not os.path.isdir(srcdir):
                continue

            for dirpath, _dirnames, filenames in os.walk(srcdir):
                for filename in sorted(filenames):
                    if not filename.endswith('.html'):
                        continue
                    path = os.path.join(dirpath, filename)
                    relurl = os.path.relpath(path, htmldir)[: -len('.html')]
                    if relurl in seen:
                        continue
                    if not in_daterange(relurl, fromdate, todate):
                        continue
                    seen.add(relurl)
                    yield relurl


class Command(BaseCommand):
    help = 'Ingest gazettes from a local gazette data directory'

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
            help='ingest a single relurl (repeatable)',
        )
        parser.add_argument('-t', '--fromdate', type=to_date, default=None,
                            help='from date (DD-MM-YYYY)')
        parser.add_argument('-T', '--todate', type=to_date, default=None,
                            help='to date (DD-MM-YYYY)')
        parser.add_argument(
            '-r', '--force', action='store_true', default=False,
            help='reindex even when the content hash is unchanged',
        )
        parser.add_argument('--limit', type=int, default=None,
                            help='stop after this many gazettes')
        parser.add_argument(
            '--dry-run', action='store_true', default=False,
            help='list what would be ingested without writing anything',
        )
        parser.add_argument(
            '--progress-every', type=int, default=200,
            help='log a running total every N gazettes (0 to disable)',
        )

    def handle(self, *args, **options):
        for src in options['srcs']:
            if not sources_service.is_known_source(src):
                raise CommandError(
                    'unknown source %r; see egazette/srcs/datasrcs_info.py' % src
                )

        roots = options['datadirs'] or None
        storage = storage_service.AssetStorage(roots=roots)
        service = IngestService(storage=storage)

        if options['relurls']:
            relurls = iter(options['relurls'])
        else:
            relurls = iter_html_relurls(
                storage, options['srcs'], options['fromdate'],
                options['todate'],
            )

        stats = IngestStats()
        processed = 0
        failures = []

        for relurl in relurls:
            if options['limit'] is not None and processed >= options['limit']:
                break
            processed += 1

            if options['dry_run']:
                self.stdout.write(relurl)
                continue

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

        summary = '%d processed: %s' % (processed, stats)
        if failures:
            self.stdout.write(self.style.WARNING(summary))
            sys.exit(1)
        self.stdout.write(self.style.SUCCESS(summary))

    @staticmethod
    def verbosity(options):
        return int(options.get('verbosity', 1))
