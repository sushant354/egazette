"""Creating and updating gazette records.

One service backs both ways data reaches the site:

  * ``manage.py ingest_gazettes`` walks a local gazette directory and passes
    relurls; the assets are already on disk and are read in place.
  * ``POST /api/ingest/`` receives the same assets as an upload; they are
    written into the site's data root first.

Both end up in :meth:`IngestService.ingest`, so the rules about what makes a
valid gazette live in exactly one place.

Metadata and the legallayout HTML are required -- a gazette with no HTML has
no text to index and is skipped, to be picked up on a later run once
``pdf2html -e legallayout`` has converted it. The raw PDF and the pymupdf
rendering are optional: they may be uploaded, or they may simply already exist
in a data root that the site can read.
"""

import logging
from dataclasses import dataclass, field

from django.conf import settings
from django.db import DatabaseError, IntegrityError, models, transaction
from django.db.models import Value
from django.contrib.postgres.search import SearchVector

from gazettes.models import Gazette, Source
from gazettes.services import metadata as metadata_service
from gazettes.services import render, sources, storage as storage_service

logger = logging.getLogger(__name__)

# Outcomes reported per gazette.
CREATED = 'created'
UPDATED = 'updated'
UNCHANGED = 'unchanged'
SKIPPED = 'skipped'
ERROR = 'error'


@dataclass
class IngestResult:
    relurl: str
    status: str
    identifier: str = ''
    reason: str = ''

    # True when the failure is in the submitted gazette rather than in the
    # site -- unparseable XML, a colliding identifier. The API turns this into
    # a 4xx so that the push tool reports it and moves on instead of retrying
    # a payload that can never succeed.
    client_error: bool = False

    @property
    def ok(self):
        return self.status in (CREATED, UPDATED, UNCHANGED)

    def as_dict(self):
        return {
            'relurl': self.relurl,
            'status': self.status,
            'identifier': self.identifier,
            'reason': self.reason,
        }


@dataclass
class IngestStats:
    counts: dict = field(default_factory=dict)

    def add(self, result):
        self.counts[result.status] = self.counts.get(result.status, 0) + 1
        return result

    def __str__(self):
        if not self.counts:
            return 'nothing to do'
        return ' '.join(
            '%s=%d' % (status, self.counts[status])
            for status in sorted(self.counts)
        )


