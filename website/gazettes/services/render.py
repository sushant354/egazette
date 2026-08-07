"""Turning gazette HTML into display markup and indexable plain text.

The legallayout converter emits a complete HTML document with its own
stylesheet and semantic classes (``.section``, ``.paragraph``,
``.header-text`` ...). The site inlines its body into the detail page rather
than framing it, so that the gazette text is part of the page for readers,
for print and for search engines. That means the markup has to be sanitised:
the document's own ``<style>`` would leak ``body`` rules into the site chrome,
and nothing from a converted third-party PDF should be able to run script.

Only a fixed set of tags and attributes survives. The legallayout ``class``
attribute is deliberately kept -- the site's own stylesheet restyles those
classes under ``.gazette-document``.

The pymupdf rendering is *not* run through here. It is a stack of
absolutely-positioned divs that only holds together as a standalone document,
so it is offered as an alternate view in a sandboxed frame and is never
indexed.
"""

import hashlib
import logging
import re

from bs4 import BeautifulSoup, Comment

logger = logging.getLogger(__name__)

# Tags kept in the rendered body. Everything else is unwrapped (children are
# kept, the tag itself is dropped) unless it is in DROP_TAGS.
ALLOWED_TAGS = {
    'p', 'div', 'span', 'br', 'hr',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'b', 'i', 'u', 's', 'em', 'strong', 'sub', 'sup', 'small',
    'ul', 'ol', 'li', 'dl', 'dt', 'dd',
    'table', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th', 'caption',
    'blockquote', 'pre', 'code', 'a',
    'section', 'article', 'figure', 'figcaption', 'center',
}

# Tags removed together with their contents.
DROP_TAGS = {
    'script', 'style', 'link', 'meta', 'title', 'head', 'noscript',
    'iframe', 'object', 'embed', 'applet', 'form', 'input', 'button',
    'select', 'textarea', 'svg', 'math', 'base', 'frame', 'frameset',
    # legallayout writes figures into a sibling images/ directory that the
    # ingest payload does not carry, so an <img> would always be broken.
    'img', 'picture', 'source', 'video', 'audio',
}

ALLOWED_ATTRS = {
    'a': {'href', 'title'},
    'td': {'colspan', 'rowspan'},
    'th': {'colspan', 'rowspan', 'scope'},
    # class carries legallayout's structural semantics, which the site's
    # stylesheet relies on.
    '*': {'class'},
}

SAFE_URL_RE = re.compile(r'^(https?://|mailto:|#|/)', re.IGNORECASE)

# Classes legallayout uses for page furniture. Kept in the text index (a page
# header often carries the gazette's registered number) but hidden on screen
# by the site stylesheet.
FURNITURE_CLASSES = {'header-text', 'footer-text', 'figure-text'}


def sha256(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def _decode(data):
    if isinstance(data, str):
        return data
    for encoding in ('utf-8', 'utf-16', 'latin-1'):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return data.decode('utf-8', errors='replace')


def _soup(data):
    return BeautifulSoup(_decode(data), 'html.parser')


def _clean_attrs(tag):
    allowed = ALLOWED_ATTRS.get(tag.name, set()) | ALLOWED_ATTRS['*']
    for name in list(tag.attrs):
        if name.lower() not in allowed:
            del tag.attrs[name]
            continue
        if name.lower() == 'href':
            href = (tag.attrs.get('href') or '').strip()
            if not SAFE_URL_RE.match(href):
                del tag.attrs['href']


def sanitize(data):
    """Return the document body as a safe HTML fragment string."""
    soup = _soup(data)

    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()

    for tag in soup.find_all(list(DROP_TAGS)):
        tag.decompose()

    body = soup.body or soup

    for tag in body.find_all(True):
        if tag.name in DROP_TAGS:
            tag.decompose()
        elif tag.name not in ALLOWED_TAGS:
            tag.unwrap()
        else:
            _clean_attrs(tag)

    # decode_contents() gives the body's inner HTML; when the source had no
    # <body> (a bare fragment) soup itself is the container and this is still
    # the right call.
    return body.decode_contents().strip()


def extract_text(data):
    """Plain text for indexing and snippets.

    Block-level tags become line breaks so that words either side of a
    paragraph boundary are not run together into a single false token.
    """
    soup = _soup(data)

    for tag in soup.find_all(['script', 'style', 'head', 'title']):
        tag.decompose()

    body = soup.body or soup
    text = body.get_text(separator='\n')

    # PDF conversion leaves a lot of ragged whitespace; collapse it so the
    # stored text stays small and snippets read cleanly.
    text = text.replace('\xa0', ' ')
    text = re.sub(r'[ \t\r\f\v]+', ' ', text)
    text = re.sub(r' *\n *', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def truncate_text(text, max_chars):
    """Cap the stored text, returning (text, was_truncated)."""
    if max_chars and len(text) > max_chars:
        return text[:max_chars], True
    return text, False


def index_text(text, max_bytes):
    """The slice of text fed to to_tsvector.

    A tsvector cannot exceed 1MB, and gazettes routinely run to hundreds of
    pages, so long documents are indexed by their opening section. Truncation
    is by *encoded* bytes because Devanagari and Bengali cost three bytes a
    character and a character-based limit would badly under-estimate the size.
    """
    encoded = text.encode('utf-8')
    if len(encoded) <= max_bytes:
        return text
    # Cut on a character boundary, then back off to the last whitespace so the
    # final token is not a fragment.
    clipped = encoded[:max_bytes].decode('utf-8', errors='ignore')
    space = clipped.rfind(' ')
    if space > max_bytes // 2:
        clipped = clipped[:space]
    return clipped


def summarize(text, length=320):
    """A short plain-text preview for listings without a search query."""
    snippet = ' '.join(text.split())
    if len(snippet) <= length:
        return snippet
    cut = snippet[:length].rsplit(' ', 1)[0]
    return cut + '…'
