"""Convert downloaded PDF gazettes into HTML.

Raw PDFs are located through egazette's FileManager (file_storage.py), so a
gazette with relurl ``central_extraordinary/2026-01-01/269031`` is read from
``<datadir>/raw/central_extraordinary/2026-01-01/269031.pdf``. The HTML is
written under an engine-specific subdirectory of datadir (see OUTPUT_SUBDIR):
  * pymupdf     -> ``<datadir>/pymupdf/<relurl>.html``
  * legallayout -> ``<datadir>/html/<relurl>.html``

Two conversion engines are supported:
  * ``pymupdf``      - fast, layout-preserving HTML straight from PyMuPDF.
  * ``legallayout``  - richer structured HTML produced by the legallayout tool
                       (/home/sushant/legallayout/source/Main.py).

Run from the directory that contains the ``egazette`` package, e.g.:

    python -m egazette.tools.pdf2html -D /home/sushant/gzdl -e pymupdf \
            -s central_extraordinary -t 01-01-2026 -T 31-01-2026 -w 8

    python -m egazette.tools.pdf2html -D /home/sushant/gzdl -e legallayout \
            --relurl central_extraordinary/2026-01-01/269031

Pass ``-w N`` to convert with N worker processes in parallel (default 1).
"""

import os
import sys
import re
import argparse
import logging
import datetime
import multiprocessing
from concurrent.futures import ProcessPoolExecutor

from egazette.utils.file_storage import FileManager

logger = logging.getLogger('pdf2html')

# Match egazette's download.py: pickle-free worker startup via fork where
# available, falling back to the platform default otherwise.
try:
    mpctx = multiprocessing.get_context('fork')
except ValueError:
    mpctx = multiprocessing.get_context()

DEFAULT_LEGALLAYOUT_DIR = '/home/sushant/legallayout'

# legallayout Main() behavioural defaults for generic gazette conversion:
# no footnote continuation across pages, and no minimum image-size filtering.
LEGALLAYOUT_IS_FOOTNOTE_CONTINUATION = False
LEGALLAYOUT_MIN_IMG_SIZE = 50

# output subdirectory (under datadir) for each engine's HTML
OUTPUT_SUBDIR = {
    'pymupdf': 'pymupdf',
    'legallayout': 'html',
}

# date directory in a relurl, e.g. central_extraordinary/2026-01-01/269031
DATE_RE = re.compile(r'(\d{4})-(\d{2})-(\d{2})')


def relurl_date(relurl):
    """Return the datetime.date embedded in a relurl, or None."""
    match = DATE_RE.search(relurl)
    if not match:
        return None
    year, month, day = (int(x) for x in match.groups())
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def in_daterange(relurl, fromdate, todate):
    if fromdate is None and todate is None:
        return True

    date = relurl_date(relurl)
    if date is None:
        # no date to compare against; keep it only when no range was asked for
        return False

    if fromdate is not None and date < fromdate:
        return False
    if todate is not None and date > todate:
        return False
    return True


def iter_pdf_relurls(storage, srcs, fromdate, todate):
    """Yield (relurl, pdf_path) for every raw PDF matching srcs and the dates.

    PDFs are located using FileManager so the on-disk layout stays the single
    source of truth.
    """
    if not srcs:
        srcs = sorted(os.listdir(storage.rawdir))

    for src in srcs:
        srcdir = os.path.join(storage.rawdir, src)
        if not os.path.isdir(srcdir):
            logger.warning('No raw directory for src %s, skipping', src)
            continue

        for relurl in storage.recursive_relurls(storage.rawdir, src):
            if not in_daterange(relurl, fromdate, todate):
                continue

            pdf_path = storage.get_rawfile_path(relurl)
            if not pdf_path or not pdf_path.lower().endswith('.pdf'):
                continue

            yield relurl, pdf_path


