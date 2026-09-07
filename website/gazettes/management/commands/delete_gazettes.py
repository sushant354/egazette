"""Delete gazettes from the site's index.

The mirror image of the ingest commands: whatever they put in, this takes out
again. It exists for the two ways an index goes wrong -- a source that was
crawled badly and has to be re-done from scratch, and a nightly run that
ingested a batch of rubbish that has to be undone before the good copy is
pushed:

    manage.py delete_gazettes -s andhra
    manage.py delete_gazettes -s central_extraordinary -t 01-01-2024 -T 31-01-2024
    manage.py delete_gazettes --added-since '2026-02-01 00:00:00'
    manage.py delete_gazettes -l 1                    # added in the last 24h
    manage.py delete_gazettes --relurl andhra/2018-05-04/2758

The filters combine with AND, so `-s andhra -l 1` is "the Andhra gazettes
added since yesterday" and not the union of the two. Selecting nothing at all
is refused unless `--all` is given, because `delete_gazettes` with a mistyped
option would otherwise empty the archive.

`-s` takes any source name that appears in the index, including one srcinfos
no longer lists -- a renamed or retired series is exactly what needs clearing
out, and there is no other way to reach those rows.

Only the database rows go. The gazette's files under `raw/`, `metatags/`,
`html/` and `pymupdf/` are left where they are -- they are the crawler's tree,
shared with the site rather than owned by it -- so a later `ingest_gazettes`
over the same data directory will index the gazette again. Delete or move the
files too when a gazette is meant to stay gone.

Bookmarks pointing at a deleted gazette go with it (the FK cascades), so the
count of those is reported alongside.
"""

import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from gazettes.management.commands.ingest_gazettes import to_date
from gazettes.management.commands.ingest_raw_gazettes import to_ts
from gazettes.models import Bookmark, Gazette
from gazettes.services import sources as sources_service

# Rows deleted per statement. Bounded so that emptying a whole source neither
# builds one enormous transaction nor holds locks on the table for the length
# of the run.
BATCH_SIZE = 500


def as_aware(value):
    """Read a naive command-line timestamp in the site's own timezone.

    ``created_at`` is stored in UTC, so a bare '2026-02-01' typed by an
    operator in Asia/Kolkata has to mean midnight there, not midnight UTC.
    """
    if settings.USE_TZ and timezone.is_naive(value):
        return timezone.make_aware(value)
    return value


def window_from_days(days):
    """The (since, before) timestamps ``-l N`` stands for.

    A rolling window ending *now*, not the 2AM-anchored one
    ``ingest_raw_gazettes -l N`` selects raw files by: the question here is
    "what has been added lately", and anything ingested this morning has to
    fall inside `-l 1` for the option to be of any use after a bad run.
    """
    now = timezone.now() if settings.USE_TZ else datetime.datetime.now()
    return now - datetime.timedelta(days=days), now


