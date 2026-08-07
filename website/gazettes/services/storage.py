"""Locating and writing gazette assets on disk.

The scraper's data directory has one subdirectory per rendering, each mirroring
the same relurl tree::

    <root>/metatags/<relurl>.xml     scraped metadata
    <root>/raw/<relurl>.<ext>        the gazette as published (usually .pdf)
    <root>/html/<relurl>.html        legallayout HTML  - displayed and indexed
    <root>/pymupdf/<relurl>.html     pymupdf HTML      - alternate view only

The site keeps that exact layout so that a deployment sharing a host with the
scraper can read the existing tree in place: list it in
``GAZETTE_DATA_ROOTS`` and the 658GB of PDFs and 886GB of pymupdf renderings
never need to be copied or uploaded. Roots are searched in order, so a small
writable root holding uploads can sit in front of a large read-only archive.
"""

import glob
import os
import re

from django.conf import settings

# Subdirectory and canonical extension for each rendering. A None extension
# means the extension varies and has to be discovered by globbing (raw files
# are usually PDFs but the scraper stores whatever the source served).
ASSET_KINDS = {
    'metatags': ('metatags', '.xml'),
    'html': ('html', '.html'),
    'pymupdf': ('pymupdf', '.html'),
    'raw': ('raw', None),
}

# A relurl is '<src>/<...>/<name>' built from scraped path components. Allowing
# only these characters, and rejecting any '..' segment, is what keeps an
# uploaded relurl from escaping the data root.
RELURL_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._\-]*(?:/[A-Za-z0-9._\-]+)+$')


class InvalidRelurl(ValueError):
    pass


def validate_relurl(relurl):
    """Return the relurl unchanged, or raise InvalidRelurl.

    Called on every path that comes from outside the process -- most
    importantly the ingest endpoint, where the relurl decides where an
    uploaded file is written.
    """
    if not relurl or not isinstance(relurl, str):
        raise InvalidRelurl('relurl is required')

    relurl = relurl.strip().strip('/')

    if not RELURL_RE.match(relurl):
        raise InvalidRelurl('malformed relurl: %r' % relurl)

    if any(part in ('.', '..') for part in relurl.split('/')):
        raise InvalidRelurl('relurl may not contain relative segments: %r' % relurl)

    if len(relurl) > 512:
        raise InvalidRelurl('relurl too long: %r' % relurl[:80])

    return relurl


def source_of(relurl):
    """The srcinfos key a relurl belongs to (its first path component)."""
    return validate_relurl(relurl).split('/')[0]


class AssetStorage:
    """Finds gazette assets across the configured data roots."""

    def __init__(self, roots=None, write_root=None):
        if roots is None:
            roots = settings.GAZETTE_DATA_ROOTS
        self.roots = [str(root) for root in roots]

        if write_root is None:
            write_root = settings.GAZETTE_WRITE_ROOT
        self.write_root = str(write_root)

    # -- reading -----------------------------------------------------------

    def _candidate_paths(self, kind, relurl):
        subdir, extension = ASSET_KINDS[kind]
        for root in self.roots:
            base = os.path.join(root, subdir, relurl)
            if extension:
                yield base + extension
            else:
                # Raw files keep whatever extension the download had. Sort so
                # the choice is stable when a source served more than one.
                for path in sorted(glob.glob(glob.escape(base) + '.*')):
                    yield path

    def find(self, kind, relurl):
        """Absolute path to an asset, or None if no root has it."""
        relurl = validate_relurl(relurl)
        for path in self._candidate_paths(kind, relurl):
            if os.path.isfile(path):
                return path
        return None

    def read(self, kind, relurl):
        """Asset contents as bytes, or None if it does not exist."""
        path = self.find(kind, relurl)
        if path is None:
            return None
        with open(path, 'rb') as handle:
            return handle.read()

    def read_text(self, kind, relurl, encoding='utf-8'):
        data = self.read(kind, relurl)
        if data is None:
            return None
        return data.decode(encoding, errors='replace')

    def size(self, kind, relurl):
        path = self.find(kind, relurl)
        if path is None:
            return None
        return os.path.getsize(path)

    # -- writing -----------------------------------------------------------

    def path_for_write(self, kind, relurl, extension=None):
        """Where an uploaded asset of this kind would be written."""
        relurl = validate_relurl(relurl)
        subdir, default_extension = ASSET_KINDS[kind]
        if extension is None:
            extension = default_extension or '.pdf'
        if not extension.startswith('.'):
            extension = '.' + extension

        path = os.path.join(self.write_root, subdir, relurl + extension)

        # Belt and braces: even though validate_relurl has already rejected
        # traversal, confirm the resolved path stays under the write root.
        root = os.path.realpath(os.path.join(self.write_root, subdir))
        resolved = os.path.realpath(path)
        if resolved != root and not resolved.startswith(root + os.sep):
            raise InvalidRelurl('relurl escapes the data root: %r' % relurl)

        return path

    def save(self, kind, relurl, data, extension=None):
        """Write an asset and return its path.

        Writes to a temporary file in the same directory and renames it into
        place, so a reader never sees a half-written gazette.
        """
        path = self.path_for_write(kind, relurl, extension)
        os.makedirs(os.path.dirname(path), exist_ok=True)

        tmp_path = '%s.tmp.%d' % (path, os.getpid())
        try:
            with open(tmp_path, 'wb') as handle:
                if hasattr(data, 'chunks'):
                    # A Django UploadedFile: stream it rather than materialise
                    # a few hundred megabytes of PDF in memory.
                    for chunk in data.chunks():
                        handle.write(chunk)
                elif hasattr(data, 'read'):
                    while True:
                        chunk = data.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
                else:
                    handle.write(data)
            os.replace(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

        return path


def default_storage():
    return AssetStorage()