def convert_pymupdf(pdf_path, out_path):
    """Convert a PDF to a single self-contained HTML file using PyMuPDF."""
    import fitz

    doc = fitz.open(pdf_path)
    try:
        parts = [
            '<!DOCTYPE html>',
            '<html>',
            '<head>',
            '<meta charset="utf-8"/>',
            '<meta name="generator" content="pymupdf"/>',
            '</head>',
            '<body>',
        ]
        for page in doc:
            parts.append(page.get_text('html'))
        parts.append('</body>')
        parts.append('</html>')
    finally:
        doc.close()

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(parts))
    return True


def convert_legallayout(pdf_path, out_path, legallayout_dir):
    """Convert a PDF to HTML using the legallayout Main pipeline.

    legallayout writes ``<pdf_basename>.html`` into the output directory (and an
    ``images/`` subdir for figures). Since the raw file is stored as
    ``<relurl>.pdf`` the produced filename already matches ``<relurl>.html``; we
    point the output directory at the target's parent and rename defensively.
    """
    if legallayout_dir not in sys.path:
        sys.path.insert(0, legallayout_dir)

    from source.Main import Main

    out_dir = os.path.dirname(out_path)

    # pdf_type=None -> generic gazette HTMLBuilder; no amendments / sidenotes.
    main = Main(pdf_path, False, out_dir, None, False, False,
                LEGALLAYOUT_IS_FOOTNOTE_CONTINUATION, LEGALLAYOUT_MIN_IMG_SIZE)
    ok = main.parsePDF(None, None, None, None, None, None)
    if ok:
        main.buildHTML(None, None)
    main.clear_cache_pdf()
    main.clear_cache()

    if not ok:
        return False

    produced = os.path.join(
        out_dir,
        os.path.splitext(os.path.basename(pdf_path))[0] + '.html',
    )
    if produced != out_path and os.path.exists(produced):
        os.replace(produced, out_path)

    return os.path.exists(out_path)


def convert_one(storage, htmldir, engine, legallayout_dir, relurl, pdf_path,
                overwrite):
    """Convert a single PDF. Returns 'converted', 'skipped' or 'failed'."""
    out_path = os.path.join(htmldir, '%s.html' % relurl)

    if os.path.exists(out_path) and not overwrite:
        logger.info('Skipping %s, html already exists', relurl)
        return 'skipped'

    # create <htmldir>/<src>/<date>/ for the output file
    storage.create_dirs(htmldir, relurl)

    logger.info('Converting %s -> %s', pdf_path, out_path)
    try:
        if engine == 'pymupdf':
            ok = convert_pymupdf(pdf_path, out_path)
        else:
            ok = convert_legallayout(pdf_path, out_path, legallayout_dir)
    except Exception:
        logger.exception('Failed to convert %s', relurl)
        ok = False

    return 'converted' if ok else 'failed'


def resolve_pdf(storage, relurl, pdf_path):
    """Return the raw PDF path for a relurl, or None if there isn't one."""
    if pdf_path is None:
        pdf_path = storage.get_rawfile_path(relurl)
    if not pdf_path or not pdf_path.lower().endswith('.pdf'):
        return None
    return pdf_path


# Per-worker state, populated once by the pool initializer so that the
# FileManager and config are not re-pickled for every task.
_worker = {}


def _worker_init(datadir, htmldir, engine, legallayout_dir, overwrite):
    _worker['storage'] = FileManager(datadir, False, False)
    _worker['htmldir'] = htmldir
    _worker['engine'] = engine
    _worker['legallayout_dir'] = legallayout_dir
    _worker['overwrite'] = overwrite


def _worker_task(relurl_pdf):
    relurl, pdf_path = relurl_pdf
    storage = _worker['storage']

    pdf_path = resolve_pdf(storage, relurl, pdf_path)
    if pdf_path is None:
        logger.error('No raw PDF found for relurl %s', relurl)
        return 'failed'

    return convert_one(storage, _worker['htmldir'], _worker['engine'],
                       _worker['legallayout_dir'], relurl, pdf_path,
                       _worker['overwrite'])


