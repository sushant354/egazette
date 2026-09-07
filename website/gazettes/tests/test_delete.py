"""Tests for ``manage.py delete_gazettes``.

Rows are built directly rather than ingested from a data directory: what is
under test is which gazettes a set of options selects, and none of that
touches the files on disk.
"""

import datetime
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from gazettes.models import Bookmark, Gazette, Source


def make_source(name='central_extraordinary'):
    source, _created = Source.objects.get_or_create(
        name=name, defaults={'title': name.replace('_', ' ').title()}
    )
    return source


def make_gazette(relurl, source=None, date=None, created_at=None):
    """One indexed gazette, optionally backdated to when it was added.

    ``created_at`` is auto_now_add, so it can only be set by updating the row
    afterwards -- which is also the only way a test can pretend a gazette was
    ingested last week.
    """
    gazette = Gazette.objects.create(
        identifier=relurl.replace('/', '.'),
        relurl=relurl,
        source=source or make_source(),
        date=date,
        year=date.year if date else None,
        title='Gazette %s' % relurl,
    )
    if created_at is not None:
        Gazette.objects.filter(pk=gazette.pk).update(created_at=created_at)
        gazette.refresh_from_db()
    return gazette


def days_ago(days):
    return timezone.now() - datetime.timedelta(days=days)


class DeleteTestCase(TestCase):
    def run_command(self, *args, **options):
        out, err = StringIO(), StringIO()
        options.setdefault('stdout', out)
        options.setdefault('stderr', err)
        options.setdefault('interactive', False)
        call_command('delete_gazettes', *args, **options)
        return out.getvalue(), err.getvalue()

    def identifiers(self):
        return sorted(Gazette.objects.values_list('relurl', flat=True))


class SelectionTests(DeleteTestCase):
    def setUp(self):
        self.andhra = make_source('andhra')
        self.central = make_source('central_extraordinary')

        self.old = make_gazette(
            'central_extraordinary/2024-04-18/1', self.central,
            date=datetime.date(2024, 4, 18), created_at=days_ago(30),
        )
        self.new = make_gazette(
            'central_extraordinary/2026-02-05/2', self.central,
            date=datetime.date(2026, 2, 5), created_at=days_ago(0.5 / 24),
        )
        self.other_src = make_gazette(
            'andhra/2024-04-18/3', self.andhra,
            date=datetime.date(2024, 4, 18), created_at=days_ago(30),
        )

    def test_deletes_a_whole_source(self):
        self.run_command('-s', 'andhra')

        self.assertEqual(self.identifiers(),
                         sorted([self.old.relurl, self.new.relurl]))

    def test_deletes_by_gazette_date_range(self):
        self.run_command('-t', '01-01-2024', '-T', '31-12-2024')

        self.assertEqual(self.identifiers(), [self.new.relurl])

    def test_deletes_by_time_added(self):
        self.run_command('-l', '1')

        self.assertEqual(self.identifiers(),
                         sorted([self.old.relurl, self.other_src.relurl]))

    def test_added_since_and_before_bound_the_window(self):
        self.run_command('--added-since', '2020-01-01',
                         '--added-before', '2020-02-01')
        self.assertEqual(len(self.identifiers()), 3)

        since = (days_ago(31)).strftime('%Y-%m-%d %H:%M:%S')
        before = (days_ago(29)).strftime('%Y-%m-%d %H:%M:%S')
        self.run_command('--added-since', since, '--added-before', before)

        self.assertEqual(self.identifiers(), [self.new.relurl])

    def test_filters_combine_with_and(self):
        # The old central gazette matches the source, the new one the window;
        # together they select nothing.
        self.run_command('-s', 'central_extraordinary', '-l', '1',
                         '-T', '31-12-2024')

        self.assertEqual(len(self.identifiers()), 3)

    def test_deletes_a_single_relurl(self):
        self.run_command('--relurl', self.new.relurl)

        self.assertEqual(self.identifiers(),
                         sorted([self.old.relurl, self.other_src.relurl]))

    def test_deletes_a_single_identifier(self):
        self.run_command('--identifier', self.old.identifier)

        self.assertEqual(self.identifiers(),
                         sorted([self.other_src.relurl, self.new.relurl]))

    def test_limit_caps_the_delete_at_the_newest(self):
        self.run_command('-s', 'central_extraordinary', '--limit', '1')

        self.assertEqual(self.identifiers(),
                         sorted([self.old.relurl, self.other_src.relurl]))

    def test_all_empties_the_index(self):
        self.run_command('--all')

        self.assertEqual(self.identifiers(), [])

    def test_no_filter_is_refused(self):
        with self.assertRaises(CommandError):
            self.run_command()

        self.assertEqual(len(self.identifiers()), 3)

    def test_source_missing_from_srcinfos_is_still_deletable(self):
        # Nothing about this name is in the catalogue; the rows are still the
        # ones somebody is trying to get rid of.
        retired = Source.objects.create(name='retired_series', title='Retired')
        make_gazette('retired_series/2024-01-01/9', retired)

        with mock.patch('gazettes.services.sources.is_known_source',
                        return_value=False):
            self.run_command('-s', 'retired_series')

        self.assertEqual(len(self.identifiers()), 3)

    def test_source_with_no_rows_warns_and_deletes_the_rest(self):
        _out, err = self.run_command('-s', 'andhra', '-s', 'not_a_source')

        self.assertIn('not_a_source', err)
        self.assertEqual(self.identifiers(),
                         sorted([self.old.relurl, self.new.relurl]))

    def test_source_with_no_rows_deletes_nothing_on_its_own(self):
        out, _err = self.run_command('-s', 'not_a_source')

        self.assertIn('nothing to delete', out)
        self.assertEqual(len(self.identifiers()), 3)

    def test_reversed_date_range_is_refused(self):
        with self.assertRaises(CommandError):
            self.run_command('-t', '31-12-2024', '-T', '01-01-2024')

    def test_days_and_timestamps_are_alternatives(self):
        with self.assertRaises(CommandError):
            self.run_command('-l', '1', '--added-since', '2026-01-01')


