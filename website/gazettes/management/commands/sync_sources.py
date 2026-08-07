"""Rebuild the Source catalogue from the scraper's srcinfos.

Run after adding a source to ``egazette/srcs/datasrcs_info.py``, and any time
the per-source counters on the browse pages look stale.
"""

from django.core.management.base import BaseCommand

from gazettes.services import sources


class Command(BaseCommand):
    help = 'Sync gazette sources from egazette.srcs.datasrcs_info.srcinfos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--counts-only', action='store_true',
            help='only refresh the per-source counters, skip the catalogue',
        )

    def handle(self, *args, **options):
        if not options['counts_only']:
            created, updated = sources.sync_sources()
            self.stdout.write(
                'sources: %d created, %d updated' % (created, updated)
            )

        changed = sources.refresh_counts()
        self.stdout.write(self.style.SUCCESS(
            'counters refreshed for %d source(s)' % changed
        ))
