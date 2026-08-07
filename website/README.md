# Indian Gazettes — website

A Django site that publishes the gazettes collected by the scraper in this
repository: full-text search over the gazette text, browse by publishing
series, and a permanent page per issue at `/details/<identifier>/`.

The site imports `egazette.srcs.datasrcs_info` and `egazette.utils` directly,
so the scraper stays the single source of truth for what a gazette series is
and how its Internet Archive identifier is built. There is no second copy of
that knowledge to keep in sync.

## How it fits together

```
egazette/
  srcs/datasrcs_info.py     srcinfos + get_identifier()   <- imported, not copied
  utils/xml_ops.py          metatags XML reader           <- imported, not copied
  tools/
    pdf2html.py             PDF -> html/ and pymupdf/
    push_gazettes.py        data directory -> website     <- the upload tool
  website/
    egazette_site/          settings, urls, wsgi
    gazettes/
      models.py             Source, Gazette
      services/             the reusable layer (see below)
      views.py  api.py      reader pages, ingest endpoint
      management/commands/  ingest_gazettes, sync_sources, reindex_gazettes
    templates/  static/
    deploy/                 uwsgi, nginx, systemd, env
```

Everything that touches gazette data goes through `gazettes/services/`, so the
local ingest command and the HTTP upload endpoint share one implementation:

| module | responsibility |
| --- | --- |
| `sources.py` | the srcinfos catalogue and Internet Archive identifiers |
| `storage.py` | locating and writing `raw/`, `metatags/`, `html/`, `pymupdf/` assets |
| `metadata.py` | metatags XML → normalised model fields |
| `render.py` | gazette HTML → safe display markup and indexable text |
| `ingest.py` | creating/updating gazettes and their search vectors |
| `search.py` | queries, highlighting, facets |

## Data model

`Source` mirrors one `srcinfos` entry (a publishing series such as the
Extraordinary Gazette of India) and is rebuilt by `manage.py sync_sources`.

`Gazette` is one issue. The tags worth querying — date, gazette number, part,
type, ministry, department, office — are promoted to columns; everything else
the scraper recorded is kept verbatim in a `metadata` JSONB column, because the
tag set differs sharply between sources (West Bengal archive scans carry a
`bookid` and no date at all).

**The legallayout HTML is required.** A gazette with no `html/<relurl>.html`
is skipped rather than half-recorded, and picked up on a later run once
`pdf2html -e legallayout` has converted it. The raw PDF and the pymupdf
rendering are optional.

Full text is indexed into a weighted `tsvector`:

| weight | field |
| --- | --- |
| A | title |
| B | subject |
| C | department, ministry, office, type |
| D | gazette body text |

A `tsvector` cannot exceed 1MB, so long issues are indexed by their opening
section (`EGAZETTE_MAX_INDEX_BYTES`, truncated by *encoded bytes* since Indic
scripts cost three bytes a character). Affected gazettes say so on their page.

## Renderings

The **legallayout** HTML is canonical: it is what gets indexed, and the detail
page inlines its body after sanitising it — the document's own `<style>` would
otherwise leak `body` rules into the site chrome, and nothing from an automated
conversion of a third-party PDF should be able to run script.

The **pymupdf** rendering is a stack of absolutely positioned divs that only
holds together as a standalone document. It is offered as a non-default
alternate view in a sandboxed frame with a restrictive CSP, is marked
`noindex`, and is never part of the search index.

## Configuration

Settings come from a `.env` file beside `manage.py`, read automatically by
`egazette_site/settings.py`. It is gitignored — it holds the secret key, the
database password and the ingest token. `deploy/env.example` is the committed
template:

```bash
cp deploy/env.example .env
chmod 600 .env
python -c "import secrets; print(secrets.token_urlsafe(64))"   # EGAZETTE_SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(48))"   # EGAZETTE_INGEST_TOKENS
$EDITOR .env
```

Anything already exported in the environment beats the file, so a one-off
override needs no edit:

