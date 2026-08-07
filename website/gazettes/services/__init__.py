"""Reusable services backing the gazette site.

The web views, the management commands and the HTTP ingest endpoint all go
through these modules rather than talking to models or the filesystem
directly, so that ingesting from a local gazette directory and ingesting from
an upload share one code path.

  sources   -- the srcinfos catalogue and Internet Archive identifiers
  storage   -- locating and writing raw/metatags/html/pymupdf assets
  metadata  -- parsing metatags XML into normalised model fields
  render    -- turning gazette HTML into safe display markup and plain text
  ingest    -- creating and updating Gazette rows plus their search vectors
  search    -- querying the archive
"""
