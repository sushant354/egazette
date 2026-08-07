"""Helpers for building a gazette data directory in tests."""

import os

# A metatags file shaped like the central gazette's: dated, with a ministry,
# department, office and subject.
CENTRAL_XML = """<?xml version="1.0" encoding="utf-8"?>
<document>
<date>
<day>18</day>
<month>4</month>
<year>2024</year>
</date>
<department>Construction Department</department>
<gazetteid>CG-BR-E-18042024-253767</gazetteid>
<ministry>Ministry of Railways</ministry>
<office>East Central Railway</office>
<subject>Acquisition of land under the Railways Amendment Act 2008</subject>
<url>https://egazette.gov.in/WriteReadData/2024/253767.pdf</url>
</document>
"""

# The West Bengal Secretariat Library shape: a year but no date, and a bookid
# that its identifier function depends on.
WBSL_XML = """<?xml version="1.0" encoding="utf-8"?>
<document>
<bookid>WB00123</bookid>
<creator>Bengal Secretariat Press</creator>
<language>eng</language>
<subject>Calcutta Gazette</subject>
<title>The Calcutta Gazette, 1885</title>
<year>1885</year>
</document>
"""

# legallayout output: a full document with its own stylesheet and semantic
# classes, which is what the site sanitises and indexes.
LEGALLAYOUT_HTML = """<!DOCTYPE HTML>
<html>
<head>
<meta charset="UTF-8" />
<style>
  body { line-height: 1.6; }
  span.header-text { display: None; }
</style>
</head>
<body>
<span class="header-text">Registered No. HSE-49/2016</span>
<h4>NOTIFICATIONS BY GOVERNMENT</h4>
<p>In exercise of the powers conferred by Sub-rule (2) of Rule 5 of the
Indian Administrative Service (Cadre) Rules, 1954, the Central Government
hereby notifies the inter cadre transfer of the officer named below.</p>
<div class="section"><p>Land acquisition proceedings shall continue.</p></div>
<table><tbody><tr><td>Serial</td><td>Description</td></tr></tbody></table>
</body>
</html>
"""

PYMUPDF_HTML = """<!DOCTYPE html>
<html><head><meta name="generator" content="pymupdf"/></head>
<body><div style="position:absolute;top:10px">Page one text</div></body></html>
"""


def write_gazette(datadir, relurl, metatags=CENTRAL_XML,
                  html=LEGALLAYOUT_HTML, pymupdf=None, raw=None):
    """Lay a gazette out on disk the way the scraper does.

    Returns the paths written, keyed by asset kind.
    """
    written = {}

    def put(kind, extension, content):
        path = os.path.join(datadir, kind, relurl + extension)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        mode = 'wb' if isinstance(content, bytes) else 'w'
        with open(path, mode) as handle:
            handle.write(content)
        written[kind] = path

    if metatags is not None:
        put('metatags', '.xml', metatags)
    if html is not None:
        put('html', '.html', html)
    if pymupdf is not None:
        put('pymupdf', '.html', pymupdf)
    if raw is not None:
        put('raw', '.pdf', raw)

    return written
