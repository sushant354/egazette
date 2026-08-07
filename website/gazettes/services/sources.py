"""The gazette source catalogue, read from the scraper's ``srcinfos``.

``egazette.srcs.datasrcs_info`` already describes every gazette series the
scraper knows about -- its publishing authority, languages, Internet Archive
prefix and the function that turns a relurl into an identifier. Rather than
duplicating any of that in the website, this module reads it directly and
syncs it into the ``Source`` table, which exists only so that the site can
join, count and facet on it.

Re-run ``manage.py sync_sources`` after srcinfos changes.
"""

import logging

from egazette.srcs import datasrcs_info

logger = logging.getLogger(__name__)

# ISO 639-2 codes used by srcinfos, spelled out for display.
LANGUAGE_NAMES = {
    'eng': 'English',
    'hin': 'Hindi',
    'ben': 'Bengali',
    'mar': 'Marathi',
    'tel': 'Telugu',
    'tam': 'Tamil',
    'kan': 'Kannada',
    'mal': 'Malayalam',
    'guj': 'Gujarati',
    'ori': 'Odia',
    'pan': 'Punjabi',
    'asm': 'Assamese',
    'urd': 'Urdu',
    'san': 'Sanskrit',
    'nep': 'Nepali',
    'kok': 'Konkani',
    'mni': 'Manipuri',
    'bod': 'Bodo',
    'doi': 'Dogri',
    'kas': 'Kashmiri',
    'mai': 'Maithili',
    'sat': 'Santali',
    'snd': 'Sindhi',
    'fre': 'French',
    'ita': 'Italian',
    'por': 'Portuguese',
}


def language_name(code):
    return LANGUAGE_NAMES.get(code, code.upper())


def language_names(codes):
    return [language_name(code) for code in codes or []]


def source_names():
    """Every srcinfos key, sorted."""
    return sorted(datasrcs_info.srcinfos)


def is_known_source(srcname):
    return srcname in datasrcs_info.srcinfos


def source_info(srcname):
    """Normalised srcinfos entry, or None if the source is unknown.

    srcinfos entries are sparse -- most omit 'source', some omit 'prefix' (it
    is then derived) and only a few declare a 'start_date' -- so this fills in
    the gaps once here instead of at every call site.
    """
    srcinfo = datasrcs_info.srcinfos.get(srcname)
    if srcinfo is None:
        return None

    start_date = srcinfo.get('start_date')
    return {
        'name': srcname,
        'title': srcinfo.get('category') or srcname.replace('_', ' ').title(),
        'authority': srcinfo.get('source', ''),
        'languages': list(srcinfo.get('languages', [])),
        'ia_prefix': datasrcs_info.get_prefix(srcname),
        'start_date': start_date.date() if start_date is not None else None,
    }


def get_identifier(relurl, metainfo):
    """Internet Archive identifier for a gazette.

    Delegates to ``datasrcs_info.get_identifier`` -- the same function
    ``GazetteIA.get_identifier`` uses -- so the website and the archive agree
    on identifiers. Returns None when the source's identifier function cannot
    build one (a few need metadata tags that are occasionally missing).
    """
    try:
        identifier = datasrcs_info.get_identifier(relurl, metainfo)
    except Exception:
        logger.warning('Could not build identifier for %s', relurl,
                       exc_info=True)
        return None

    if not identifier or not isinstance(identifier, str):
        return None
    return identifier


def sync_sources():
    """Upsert a Source row for every srcinfos entry.

    Returns (created, updated).
    """
    from gazettes.models import Source

    created = updated = 0
    for srcname in source_names():
        info = source_info(srcname)
        obj, was_created = Source.objects.update_or_create(
            name=srcname,
            defaults={
                'title': info['title'],
                'authority': info['authority'],
                'languages': info['languages'],
                'ia_prefix': info['ia_prefix'],
                'start_date': info['start_date'],
            },
        )
        created += was_created
        updated += not was_created

    return created, updated


def refresh_counts():
    """Recompute the denormalised per-source counters.

    Cheap enough to run at the end of every ingest batch.
    """
    from django.db.models import Count, Max, Min

    from gazettes.models import Gazette, Source

    stats = {
        row['source_id']: row
        for row in Gazette.objects.values('source_id').annotate(
            total=Count('id'), earliest=Min('date'), latest=Max('date')
        )
    }

    to_update = []
    for source in Source.objects.all():
        row = stats.get(source.pk)
        total = row['total'] if row else 0
        earliest = row['earliest'] if row else None
        latest = row['latest'] if row else None
        if (
            source.gazette_count != total
            or source.earliest_date != earliest
            or source.latest_date != latest
        ):
            source.gazette_count = total
            source.earliest_date = earliest
            source.latest_date = latest
            to_update.append(source)

    if to_update:
        Source.objects.bulk_update(
            to_update, ['gazette_count', 'earliest_date', 'latest_date']
        )
    return len(to_update)
