"""Rebuild search vectors for gazettes already in the database.

Needed after changing ``EGAZETTE_TS_CONFIG`` or the search weights, and to
fill in any gazette whose tsvector build failed at ingest time.

    manage.py reindex_gazettes            only rows with no vector
    manage.py reindex_gazettes --all      every row
    manage.py reindex_gazettes -s andhra
"""

from django.core.management.base import BaseCommand, CommandError

from gazettes.models import Gazette
from gazettes.services import sources as sources_service
from gazettes.services.ingest import IngestService


class Command(BaseCommand):
    help = 'Rebuild the full-text search vectors'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all', action='store_true', default=False,
            help='reindex every gazette, not just unindexed ones',
        )
        parser.add_argument(
            '-s', '--src', action='append', dest='srcs', default=[],
            help='restrict to a gazette source (repeatable)',
        )
        parser.add_argument('--batch-size', type=int, default=200)

    def handle(self, *args, **options):
        for src in options['srcs']:
            if not sources_service.is_known_source(src):
                raise CommandError('unknown source %r' % src)

        queryset = Gazette.objects.all()
        if options['srcs']:
            queryset = queryset.filter(source__name__in=options['srcs'])
        if not options['all']:
            queryset = queryset.filter(search_vector__isnull=True)

        total = queryset.count()
        if not total:
            self.stdout.write('nothing to reindex')
            return

        self.stdout.write('reindexing %d gazette(s)…' % total)

        service = IngestService()
        done = failed = 0

        # Iterate with only the columns the vector needs; `text` alone can run
        # to megabytes, so loading whole rows would be wasteful.
        for gazette in queryset.only('id', 'relurl', 'text').iterator(
            chunk_size=options['batch_size']
        ):
            if service.update_search_vector(gazette):
                done += 1
            else:
                failed += 1
            if (done + failed) % options['batch_size'] == 0:
                self.stderr.write('… %d/%d' % (done + failed, total))

        message = 'reindexed %d, failed %d' % (done, failed)
        if failed:
            self.stdout.write(self.style.WARNING(message))
        else:
            self.stdout.write(self.style.SUCCESS(message))