class OutputTests(DeleteTestCase):
    def setUp(self):
        self.gazette = make_gazette('andhra/2024-04-18/1', make_source('andhra'))

    def test_dry_run_lists_without_deleting(self):
        out, _err = self.run_command('-s', 'andhra', '--dry-run')

        self.assertIn(self.gazette.identifier, out)
        self.assertIn('would be deleted', out)
        self.assertEqual(Gazette.objects.count(), 1)

    def test_nothing_to_delete_says_so(self):
        out, _err = self.run_command('-s', 'central_extraordinary')

        self.assertIn('nothing to delete', out)

    def test_confirmation_aborts_on_anything_but_yes(self):
        with mock.patch('builtins.input', return_value='no'):
            out, _err = self.run_command('-s', 'andhra', interactive=True)

        self.assertIn('cancelled', out)
        self.assertEqual(Gazette.objects.count(), 1)

    def test_confirmation_proceeds_on_yes(self):
        with mock.patch('builtins.input', return_value='yes'):
            self.run_command('-s', 'andhra', interactive=True)

        self.assertEqual(Gazette.objects.count(), 0)


class CascadeTests(DeleteTestCase):
    def test_bookmarks_go_with_the_gazette_and_are_reported(self):
        gazette = make_gazette('andhra/2024-04-18/1', make_source('andhra'))
        user = get_user_model().objects.create_user(
            username='reader', password='secret'
        )
        Bookmark.objects.create(user=user, gazette=gazette)

        out, _err = self.run_command('-s', 'andhra')

        self.assertEqual(Bookmark.objects.count(), 0)
        self.assertIn('1 bookmark(s)', out)

    def test_counters_are_refreshed(self):
        source = make_source('andhra')
        make_gazette('andhra/2024-04-18/1', source,
                     date=datetime.date(2024, 4, 18))
        call_command('sync_sources', '--counts-only', stdout=StringIO())
        source.refresh_from_db()
        self.assertEqual(source.gazette_count, 1)

        self.run_command('-s', 'andhra')

        source.refresh_from_db()
        self.assertEqual(source.gazette_count, 0)
        self.assertIsNone(source.latest_date)


class BatchTests(DeleteTestCase):
    def test_deletes_more_rows_than_one_batch_holds(self):
        source = make_source('andhra')
        for num in range(7):
            make_gazette('andhra/2024-04-18/%d' % num, source)

        with mock.patch(
            'gazettes.management.commands.delete_gazettes.BATCH_SIZE', 2
        ):
            out, err = self.run_command('-s', 'andhra')

        self.assertEqual(Gazette.objects.count(), 0)
        self.assertIn('deleted 7 gazette(s)', out)
        self.assertIn('/7 deleted', err)
