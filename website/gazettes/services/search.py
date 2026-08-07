"""Querying the gazette archive.

Full text lives in a weighted tsvector built at ingest (see
``ingest.update_search_vector``), so searching is a GIN index lookup with a
rank, and the metadata filters are ordinary column predicates on top.

Queries use Postgres' ``websearch_to_tsquery`` syntax, which is what readers
already expect from a search box: quoted phrases, ``OR``, and ``-`` to
exclude.
"""

import datetime
from dataclasses import dataclass, field

from django.conf import settings
from django.contrib.postgres.search import (
    SearchHeadline,
    SearchQuery,
    SearchRank,
)
from django.db.models import Count, F
from django.utils.html import escape
from django.utils.safestring import mark_safe

from gazettes.models import Gazette, Source

# ts_headline inserts its delimiters into raw document text without escaping
# it, so asking Postgres for '<mark>' directly would let gazette content that
# happens to contain markup through into the page. Instead it marks hits with
# control characters that cannot occur in extracted text, and the result is
# HTML-escaped here before those sentinels become tags.
HL_START = '\x02'
HL_STOP = '\x03'

ORDER_RELEVANCE = 'relevance'
ORDER_NEWEST = 'newest'
ORDER_OLDEST = 'oldest'

ORDER_CHOICES = [
    (ORDER_RELEVANCE, 'Relevance'),
    (ORDER_NEWEST, 'Newest first'),
    (ORDER_OLDEST, 'Oldest first'),
]


@dataclass
class SearchCriteria:
    q: str = ''
    sources: list = field(default_factory=list)
    from_date: datetime.date = None
    to_date: datetime.date = None
    year: int = None
    order: str = ''

    @property
    def has_query(self):
        return bool(self.q and self.q.strip())

    @property
    def is_empty(self):
        return not (
            self.has_query
            or self.sources
            or self.from_date
            or self.to_date
            or self.year
        )

    def effective_order(self):
        if self.order in dict(ORDER_CHOICES):
            return self.order
        return ORDER_RELEVANCE if self.has_query else ORDER_NEWEST


class SearchService:
    def __init__(self, ts_config=None):
        self.ts_config = ts_config or settings.GAZETTE_TS_CONFIG

    def build_query(self, text):
        return SearchQuery(text, config=self.ts_config, search_type='websearch')

    def search(self, criteria):
        """A queryset of matching gazettes, ordered as the criteria ask."""
        queryset = Gazette.objects.with_source()
        queryset = self._apply_filters(queryset, criteria)

        order = criteria.effective_order()

        if criteria.has_query:
            query = self.build_query(criteria.q)
            queryset = queryset.filter(search_vector=query)
            if order == ORDER_RELEVANCE:
                # cover_density rewards hits that sit close together, which
                # matters a lot on documents this long.
                queryset = queryset.annotate(
                    rank=SearchRank(F('search_vector'), query,
                                    cover_density=True)
                ).order_by('-rank', F('date').desc(nulls_last=True), '-id')
                return queryset

        if order == ORDER_OLDEST:
            return queryset.order_by(F('date').asc(nulls_last=True), 'id')
        return queryset.order_by(F('date').desc(nulls_last=True), '-id')

    def _apply_filters(self, queryset, criteria):
        if criteria.sources:
            queryset = queryset.filter(source__name__in=criteria.sources)
        if criteria.from_date:
            queryset = queryset.filter(date__gte=criteria.from_date)
        if criteria.to_date:
            queryset = queryset.filter(date__lte=criteria.to_date)
        if criteria.year:
            queryset = queryset.filter(year=criteria.year)
        return queryset

    # -- highlighting ------------------------------------------------------

    def headlines(self, gazettes, criteria):
        """Map of gazette pk -> highlighted snippet.

        Run against only the gazettes on the current page: ts_headline has to
        re-read and re-parse the document text, which is far too expensive to
        annotate onto the whole result set.
        """
        if not criteria.has_query:
            return {}

        gazettes = list(gazettes)
        if not gazettes:
            return {}

        query = self.build_query(criteria.q)
        rows = (
            Gazette.objects.filter(pk__in=[g.pk for g in gazettes])
            .annotate(
                headline=SearchHeadline(
                    'text',
                    query,
                    config=self.ts_config,
                    start_sel=HL_START,
                    stop_sel=HL_STOP,
                    max_words=40,
                    min_words=20,
                    max_fragments=3,
                    fragment_delimiter=' … ',
                )
            )
            .values_list('pk', 'headline')
        )
        return {pk: render_highlight(headline) for pk, headline in rows}

    # -- facets ------------------------------------------------------------

    def source_facets(self, criteria, limit=None):
        """Result counts per source for the current query.

        The source filter itself is left out so that the facet list keeps
        showing the other sources a reader could switch to.
        """
        without_source = SearchCriteria(
            q=criteria.q,
            sources=[],
            from_date=criteria.from_date,
            to_date=criteria.to_date,
            year=criteria.year,
        )
        queryset = self._apply_filters(Gazette.objects.all(), without_source)
        if criteria.has_query:
            queryset = queryset.filter(search_vector=self.build_query(criteria.q))

        rows = (
            queryset.values('source__name', 'source__title')
            .annotate(total=Count('id'))
            .order_by('-total')
        )
        if limit:
            rows = rows[:limit]

        selected = set(criteria.sources)
        return [
            {
                'name': row['source__name'],
                'title': row['source__title'],
                'total': row['total'],
                'selected': row['source__name'] in selected,
            }
            for row in rows
        ]

    def year_facets(self, criteria, limit=None):
        """Result counts per year, newest first."""
        queryset = self._apply_filters(Gazette.objects.all(), criteria)
        if criteria.has_query:
            queryset = queryset.filter(search_vector=self.build_query(criteria.q))

        rows = (
            queryset.exclude(year__isnull=True)
            .values('year')
            .annotate(total=Count('id'))
            .order_by('-year')
        )
        if limit:
            rows = rows[:limit]
        return list(rows)


def render_highlight(headline):
    """Escape a ts_headline result, then turn its sentinels into <mark>."""
    if not headline:
        return ''
    escaped = escape(headline)
    escaped = escaped.replace(escape(HL_START), '<mark>')
    escaped = escaped.replace(escape(HL_STOP), '</mark>')
    # escape() leaves the control characters alone, but be explicit in case a
    # future Django escapes them.
    escaped = escaped.replace(HL_START, '<mark>').replace(HL_STOP, '</mark>')
    return mark_safe(escaped)


def archive_stats():
    """Headline numbers for the home page."""
    from django.db.models import Max, Min

    aggregate = Gazette.objects.aggregate(
        total=Count('id'), earliest=Min('date'), latest=Max('date')
    )
    aggregate['sources'] = (
        Source.objects.filter(gazette_count__gt=0).count()
    )
    return aggregate
