"""Upload gazettes from a data directory to the website.

This is the tool half of the website's update path. It runs on the machine
that holds the gazette data (typically the one running sync.py), walks the
data directory the same way pdf2html.py does, and posts each gazette to the
site's ``/api/ingest/`` endpoint. The site feeds them to the same
IngestService that its local ``manage.py ingest_gazettes`` uses, so pushing
and local ingest produce identical records.

Metadata and the legallayout HTML are always sent -- they are what the site
indexes, and a gazette without HTML is skipped here rather than rejected
there. The raw PDF and the pymupdf rendering are large and optional: pass
``--with-pdf`` / ``--with-pymupdf`` to upload them, or leave them out when the
site can already read them from a shared data root.

Before uploading, the tool asks the site which of the next batch of gazettes
it already holds and at what content hash, so an unchanged gazette is never
re-uploaded.

    python -m egazette.tools.push_gazettes -D /home/sushant/public/gzdl \\
        --endpoint https://gazettes.example.org --token "$EGAZETTE_TOKEN" \\
        -s andhra -t 01-01-2018 -T 31-12-2018

Run from the directory that contains the ``egazette`` package. The token may
also come from the EGAZETTE_INGEST_TOKEN environment variable.
"""

import argparse
import datetime
import hashlib
import logging
import os
import re
import sys
import time

import requests

logger = logging.getLogger('push_gazettes')

DATE_RE = re.compile(r'(\d{4})-(\d{2})-(\d{2})')

# How many relurls to ask about in one status call. The endpoint caps this at
# 2000.
STATUS_BATCH = 500

RETRY_STATUSES = {429, 500, 502, 503, 504}


def relurl_date(relurl):
    match = DATE_RE.search(relurl)
    if not match:
        return None
    try:
        return datetime.date(*(int(x) for x in match.groups()))
    except ValueError:
        return None


def in_daterange(relurl, fromdate, todate):
    if fromdate is None and todate is None:
        return True
    date = relurl_date(relurl)
    if date is None:
        return False
    if fromdate is not None and date < fromdate:
        return False
    if todate is not None and date > todate:
        return False
    return True


def iter_relurls(datadir, srcs, fromdate, todate):
    """Yield every relurl under datadir that has legallayout HTML.

    Enumeration walks ``html/`` because HTML is what the site requires, and
    because ``raw/`` holds two orders of magnitude more files.
    """
    htmldir = os.path.join(datadir, 'html')
    if not os.path.isdir(htmldir):
        logger.error('No html directory under %s', datadir)
        return

    for src in srcs or sorted(os.listdir(htmldir)):
        srcdir = os.path.join(htmldir, src)
        if not os.path.isdir(srcdir):
            if srcs:
                logger.warning('No html directory for src %s, skipping', src)
            continue

        for dirpath, _dirnames, filenames in os.walk(srcdir):
            for filename in sorted(filenames):
                if not filename.endswith('.html'):
                    continue
                path = os.path.join(dirpath, filename)
                relurl = os.path.relpath(path, htmldir)[: -len('.html')]
                if in_daterange(relurl, fromdate, todate):
                    yield relurl


def asset_path(datadir, kind, relurl, extension):
    return os.path.join(datadir, kind, relurl + extension)


def find_raw(datadir, relurl):
    """The raw file for a relurl, whatever extension it was saved with."""
    base = os.path.join(datadir, 'raw', relurl)
    for extension in ('.pdf', '.PDF', '.htm', '.html', '.txt', '.doc', '.docx'):
        candidate = base + extension
        if os.path.isfile(candidate):
            return candidate

    directory = os.path.dirname(base)
    prefix = os.path.basename(base) + '.'
    if os.path.isdir(directory):
        for name in sorted(os.listdir(directory)):
            if name.startswith(prefix):
                return os.path.join(directory, name)
    return None


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