class IngestService:
    def __init__(self, storage=None, ts_config=None, max_index_bytes=None,
                 max_text_chars=None):
        self.storage = storage or storage_service.default_storage()
        self.ts_config = ts_config or settings.GAZETTE_TS_CONFIG
        self.max_index_bytes = (
            max_index_bytes
            if max_index_bytes is not None
            else settings.GAZETTE_MAX_INDEX_BYTES
        )
        self.max_text_chars = (
            max_text_chars
            if max_text_chars is not None
            else settings.GAZETTE_MAX_TEXT_CHARS
        )
        self._source_cache = {}

    # -- sources -----------------------------------------------------------

    def get_source(self, srcname):
        """The Source row for a srcinfos key, created on first use.

        ``sync_sources`` normally creates these up front, but creating on
        demand means an ingest never fails just because the catalogue has not
        been synced since a new source was added to srcinfos.
        """
        if srcname in self._source_cache:
            return self._source_cache[srcname]

        info = sources.source_info(srcname)
        if info is None:
            return None

        source, _ = Source.objects.get_or_create(
            name=srcname,
            defaults={
                'title': info['title'],
                'authority': info['authority'],
                'languages': info['languages'],
                'ia_prefix': info['ia_prefix'],
                'start_date': info['start_date'],
            },
        )
        self._source_cache[srcname] = source
        return source

    # -- ingest ------------------------------------------------------------

    def ingest(self, relurl, metatags=None, html=None, pymupdf=None, raw=None,
               raw_extension=None, force=False):
        """Ingest one gazette. Never raises; failures come back as results.

        ``metatags``, ``html``, ``pymupdf`` and ``raw`` are optional uploaded
        payloads (bytes or a Django UploadedFile). Anything not supplied is
        looked for in the configured data roots.
        """
        try:
            return self._ingest(relurl, metatags, html, pymupdf, raw,
                                raw_extension, force)
        except (storage_service.InvalidRelurl,
                metadata_service.MetadataError) as exc:
            return IngestResult(str(relurl)[:512], ERROR, reason=str(exc),
                                client_error=True)
        except Exception as exc:
            logger.exception('Ingest failed for %s', relurl)
            return IngestResult(str(relurl)[:512], ERROR,
                                reason='%s: %s' % (type(exc).__name__, exc))

    def _ingest(self, relurl, metatags, html, pymupdf, raw, raw_extension,
                force):
        relurl = storage_service.validate_relurl(relurl)
        srcname = relurl.split('/')[0]

        source = self.get_source(srcname)
        if source is None:
            return IngestResult(relurl, SKIPPED,
                                reason='unknown source %r' % srcname)

        # --- metadata (required) ---
        if metatags is not None:
            metatags_bytes = _to_bytes(metatags)
            metainfo = metadata_service.parse_metainfo(metatags_bytes, relurl)
        else:
            metatags_bytes = self.storage.read('metatags', relurl)
            if metatags_bytes is None:
                return IngestResult(relurl, SKIPPED, reason='no metatags file')
            metainfo = metadata_service.parse_metainfo(metatags_bytes, relurl)

        # --- html (required) ---
        if html is not None:
            html_bytes = _to_bytes(html)
        else:
            html_bytes = self.storage.read('html', relurl)
            if html_bytes is None:
                return IngestResult(
                    relurl, SKIPPED,
                    reason='no legallayout html; run pdf2html -e legallayout',
                )
        if not html_bytes.strip():
            return IngestResult(relurl, SKIPPED, reason='html file is empty')

        # --- identifier ---
        identifier = sources.get_identifier(relurl, metainfo)
        if identifier is None:
            return IngestResult(
                relurl, SKIPPED,
                reason='could not build an Internet Archive identifier',
            )
        if len(identifier) > 255:
            return IngestResult(relurl, SKIPPED,
                                reason='identifier too long: %s' % identifier[:80])

        # --- persist uploaded assets ---
        # Assets that arrived over HTTP are written into the site's data root.
        # Assets that were already on disk stay where they are.
        if metatags is not None:
            self.storage.save('metatags', relurl, metatags_bytes)
        if html is not None:
            self.storage.save('html', relurl, html_bytes)
        if pymupdf is not None:
            self.storage.save('pymupdf', relurl, pymupdf)
        if raw is not None:
            self.storage.save('raw', relurl, raw, extension=raw_extension)

        html_hash = render.sha256(html_bytes)
        metadata_hash = render.sha256(metatags_bytes)

        pdf_size = self.storage.size('raw', relurl)
        asset_fields = {
            'has_pymupdf': self.storage.find('pymupdf', relurl) is not None,
            'has_pdf': pdf_size is not None,
            'pdf_bytes': pdf_size,
        }

        existing = Gazette.objects.filter(relurl=relurl).first()

        if (
            existing is not None
            and not force
            and existing.html_sha256 == html_hash
            and existing.metadata_sha256 == metadata_hash
            and existing.identifier == identifier
        ):
            # Content is byte-identical to what is already indexed. Still
            # refresh the asset flags, since a PDF or pymupdf rendering may
            # have shown up since the last run.
            changed = [
                name for name, value in asset_fields.items()
                if getattr(existing, name) != value
            ]
            if changed:
                for name, value in asset_fields.items():
                    setattr(existing, name, value)
                existing.save(update_fields=changed + ['updated_at'])
            return IngestResult(relurl, UNCHANGED, identifier=identifier)

        # --- text extraction ---
        text = render.extract_text(html_bytes)
        text, truncated = render.truncate_text(text, self.max_text_chars)

        fields = metadata_service.extract_fields(metainfo, source.title)
        fields.update(asset_fields)
        fields.update({
            'identifier': identifier,
            'source': source,
            'text': text,
            'text_truncated': truncated,
            'html_sha256': html_hash,
            'metadata_sha256': metadata_hash,
        })

        try:
            with transaction.atomic():
                gazette, created = Gazette.objects.update_or_create(
                    relurl=relurl, defaults=fields
                )
        except IntegrityError as exc:
            # The only unique constraint that another relurl can collide on is
            # the identifier; two relurls mapping to one identifier means the
            # source's identifier function needs a metadata tag this gazette
            # is missing.
            other = Gazette.objects.filter(identifier=identifier).exclude(
                relurl=relurl
            ).first()
            if other is not None:
                return IngestResult(
                    relurl, ERROR, identifier=identifier,
                    reason='identifier already used by %s' % other.relurl,
                    client_error=True,
                )
            return IngestResult(relurl, ERROR, identifier=identifier,
                                reason=str(exc))

        self.update_search_vector(gazette, text)

        return IngestResult(relurl, CREATED if created else UPDATED,
                            identifier=identifier)

    # -- indexing ----------------------------------------------------------

    def update_search_vector(self, gazette, text=None):
        """Rebuild one gazette's tsvector.

        Weighted so that a hit in the title outranks one in the subject, which
        outranks one in the issuing ministry, which outranks one buried in the
        body text.

        Postgres refuses a tsvector over 1MB. The body text is pre-truncated
        to stay well under that, but token-dense documents can still overflow,
        so an overflow is retried with progressively less text rather than
        losing the gazette from the index entirely.
        """
        if text is None:
            text = gazette.text or ''

        limit = self.max_index_bytes
        for attempt in range(4):
            body = render.index_text(text, limit)
            try:
                with transaction.atomic():
                    Gazette.objects.filter(pk=gazette.pk).update(
                        search_vector=(
                            SearchVector('title', weight='A',
                                         config=self.ts_config)
                            + SearchVector('subject', weight='B',
                                           config=self.ts_config)
                            + SearchVector('department', 'ministry', 'office',
                                           'gztype', weight='C',
                                           config=self.ts_config)
                            + SearchVector(
                                Value(body, output_field=models.TextField()),
                                weight='D', config=self.ts_config)
                        )
                    )
                return True
            except DatabaseError as exc:
                limit //= 2
                logger.warning(
                    'tsvector build failed for %s (%s); retrying with %d bytes',
                    gazette.relurl, exc, limit,
                )
                if attempt == 3 or limit < 1024:
                    logger.error('Giving up on tsvector for %s',
                                 gazette.relurl)
                    return False
        return False


def _to_bytes(payload):
    """Normalise an uploaded file or raw buffer to bytes."""
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode('utf-8')
    if hasattr(payload, 'read'):
        if hasattr(payload, 'seek'):
            payload.seek(0)
        return payload.read()
    raise TypeError('unsupported payload type %r' % type(payload))