```bash
EGAZETTE_DEBUG=true python manage.py runserver
```

Set `EGAZETTE_ENV_FILE` to read a file from elsewhere — that path must exist,
or startup fails rather than quietly falling back to defaults. In production
systemd supplies the same keys through `EnvironmentFile=`.

The settings worth knowing about:

| variable | meaning |
| --- | --- |
| `EGAZETTE_DATA_ROOTS` | comma-separated gazette directories, searched in order |
| `EGAZETTE_WRITE_ROOT` | where `/api/ingest/` uploads land |
| `EGAZETTE_INGEST_TOKENS` | comma-separated ingest secrets; empty closes the API |
| `EGAZETTE_TS_CONFIG` | Postgres text search config (reindex after changing) |
| `EGAZETTE_MAX_INDEX_BYTES` | how much of a long gazette reaches the tsvector |

## Setup

```bash
# Postgres
createdb -O egazette egazette

# dependencies (shares the scraper's virtualenv)
/home/sushant/.egazette312/bin/pip install -r requirements.website.in

cp deploy/env.example .env && chmod 600 .env && $EDITOR .env

python manage.py migrate
python manage.py sync_sources
python manage.py ingest_gazettes
python manage.py runserver
```

## Updating the archive

Two routes, both landing in the same `IngestService`.

**Same host as the data** — read it in place:

```bash
python manage.py ingest_gazettes                    # everything available
python manage.py ingest_gazettes -s andhra          # one series
python manage.py ingest_gazettes -t 01-01-2024 -T 31-01-2024
python manage.py ingest_gazettes --relurl andhra/2018-05-04/2758
python manage.py ingest_gazettes --dry-run
```

Re-running is cheap: a gazette whose HTML and metadata hashes are unchanged is
left alone, though its PDF/pymupdf flags are refreshed in case those appeared
since. Use `--force` to reindex regardless.

**Separate web host** — push from the machine holding the data:

```bash
python -m egazette.tools.push_gazettes \
    -D /home/sushant/public/gzdl \
    --endpoint https://gazettes.example.org \
    --token "$EGAZETTE_INGEST_TOKEN" \
    -s andhra -t 01-01-2018 -T 31-12-2018
```

The tool asks the site which gazettes it already holds and at what content
hash before uploading anything, so an unchanged gazette is never re-sent.
Metadata and HTML always go; add `--with-pdf` / `--with-pymupdf` to upload
those too. **When the site can already read the gazette directory, leave them
off** — 658GB of PDFs and 886GB of pymupdf renderings do not need to move.

### Ingest API

```
POST /api/ingest/status/    {"relurls": [...]}  -> what the site holds
POST /api/ingest/           multipart: relurl, metatags, html [, pymupdf, raw]
```

Authenticate with `Authorization: Bearer <token>` against
`EGAZETTE_INGEST_TOKENS`. With no tokens set the endpoint is closed, so a site
updated only by `ingest_gazettes` exposes no write path at all.

Responses: `200` with a status of `created` / `updated` / `unchanged` /
`skipped`; `422` when the gazette itself is at fault (unparseable XML, a
colliding identifier) so the pusher does not retry it; `500` only for genuine
server faults.

## Other commands

```bash
python manage.py sync_sources                 # after editing datasrcs_info.py
python manage.py sync_sources --counts-only   # refresh browse-page counters
python manage.py reindex_gazettes             # fill in missing search vectors
python manage.py reindex_gazettes --all       # after changing EGAZETTE_TS_CONFIG
```

## Tests

```bash
python manage.py test gazettes
```

122 tests covering path-traversal defences on the upload endpoint, HTML
sanitisation, byte-accurate index truncation for Indic scripts, identifier
agreement with the scraper, undated sources, and the escaping that keeps
`ts_headline` output safe.

## Deployment

See [`deploy/README.md`](deploy/README.md) for the uwsgi/nginx/systemd setup.