class Pusher:
    def __init__(self, endpoint, token, datadir, with_pdf=False,
                 with_pymupdf=False, force=False, timeout=300, retries=3):
        self.base = endpoint.rstrip('/')
        self.datadir = datadir
        self.with_pdf = with_pdf
        self.with_pymupdf = with_pymupdf
        self.force = force
        self.timeout = timeout
        self.retries = retries

        self.session = requests.Session()
        self.session.headers['Authorization'] = 'Bearer %s' % token

    # -- http --------------------------------------------------------------

    def _request(self, method, path, **kwargs):
        """One request with retries on transport errors and 5xx."""
        url = self.base + path
        delay = 2

        for attempt in range(1, self.retries + 1):
            try:
                response = self.session.request(
                    method, url, timeout=self.timeout, **kwargs
                )
            except requests.RequestException as exc:
                if attempt == self.retries:
                    raise
                logger.warning('%s %s failed (%s), retrying in %ds',
                               method, path, exc, delay)
                time.sleep(delay)
                delay *= 2
                continue

            if response.status_code in RETRY_STATUSES and attempt < self.retries:
                logger.warning('%s %s returned %d, retrying in %ds',
                               method, path, response.status_code, delay)
                time.sleep(delay)
                delay *= 2
                continue

            return response

        raise RuntimeError('unreachable')

    def remote_status(self, relurls):
        """What the site already holds, keyed by relurl."""
        response = self._request(
            'POST', '/api/ingest/status/', json={'relurls': list(relurls)}
        )
        if response.status_code != 200:
            raise RuntimeError(
                'status call failed: %d %s'
                % (response.status_code, response.text[:300])
            )
        return response.json().get('gazettes', {})

    # -- per gazette -------------------------------------------------------

    def needs_push(self, relurl, remote, metatags_path, html_path):
        if self.force or relurl not in remote:
            return True

        known = remote[relurl]
        # Compare content hashes rather than mtimes: the scraper rewrites
        # files it re-downloads even when the bytes have not changed.
        if known.get('html_sha256') != sha256_file(html_path):
            return True
        if known.get('metadata_sha256') != sha256_file(metatags_path):
            return True

        # The site is up to date on content; only push again if we are now
        # sending an optional asset it does not have yet.
        if self.with_pdf and not known.get('has_pdf'):
            return bool(find_raw(self.datadir, relurl))
        if self.with_pymupdf and not known.get('has_pymupdf'):
            return os.path.isfile(
                asset_path(self.datadir, 'pymupdf', relurl, '.html')
            )
        return False

    def push(self, relurl, metatags_path, html_path):
        """Upload one gazette. Returns the site's result dict."""
        handles = []
        files = {}
        data = {'relurl': relurl}
        if self.force:
            data['force'] = '1'

        try:
            handles.append(open(metatags_path, 'rb'))
            files['metatags'] = (os.path.basename(metatags_path), handles[-1])

            handles.append(open(html_path, 'rb'))
            files['html'] = (os.path.basename(html_path), handles[-1])

            if self.with_pymupdf:
                path = asset_path(self.datadir, 'pymupdf', relurl, '.html')
                if os.path.isfile(path):
                    handles.append(open(path, 'rb'))
                    files['pymupdf'] = (os.path.basename(path), handles[-1])

            if self.with_pdf:
                path = find_raw(self.datadir, relurl)
                if path:
                    handles.append(open(path, 'rb'))
                    files['raw'] = (os.path.basename(path), handles[-1])
                    data['raw_extension'] = os.path.splitext(path)[1] or '.pdf'

            response = self._request('POST', '/api/ingest/', data=data,
                                     files=files)
        finally:
            for handle in handles:
                handle.close()

        if response.status_code == 401:
            raise SystemExit('Authentication failed: check --token')
        if response.status_code == 503:
            raise SystemExit(
                'The site has no ingest tokens configured '
                '(set EGAZETTE_INGEST_TOKENS there)'
            )

        try:
            return response.json()
        except ValueError:
            return {
                'relurl': relurl,
                'status': 'error',
                'reason': 'HTTP %d: %s' % (response.status_code,
                                           response.text[:200]),
            }

    # -- driver ------------------------------------------------------------

    def run(self, relurls, dry_run=False, limit=None):
        counts = {}
        processed = 0

        for batch in batched(relurls, STATUS_BATCH):
            if limit is not None and processed >= limit:
                break

            remote = {} if self.force else self.remote_status(batch)

            for relurl in batch:
                if limit is not None and processed >= limit:
                    break

                metatags_path = asset_path(self.datadir, 'metatags', relurl,
                                           '.xml')
                html_path = asset_path(self.datadir, 'html', relurl, '.html')

                if not os.path.isfile(metatags_path):
                    logger.warning('No metatags for %s, skipping', relurl)
                    counts['no-metadata'] = counts.get('no-metadata', 0) + 1
                    continue
                if not os.path.isfile(html_path):
                    counts['no-html'] = counts.get('no-html', 0) + 1
                    continue

                if not self.needs_push(relurl, remote, metatags_path,
                                       html_path):
                    counts['up-to-date'] = counts.get('up-to-date', 0) + 1
                    continue

                processed += 1

                if dry_run:
                    print(relurl)
                    counts['would-push'] = counts.get('would-push', 0) + 1
                    continue

                result = self.push(relurl, metatags_path, html_path)
                status = result.get('status', 'error')
                counts[status] = counts.get(status, 0) + 1

                if status == 'error':
                    logger.error('%s: %s', relurl,
                                 result.get('reason', 'unknown error'))
                else:
                    logger.info('%-9s %s', status,
                                result.get('identifier') or relurl)

        return counts


