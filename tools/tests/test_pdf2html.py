"""Diff-based (snapshot) tests for egazette.tools.pdf2html.

Each engine has its own expected file holding the concatenated HTML for a few
fixed relurls:

    tools/tests/expected/pymupdf.html
    tools/tests/expected/legallayout.html

The test regenerates the HTML for those relurls and asserts it matches the
expected file byte-for-byte (a unified diff is shown on mismatch). To refresh
the expected files after an intentional change, run with:

    UPDATE_EXPECTED=1 python -m unittest egazette.tools.tests.test_pdf2html

The raw PDFs are located through FileManager, exactly like pdf2html itself.
Point GZDL_DIR at the gazette data directory if it is not the default.
"""

import os
import sys
import difflib
import tempfile
import unittest

from egazette.utils.file_storage import FileManager
from egazette.tools import pdf2html

GZDL_DIR = os.environ.get('GZDL_DIR', '/home/sushant/gzdl')
LEGALLAYOUT_DIR = os.environ.get('LEGALLAYOUT_DIR',
                                 pdf2html.DEFAULT_LEGALLAYOUT_DIR)
UPDATE_EXPECTED = os.environ.get('UPDATE_EXPECTED') == '1'

EXPECTED_DIR = os.path.join(os.path.dirname(__file__), 'expected')

# A few small gazettes (1-2 pages each) used as fixtures.
RELURLS = [
    'central_extraordinary/2026-01-06/269218',
    'central_extraordinary/2026-01-08/269213',
    'central_extraordinary/2026-01-27/269607',
]

SEP = '\n<!-- ===== relurl: %s ===== -->\n'


def normalize(html, out_dir):
    """Strip run-specific bits so the snapshot is reproducible.

    legallayout writes figures under <out_dir>/images and embeds that absolute
    path in the HTML; replace the temp directory with a stable token.
    """
    return html.replace(out_dir, '<OUTDIR>')


def build_snapshot(engine):
    storage = FileManager(GZDL_DIR, False, False)
    chunks = []
    for relurl in RELURLS:
        pdf_path = storage.get_rawfile_path(relurl)
        if not pdf_path or not pdf_path.lower().endswith('.pdf'):
            raise unittest.SkipTest('raw PDF not found for %s' % relurl)

        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, os.path.basename(pdf_path)[:-4] + '.html')
            if engine == 'pymupdf':
                ok = pdf2html.convert_pymupdf(pdf_path, out_path)
            else:
                ok = pdf2html.convert_legallayout(pdf_path, out_path,
                                                  LEGALLAYOUT_DIR)
            assert ok, 'conversion failed for %s with %s' % (relurl, engine)
            with open(out_path, encoding='utf-8') as f:
                html = f.read()
            html = normalize(html, tmp)

        chunks.append(SEP % relurl)
        chunks.append(html)

    return ''.join(chunks)


def expected_path(engine):
    return os.path.join(EXPECTED_DIR, '%s.html' % engine)


def check_engine(testcase, engine):
    actual = build_snapshot(engine)
    path = expected_path(engine)

    if UPDATE_EXPECTED:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(actual)
        testcase.skipTest('updated expected file %s' % path)
        return

    testcase.assertTrue(
        os.path.exists(path),
        'missing expected file %s; run with UPDATE_EXPECTED=1 to create it'
        % path)

    with open(path, encoding='utf-8') as f:
        expected = f.read()

    if actual != expected:
        diff = '\n'.join(difflib.unified_diff(
            expected.splitlines(), actual.splitlines(),
            fromfile='expected/%s.html' % engine,
            tofile='actual', lineterm=''))
        testcase.fail('%s output differs from expected:\n%s' % (engine, diff))


class TestPyMuPDF(unittest.TestCase):
    def test_snapshot(self):
        check_engine(self, 'pymupdf')


class TestLegalLayout(unittest.TestCase):
    def test_snapshot(self):
        check_engine(self, 'legallayout')


if __name__ == '__main__':
    unittest.main()