class Command(BaseCommand):
    help = ('Delete gazettes from the index, selected by source, gazette '
            'date, or when they were added')

    def add_arguments(self, parser):
        parser.add_argument(
            '-s', '--src', action='append', dest='srcs', default=[],
            help='gazette source to delete from (repeatable)',
        )
        parser.add_argument('-t', '--fromdate', type=to_date, default=None,
                            help='earliest gazette date (DD-MM-YYYY)')
        parser.add_argument('-T', '--todate', type=to_date, default=None,
                            help='latest gazette date (DD-MM-YYYY)')
        parser.add_argument(
            '-l', '--days', type=int, default=None,
            help='added within the last N days, counted from now',
        )
        parser.add_argument(
            '--added-since', type=to_ts, default=None,
            help='added at or after this timestamp, YYYY-MM-DD [HH:MM:SS]',
        )
        parser.add_argument(
            '--added-before', type=to_ts, default=None,
            help='added strictly before this timestamp (exclusive)',
        )
        parser.add_argument(
            '--relurl', action='append', dest='relurls', default=[],
            help='delete a single relurl (repeatable)',
        )
        parser.add_argument(
            '--identifier', action='append', dest='identifiers', default=[],
            help='delete a single Internet Archive identifier (repeatable)',
        )
        parser.add_argument(
            '--limit', type=int, default=None,
            help='delete at most this many, newest gazettes first',
        )
        parser.add_argument(
            '--all', action='store_true', default=False,
            help='required to run with no filter at all, i.e. empty the index',
        )
        parser.add_argument(
            '--dry-run', action='store_true', default=False,
            help='list what would be deleted without deleting anything',
        )
        parser.add_argument(
            '--noinput', '--no-input', action='store_false', dest='interactive',
            default=True, help='do not prompt for confirmation',
        )

    def handle(self, *args, **options):
        queryset, filters = self.select(options)

        if not filters and not options['all']:
            raise CommandError(
                'no filter given; pass --all to delete every gazette'
            )

        if options['limit'] is not None:
            if options['limit'] < 1:
                raise CommandError('--limit must be at least 1')
            # Model ordering is newest issue first, which is the half of a bad
            # batch an operator means when they cap a delete.
            pks = list(queryset.values_list('pk', flat=True)
                       [:options['limit']])
            queryset = Gazette.objects.filter(pk__in=pks)

        description = ', '.join(filters) if filters else 'every gazette'
        total = queryset.count()
        if not total:
            self.stdout.write('nothing to delete (%s)' % description)
            return

        bookmarks = Bookmark.objects.filter(gazette__in=queryset).count()
        summary = '%d gazette(s) (%s)%s' % (
            total, description,
            ' and %d bookmark(s)' % bookmarks if bookmarks else '',
        )

        if options['dry_run']:
            for identifier in queryset.values_list(
                'identifier', flat=True
            ).iterator(chunk_size=BATCH_SIZE):
                self.stdout.write(identifier)
            self.stdout.write(self.style.SUCCESS(
                '%s would be deleted' % summary
            ))
            return

        if options['interactive'] and not self.confirm(summary):
            self.stdout.write('cancelled, nothing deleted')
            return

        deleted, bookmarks_deleted = self.delete(queryset, total)

        # The browse pages read the per-source counters rather than counting
        # rows, so they have to be brought back in line with the table.
        sources_service.refresh_counts()

        message = 'deleted %d gazette(s)' % deleted
        if bookmarks_deleted:
            message += ' and %d bookmark(s)' % bookmarks_deleted
        self.stdout.write(self.style.SUCCESS(message))

    # -- selection ---------------------------------------------------------

    def select(self, options):
        """The gazettes to delete, and a description of why they were picked.

        The description is what the confirmation prompt shows, so it has to
        name every filter that narrowed the queryset.
        """
        queryset = Gazette.objects.all()
        filters = []

        if options['srcs']:
            # Any name in the index can be deleted, whether or not srcinfos
            # still lists it: a source that was renamed, retired or crawled
            # under a name that has since been corrected is precisely the one
            # somebody needs to clear out, and refusing it would leave those
            # rows with no way out. A name that matches nothing is reported
            # rather than rejected, so a typo is visible without blocking the
            # sources that were spelled right.
            present = set(
                Gazette.objects.filter(source__name__in=options['srcs'])
                .values_list('source__name', flat=True).distinct()
            )
            for src in sorted(set(options['srcs']) - present):
                self.stderr.write(self.style.WARNING(
                    'no gazettes in the index for source %r' % src
                ))
            queryset = queryset.filter(source__name__in=options['srcs'])
            filters.append('source %s' % ', '.join(sorted(options['srcs'])))

        fromdate, todate = options['fromdate'], options['todate']
        if fromdate and todate and todate < fromdate:
            raise CommandError('-T/--todate is before -t/--fromdate')
        if fromdate is not None:
            queryset = queryset.filter(date__gte=fromdate)
            filters.append('dated from %s' % fromdate)
        if todate is not None:
            queryset = queryset.filter(date__lte=todate)
            filters.append('dated to %s' % todate)

        since, before = self.window(options)
        if since is not None:
            queryset = queryset.filter(created_at__gte=since)
            filters.append('added since %s' % since)
        if before is not None:
            queryset = queryset.filter(created_at__lt=before)
            filters.append('added before %s' % before)

        if options['relurls']:
            queryset = queryset.filter(relurl__in=options['relurls'])
            filters.append('%d relurl(s)' % len(options['relurls']))
        if options['identifiers']:
            queryset = queryset.filter(identifier__in=options['identifiers'])
            filters.append('%d identifier(s)' % len(options['identifiers']))

        return queryset, filters

    def window(self, options):
        """The created_at window, from -l or from --added-since/--added-before."""
        if options['days'] is not None:
            if options['added_since'] or options['added_before']:
                raise CommandError(
                    '-l/--days and --added-since/--added-before are '
                    'alternatives'
                )
            if options['days'] < 0:
                raise CommandError('-l/--days must not be negative')
            return window_from_days(options['days'])

        since, before = options['added_since'], options['added_before']
        if since and before and before < since:
            raise CommandError('--added-before is before --added-since')
        return (as_aware(since) if since else None,
                as_aware(before) if before else None)

    # -- deletion ----------------------------------------------------------

    def confirm(self, summary):
        self.stdout.write(self.style.WARNING(
            'About to delete %s. This cannot be undone.' % summary
        ))
        self.stdout.write("Type 'yes' to continue, or anything else to abort: ",
                          ending='')
        return input().strip().lower() == 'yes'

    def delete(self, queryset, total):
        """Delete the queryset a batch at a time.

        The queryset is re-evaluated per batch, which is safe because every
        batch removes the rows it just matched, and keeps the working set
        bounded however large the selection is.
        """
        pks = queryset.order_by('pk').values_list('pk', flat=True)
        deleted = bookmarks = 0

        while True:
            batch = list(pks[:BATCH_SIZE])
            if not batch:
                break

            _count, per_model = Gazette.objects.filter(pk__in=batch).delete()
            deleted += per_model.get(Gazette._meta.label, 0)
            bookmarks += per_model.get(Bookmark._meta.label, 0)

            if deleted < total:
                self.stderr.write('… %d/%d deleted' % (deleted, total))

        return deleted, bookmarks