def batched(iterable, size):
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def to_date(datestr):
    nums = re.findall(r'\d+', datestr)
    if len(nums) != 3:
        raise argparse.ArgumentTypeError('%s not in DD-MM-YYYY format' % datestr)
    day, month, year = (int(x) for x in nums)
    return datetime.date(year, month, day)


def get_arg_parser():
    parser = argparse.ArgumentParser(
        description='Upload gazettes from a data directory to the website.',
    )
    parser.add_argument('-D', '--datadir', required=True,
                        help='gazette data directory (contains metatags/, '
                             'html/, raw/, pymupdf/)')
    parser.add_argument('--endpoint', required=True,
                        help='website base URL, e.g. https://gazettes.example.org')
    parser.add_argument('--token', default=os.environ.get('EGAZETTE_INGEST_TOKEN'),
                        help='ingest token (defaults to $EGAZETTE_INGEST_TOKEN)')
    parser.add_argument('-s', '--src', action='append', dest='srcs', default=[],
                        help='gazette src to push (repeatable); all if omitted')
    parser.add_argument('-t', '--fromdate', type=to_date, default=None,
                        help='from date (DD-MM-YYYY)')
    parser.add_argument('-T', '--todate', type=to_date, default=None,
                        help='to date (DD-MM-YYYY)')
    parser.add_argument('--with-pdf', action='store_true', default=False,
                        help='also upload the raw PDF (large; unnecessary when '
                             'the site can read the data directory itself)')
    parser.add_argument('--with-pymupdf', action='store_true', default=False,
                        help='also upload the pymupdf rendering')
    parser.add_argument('-r', '--force', action='store_true', default=False,
                        help='re-upload even when the site is up to date')
    parser.add_argument('--limit', type=int, default=None,
                        help='stop after this many uploads')
    parser.add_argument('--dry-run', action='store_true', default=False,
                        help='list what would be uploaded and exit')
    parser.add_argument('--timeout', type=int, default=300,
                        help='per-request timeout in seconds (default 300)')
    parser.add_argument('--retries', type=int, default=3,
                        help='attempts per request (default 3)')
    parser.add_argument('-l', '--loglevel', default='info',
                        help='critical|error|warning|info|debug')
    parser.add_argument('-f', '--logfile', default=None,
                        help='log file (defaults to stderr)')
    return parser


def main():
    args = get_arg_parser().parse_args()

    levels = {'critical': logging.CRITICAL, 'error': logging.ERROR,
              'warning': logging.WARNING, 'info': logging.INFO,
              'debug': logging.DEBUG}
    logging.basicConfig(
        level=levels.get(args.loglevel, logging.INFO),
        format='%(asctime)s: %(name)s: %(levelname)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        filename=args.logfile,
    )

    if not args.token and not args.dry_run:
        sys.exit('No ingest token: pass --token or set EGAZETTE_INGEST_TOKEN')

    if not os.path.isdir(args.datadir):
        sys.exit('No such data directory: %s' % args.datadir)

    pusher = Pusher(
        args.endpoint, args.token or '', args.datadir,
        with_pdf=args.with_pdf, with_pymupdf=args.with_pymupdf,
        force=args.force, timeout=args.timeout, retries=args.retries,
    )

    relurls = iter_relurls(args.datadir, args.srcs, args.fromdate, args.todate)
    counts = pusher.run(relurls, dry_run=args.dry_run, limit=args.limit)

    summary = ' '.join('%s=%d' % (k, counts[k]) for k in sorted(counts))
    logger.info('Done. %s', summary or 'nothing to do')

    if counts.get('error'):
        sys.exit(1)


if __name__ == '__main__':
    main()