def convert(storage, datadir, htmldir, engine, legallayout_dir, relurl_pdfs,
            overwrite, workers=1):
    counts = {'converted': 0, 'failed': 0, 'skipped': 0}

    if workers and workers > 1:
        # relurl_pdfs is an iterable of (relurl, pdf_path) tuples; both entries
        # are plain strings/None so they pickle cleanly across workers.
        with ProcessPoolExecutor(
                max_workers=workers, mp_context=mpctx,
                initializer=_worker_init,
                initargs=(datadir, htmldir, engine, legallayout_dir,
                          overwrite)) as executor:
            for result in executor.map(_worker_task, relurl_pdfs):
                counts[result] += 1
    else:
        for relurl, pdf_path in relurl_pdfs:
            pdf_path = resolve_pdf(storage, relurl, pdf_path)
            if pdf_path is None:
                logger.error('No raw PDF found for relurl %s', relurl)
                counts['failed'] += 1
                continue

            result = convert_one(storage, htmldir, engine, legallayout_dir,
                                 relurl, pdf_path, overwrite)
            counts[result] += 1

    logger.info('Done. converted=%d failed=%d skipped=%d',
                counts['converted'], counts['failed'], counts['skipped'])
    return counts


def to_date(datestr):
    nums = re.findall(r'\d+', datestr)
    if len(nums) != 3:
        raise argparse.ArgumentTypeError(
            '%s not in DD-MM-YYYY format' % datestr)
    day, month, year = (int(x) for x in nums)
    return datetime.date(year, month, day)


def get_arg_parser():
    parser = argparse.ArgumentParser(
        description='Convert downloaded PDF gazettes into HTML.')
    parser.add_argument('-D', '--datadir', dest='datadir', required=True,
                        help='gazette data directory (contains raw/ and html/)')
    parser.add_argument('-e', '--engine', dest='engine', default='pymupdf',
                        choices=['pymupdf', 'legallayout'],
                        help='conversion engine (default: pymupdf)')
    parser.add_argument('-s', '--src', dest='srcs', action='append',
                        default=[],
                        help='gazette src to convert (repeatable); all if omitted')
    parser.add_argument('--relurl', dest='relurls', action='append',
                        default=[],
                        help='convert a single relurl (repeatable)')
    parser.add_argument('-t', '--fromdate', dest='fromdate', type=to_date,
                        default=None, help='from date (DD-MM-YYYY)')
    parser.add_argument('-T', '--todate', dest='todate', type=to_date,
                        default=None, help='to date (DD-MM-YYYY)')
    parser.add_argument('-r', '--overwrite', dest='overwrite',
                        action='store_true', default=False,
                        help='overwrite existing html files')
    parser.add_argument('-w', '--workers', dest='workers', type=int,
                        default=1,
                        help='number of worker processes (default: 1)')
    parser.add_argument('--legallayout-dir', dest='legallayout_dir',
                        default=DEFAULT_LEGALLAYOUT_DIR,
                        help='path to the legallayout checkout (parent of '
                             'the source/ package)')
    parser.add_argument('-l', '--loglevel', dest='loglevel', default='info',
                        help='log level (critical|error|warning|info|debug)')
    parser.add_argument('-f', '--logfile', dest='logfile', default=None,
                        help='log file (defaults to stderr)')
    return parser


def main():
    args = get_arg_parser().parse_args()

    leveldict = {'critical': logging.CRITICAL, 'error': logging.ERROR,
                 'warning': logging.WARNING, 'info': logging.INFO,
                 'debug': logging.DEBUG}
    logging.basicConfig(
        level=leveldict.get(args.loglevel, logging.INFO),
        format='%(asctime)s: %(name)s: %(levelname)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        filename=args.logfile,
    )

    storage = FileManager(args.datadir, False, False)
    htmldir = os.path.join(args.datadir, OUTPUT_SUBDIR[args.engine])
    if not os.path.exists(htmldir):
        os.makedirs(htmldir)

    if args.relurls:
        # explicit relurls bypass src/date enumeration; pdf located on demand
        relurl_pdfs = ((relurl, None) for relurl in args.relurls)
    else:
        relurl_pdfs = iter_pdf_relurls(storage, args.srcs,
                                       args.fromdate, args.todate)

    convert(storage, args.datadir, htmldir, args.engine, args.legallayout_dir,
            relurl_pdfs, args.overwrite, args.workers)


if __name__ == '__main__':
    main()
