"""Parsing metatags XML into normalised Gazette fields.

The scraper writes one XML file per gazette via ``egazette.utils.xml_ops``, and
its tag set differs from source to source: the central gazette carries
ministry/department/office, Goa carries a series and number, the West Bengal
Secretariat Library scans carry a bookid and a year but no date at all. This
module reads whatever is there, promotes the tags worth querying into model
columns, and keeps the rest for the detail page.

Parsing goes through xml_ops rather than a second XML reader so that the site
sees exactly what ``GazetteIA`` sees -- including the MetaInfo instance the
identifier functions expect, some of which call ``metainfo.get_date()``.
"""

import datetime
import logging

from egazette.utils import xml_ops

logger = logging.getLogger(__name__)

# Tags promoted to their own column, mapped to the model field name.
PROMOTED_FIELDS = {
    'subject': 'subject',
    'gznum': 'gznum',
    'gztype': 'gztype',
    'department': 'department',
    'ministry': 'ministry',
    'office': 'office',
    'partnum': 'partnum',
    'notification_num': 'notification_num',
    'refnum': 'refnum',
}

# Longest value accepted into a CharField column; anything longer is kept only
# in the metadata JSON, since these are meant to be short identifiers and an
# over-long value is almost always a parsing artefact at the source.
MAX_CHAR_LENGTHS = {
    'gznum': 255,
    'gztype': 255,
    'department': 512,
    'ministry': 512,
    'office': 512,
    'partnum': 255,
    'notification_num': 255,
    'refnum': 255,
}


class MetadataError(ValueError):
    pass


def parse_metainfo(data, relurl):
    """Parse metatags XML bytes into a MetaInfo, or raise MetadataError.

    ``data`` may be bytes or str; xml_ops needs bytes for minidom.
    """
    if isinstance(data, str):
        data = data.encode('utf-8')

    try:
        metainfo = xml_ops.xml_to_tagdict(relurl, data)
    except (AttributeError, TypeError) as exc:
        # xml_to_tagdict assumes the document element has children; a
        # degenerate file like '<document/>' makes it return a bare string and
        # then fail on .items(). Report that as bad metadata rather than
        # letting an AttributeError escape as a 500.
        raise MetadataError(
            'malformed metatags XML for %s: %s' % (relurl, exc)
        ) from exc

    if metainfo is None:
        raise MetadataError('could not parse metatags XML for %s' % relurl)
    if not hasattr(metainfo, 'items'):
        raise MetadataError('metatags XML for %s has no tags' % relurl)
    return metainfo


def read_metainfo(storage, relurl):
    """Parse the metatags file for a relurl from disk, or return None."""
    data = storage.read('metatags', relurl)
    if data is None:
        return None
    return parse_metainfo(data, relurl)


def _as_text(value):
    """Flatten a metainfo value to a display string.

    Values are usually strings, but a repeated tag becomes a list and a nested
    tag becomes a dict; neither belongs in a CharField.
    """
    if value is None:
        return ''
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return ''


def _as_year(value):
    text = _as_text(value)
    if not text.isdigit():
        return None
    year = int(text)
    # Guard against a stray page number or id landing in the year tag; the
    # oldest thing in the archive is an 18th century Bengal gazette.
    if 1600 <= year <= 2200:
        return year
    return None


def jsonify(metainfo):
    """A JSON-serialisable copy of the metainfo, dates as ISO strings."""

    def convert(value):
        if isinstance(value, (datetime.datetime, datetime.date)):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(k): convert(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [convert(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    return {str(key): convert(value) for key, value in metainfo.items()}


def build_title(metainfo, source_title, date, year):
    """The heading shown for a gazette.

    Prefers the source's own title tag, falls back to the subject, and finally
    constructs one from the series name and date so that no gazette in the
    archive is listed as untitled.
    """
    title = _as_text(metainfo.get('title'))
    if title:
        return title

    subject = _as_text(metainfo.get('subject'))
    if subject:
        return subject

    parts = [source_title]

    gznum = _as_text(metainfo.get('gznum'))
    partnum = _as_text(metainfo.get('partnum'))
    if gznum:
        parts.append('No. %s' % gznum)
    if partnum:
        parts.append('Part %s' % partnum)

    if date:
        parts.append(date.strftime('%d %B %Y'))
    elif year:
        parts.append(str(year))

    return ', '.join(part for part in parts if part)


def extract_fields(metainfo, source_title):
    """Model field values for a parsed metainfo.

    Returns a dict ready to be splatted into Gazette(...) -- everything except
    identifier, relurl, source and the text/search columns.
    """
    date = metainfo.get('date')
    if isinstance(date, datetime.datetime):
        date = date.date()
    elif not isinstance(date, datetime.date):
        date = None

    year = _as_year(metainfo.get('year'))
    if year is None and date is not None:
        year = date.year

    fields = {
        'date': date,
        'year': year,
        'source_url': _as_text(metainfo.get('url')) or _as_text(metainfo.get('href')),
        'metadata': jsonify(metainfo),
    }

    for tag, field in PROMOTED_FIELDS.items():
        value = _as_text(metainfo.get(tag))
        limit = MAX_CHAR_LENGTHS.get(field)
        if limit and len(value) > limit:
            # Keep the column clean; the full value survives in metadata.
            value = ''
        fields[field] = value

    fields['title'] = build_title(metainfo, source_title, date, year)

    return fields
