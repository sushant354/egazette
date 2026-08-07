# Deploying the Indian Gazettes website

nginx terminates TLS and serves static files; uwsgi runs Django behind a unix
socket; systemd supervises uwsgi and supplies the environment.

```
        nginx  ──unix socket──>  uwsgi (4 workers × 2 threads)  ──>  Postgres
          │                              │
     /static/                     gazette data roots
   (collectstatic)             (raw/ metatags/ html/ pymupdf/)
```

Files here:

| file | install as |
| --- | --- |
| `env.example` | `/etc/egazette-web.env` |
| `uwsgi.ini` | referenced in place by the unit |
| `egazette-web.service` | `/etc/systemd/system/egazette-web.service` |
| `nginx.conf` | `/etc/nginx/sites-available/egazette` |

## 1. System user and directories

```bash
sudo useradd --system --home /srv/egazette --shell /usr/sbin/nologin egazette
sudo mkdir -p /srv/egazette/{data,static}
sudo chown -R egazette:www-data /srv/egazette
sudo chmod 0750 /srv/egazette/data
```

`/srv/egazette/data` is the write root — where uploads land. It holds the same
`raw/ metatags/ html/ pymupdf/` layout as the scraper's directory.

## 2. Database

```bash
sudo -u postgres createuser --pwprompt egazette
sudo -u postgres createdb -O egazette egazette
```

## 3. Dependencies

The site shares the scraper's virtualenv so it can import `datasrcs_info`:

```bash
/home/sushant/.egazette312/bin/pip install -r /home/sushant/egazette/website/requirements.website.in
```

## 4. Environment

`settings.py` reads configuration from an env file. It looks at
`EGAZETTE_ENV_FILE` if that is set, otherwise `website/.env`; either way,
variables already exported in the process environment take precedence. In
production systemd supplies them through `EnvironmentFile=`, so the file lives
outside the checkout and no secret sits in a working copy:

```bash
sudo install -m 0640 -o root -g www-data \
     /home/sushant/egazette/website/deploy/env.example /etc/egazette-web.env
sudo -e /etc/egazette-web.env
```

At minimum set `EGAZETTE_SECRET_KEY`, `EGAZETTE_ALLOWED_HOSTS`,
`EGAZETTE_DB_PASSWORD` and `EGAZETTE_DATA_ROOTS`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"   # secret key
python -c "import secrets; print(secrets.token_urlsafe(48))"   # ingest token
```

If a development `.env` also exists in the checkout, note that the systemd
unit's `EnvironmentFile` wins for every key it sets — but keys it *omits* fall
through to `.env`. Keep the two in step, or delete `.env` on the production
host to remove the ambiguity.

`EGAZETTE_DATA_ROOTS` is a comma-separated list searched in order. If the web
host shares a filesystem with the scraper, list its data directory and the
PDFs and pymupdf renderings are served straight from there rather than being
copied. A small writable root can sit in front of a large read-only archive:

```
EGAZETTE_DATA_ROOTS=/srv/egazette/data,/mnt/gzdl
EGAZETTE_WRITE_ROOT=/srv/egazette/data
```

Leave `EGAZETTE_INGEST_TOKENS` empty unless the site is updated over HTTP; an
empty list closes the write endpoint completely.

## 5. Migrate and collect static

```bash
cd /home/sushant/egazette/website
export EGAZETTE_ENV_FILE=/etc/egazette-web.env
/home/sushant/.egazette312/bin/python manage.py migrate
/home/sushant/.egazette312/bin/python manage.py sync_sources
/home/sushant/.egazette312/bin/python manage.py collectstatic --noinput
```

`collectstatic` writes to `EGAZETTE_STATIC_ROOT` (set it to
`/srv/egazette/static` to match the nginx config).

## 6. uwsgi under systemd

```bash
sudo cp deploy/egazette-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now egazette-web
sudo systemctl status egazette-web
```

`ReadWritePaths` in the unit grants write access to the upload root only —
change it if `EGAZETTE_WRITE_ROOT` is elsewhere, or the service will start but
uploads will fail with permission errors.

## 7. nginx

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/egazette
sudo ln -s ../sites-available/egazette /etc/nginx/sites-enabled/egazette
sudo nginx -t && sudo systemctl reload nginx
```

Edit `server_name`, the certificate paths, and the `/static/` alias first.
`client_max_body_size` must be at least `EGAZETTE_MAX_UPLOAD_BYTES` or large
PDF uploads are rejected by nginx before Django ever sees them.

### Serving PDFs through nginx

Streaming a 200MB PDF out of Python ties up a worker for the whole download.
With `EGAZETTE_USE_X_ACCEL=true`, Django authorises the request and names the
file; nginx sends it.

Add one internal location per entry in `EGAZETTE_DATA_ROOTS`, numbered from
zero in the same order — the app builds `/protected/<index>/<path>` from
whichever root the file was found in:

```nginx
location /protected/0/ { internal; alias /srv/egazette/data/; }
location /protected/1/ { internal; alias /mnt/gzdl/; }
```

If the numbering and the root order disagree, PDFs 404.

## 8. Load the archive

```bash
sudo -u egazette EGAZETTE_ENV_FILE=/etc/egazette-web.env \
     /home/sushant/.egazette312/bin/python manage.py ingest_gazettes
```

or push from the scraper host — see the main [README](../README.md).

Ingestion is safe to run repeatedly; unchanged gazettes are skipped by content
hash. A nightly cron after the scraper's own run keeps the site current:

```cron
30 4 * * * cd /home/sushant/egazette/website && EGAZETTE_ENV_FILE=/etc/egazette-web.env /home/sushant/.egazette312/bin/python manage.py ingest_gazettes >> /var/log/egazette-ingest.log 2>&1
```

## Operating notes

**Caching.** Sanitised gazette bodies are cached, by default in per-process
memory — with four workers a popular gazette is sanitised up to four times.
Point `EGAZETTE_CACHE_BACKEND` at memcached or redis to share one copy.

**After changing the text search config.** `EGAZETTE_TS_CONFIG` is baked into
stored vectors; changing it requires `manage.py reindex_gazettes --all`, and
until that finishes results will be inconsistent.

**Counters.** The browse pages read denormalised per-source counts.
`ingest_gazettes` refreshes them at the end of a run; if they ever look stale,
`manage.py sync_sources --counts-only`.

**Postgres.** The full-text index is GIN over `search_vector`. For a large
archive, raise `maintenance_work_mem` before a bulk reindex and make sure
autovacuum is keeping up with the gazette table.
