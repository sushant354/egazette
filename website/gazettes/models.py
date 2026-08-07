"""Database model for the gazette archive.

Two tables carry the site. ``Source`` mirrors an entry of
``egazette.srcs.datasrcs_info.srcinfos`` (one publishing series, e.g. the
Extraordinary Gazette of India) and is rebuilt from that dict rather than
edited by hand. ``Gazette`` is one published issue, keyed by the same
identifier the scraper uses when it uploads to the Internet Archive.

Gazette metadata is deeply heterogeneous across the ~55 sources -- West Bengal
archive scans carry a ``bookid`` and no date at all, while the central gazette
carries a ministry, department and office. The columns below are the fields
worth querying and faceting on; everything the scraper recorded is preserved
verbatim in ``metadata`` so nothing is lost in translation.
"""

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.urls import reverse


class Source(models.Model):
    """A gazette publishing series, synced from ``srcinfos``."""

    # srcinfos key, e.g. 'central_extraordinary'. This is also the first
    # component of every relurl belonging to the source.
    name = models.CharField(max_length=64, unique=True)

    # srcinfos 'category', e.g. 'Extrordinary Gazette of India'.
    title = models.CharField(max_length=255)

    # srcinfos 'source', e.g. 'Government of India'. Absent for a few archival
    # collections that are not published by a government press.
    authority = models.CharField(max_length=255, blank=True)

    # ISO 639-2 codes from srcinfos, e.g. ['eng', 'hin'].
    languages = models.JSONField(default=list, blank=True)

    # srcinfos prefix used to build Internet Archive identifiers.
    ia_prefix = models.CharField(max_length=128, blank=True)

    # Earliest issue the scraper attempts to fetch, when srcinfos declares one.
    start_date = models.DateField(null=True, blank=True)

    # Denormalised counters, refreshed by `manage.py sync_sources`. They back
    # the browse pages, where a COUNT(*) over the gazette table per source
    # would otherwise run on every request.
    gazette_count = models.PositiveIntegerField(default=0)
    earliest_date = models.DateField(null=True, blank=True)
    latest_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['title']

    def __str__(self):
        return self.title or self.name

    def get_absolute_url(self):
        return reverse('gazettes:source_detail', args=[self.name])


class GazetteQuerySet(models.QuerySet):
    def with_source(self):
        return self.select_related('source')


class Gazette(models.Model):
    """One published gazette issue."""

    # The Internet Archive identifier, from datasrcs_info.get_identifier().
    # It is the site's public key: /details/<identifier>/.
    identifier = models.CharField(max_length=255, unique=True)

    # Path of the gazette within the scraper's data directory, without the
    # file extension, e.g. 'central_extraordinary/2024-04-18/253767'. Assets
    # for the issue live at <root>/<kind>/<relurl>.<ext>.
    relurl = models.CharField(max_length=512, unique=True)

    source = models.ForeignKey(
        Source, on_delete=models.CASCADE, related_name='gazettes'
    )

    # Publication date. Null for archival collections catalogued by year only.
    date = models.DateField(null=True, blank=True)
    # Always populated when either a date or a year tag was available, so that
    # year faceting works uniformly across dated and undated sources.
    year = models.PositiveSmallIntegerField(null=True, blank=True)

    # Best available human-readable heading, derived at ingest from the
    # title/subject tags with a constructed fallback so no issue is untitled.
    title = models.TextField()

    subject = models.TextField(blank=True)
    gznum = models.CharField(max_length=255, blank=True)
    gztype = models.CharField(max_length=255, blank=True)
    department = models.CharField(max_length=512, blank=True)
    ministry = models.CharField(max_length=512, blank=True)
    office = models.CharField(max_length=512, blank=True)
    partnum = models.CharField(max_length=255, blank=True)
    notification_num = models.CharField(max_length=255, blank=True)
    refnum = models.CharField(max_length=255, blank=True)

    # URL the scraper downloaded the issue from.
    source_url = models.TextField(blank=True)

    # Every tag the scraper recorded, including the ones promoted to columns
    # above. Dates are serialised as ISO strings.
    metadata = models.JSONField(default=dict, blank=True)

    # Plain text extracted from the legallayout HTML. Backs both the tsvector
    # and the highlighted snippets on the results page.
    text = models.TextField(blank=True)
    text_truncated = models.BooleanField(default=False)

    search_vector = SearchVectorField(null=True, editable=False)

    # Which renderings exist on disk for this issue. The legallayout HTML is
    # mandatory (a gazette is not ingested without it); the PDF and the pymupdf
    # rendering are optional and may live in a read-only data root.
    has_pymupdf = models.BooleanField(default=False)
    has_pdf = models.BooleanField(default=False)
    pdf_bytes = models.BigIntegerField(null=True, blank=True)

    # sha256 of the source HTML, so a repeated push of unchanged content skips
    # the expensive text extraction and reindex.
    html_sha256 = models.CharField(max_length=64, blank=True)
    metadata_sha256 = models.CharField(max_length=64, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = GazetteQuerySet.as_manager()

    class Meta:
        ordering = ['-date', '-id']
        indexes = [
            GinIndex(fields=['search_vector'], name='gazette_search_gin'),
            models.Index(fields=['-date'], name='gazette_date_desc'),
            models.Index(fields=['source', '-date'], name='gazette_source_date'),
            models.Index(fields=['year'], name='gazette_year'),
        ]

    def __str__(self):
        return self.identifier

    def get_absolute_url(self):
        return reverse('gazettes:detail', args=[self.identifier])

    @property
    def display_date(self):
        """Date if known, otherwise the year, otherwise nothing."""
        if self.date:
            return self.date.strftime('%d %B %Y')
        if self.year:
            return str(self.year)
        return ''

    def metadata_items(self):
        """Extra metadata tags that have no column of their own.

        Used by the detail page so that source-specific fields (bookid,
        division, creator, keywords ...) still surface without the template
        needing to know which source it is looking at.
        """
        promoted = {
            'title', 'subject', 'gznum', 'gztype', 'department', 'ministry',
            'office', 'partnum', 'notification_num', 'refnum', 'url', 'href',
            'date', 'year', 'links', 'linknames', 'linkids',
        }
        items = []
        for key, value in sorted(self.metadata.items()):
            if key in promoted or value in (None, '', [], {}):
                continue
            if isinstance(value, (dict, list)):
                continue
            items.append((key.replace('_', ' ').title(), value))
        return items
