"""Django settings for the Indian Gazettes website.

Everything that differs between a laptop and the production host is read from
the environment, so the same checkout runs in both places. Configuration comes
from a ``.env`` file next to ``manage.py`` (see ``deploy/env.example`` for the
full list of keys), and anything already exported into the real environment
wins over it -- which is what lets systemd's ``EnvironmentFile`` and one-off
shell overrides take precedence in production.

Point ``EGAZETTE_ENV_FILE`` at another path to load that instead.

The site sits inside the egazette checkout (``<egazette>/website``) and imports
``egazette.srcs.datasrcs_info`` for source metadata and Internet Archive
identifiers, so the scraper stays the single source of truth for both. That
import needs the *parent* of the egazette package on sys.path, which is wired
up below.
"""

import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

# <egazette>/website -> <egazette> -> the directory holding the egazette
# package. Putting the latter on sys.path is what makes `import egazette` work
# without installing the scraper as a distribution.
EGAZETTE_DIR = BASE_DIR.parent
EGAZETTE_PARENT = EGAZETTE_DIR.parent
if str(EGAZETTE_PARENT) not in sys.path:
    sys.path.insert(0, str(EGAZETTE_PARENT))


def load_env_file(path, override=False):
    """Read KEY=value lines from an env file into os.environ.

    Deliberately small: no interpolation, no multi-line values, no shell. The
    same file is read by Django here and by systemd's ``EnvironmentFile=`` in
    production, so it has to stay within what both understand.

    Existing environment variables are left alone unless ``override`` is set,
    so an exported value always beats the file.

    Returns True if the file was read, False if it does not exist.
    """
    path = Path(path)
    if not path.is_file():
        return False

    with path.open(encoding='utf-8') as handle:
        for lineno, raw in enumerate(handle, 1):
            line = raw.strip()
            if not line or line.startswith('#'):
                continue

            # `export FOO=bar` so the same file can also be sourced by a shell.
            if line.startswith('export '):
                line = line[len('export '):].lstrip()

            key, sep, value = line.partition('=')
            if not sep:
                raise ImproperlyConfigured(
                    '%s:%d: expected KEY=value, got %r' % (path, lineno, line)
                )

            key = key.strip()
            if not key.isidentifier():
                raise ImproperlyConfigured(
                    '%s:%d: %r is not a valid variable name'
                    % (path, lineno, key)
                )

            value = value.strip()
            # Quotes let a value keep leading/trailing spaces or a '#'.
            if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
                value = value[1:-1]

            if override or key not in os.environ:
                os.environ[key] = value

    return True


# An explicitly named file must exist -- silently ignoring a typo'd path would
# start the site on defaults and look like a configuration bug much later.
_env_file = os.environ.get('EGAZETTE_ENV_FILE')
if _env_file:
    if not load_env_file(_env_file):
        raise ImproperlyConfigured(
            'EGAZETTE_ENV_FILE points at %s, which does not exist' % _env_file
        )
else:
    load_env_file(BASE_DIR / '.env')


def env(name, default=None):
    value = os.environ.get(name)
    return default if value is None or value == '' else value


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None or value == '':
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def env_list(name, default=()):
    value = os.environ.get(name)
    if value is None or value.strip() == '':
        return list(default)
    return [item.strip() for item in value.split(',') if item.strip()]


def env_int(name, default):
    value = os.environ.get(name)
    if value is None or value.strip() == '':
        return default
    return int(value)


# --- core -----------------------------------------------------------------

# A generated secret is fine for runserver, but the deployed site must set
# EGAZETTE_SECRET_KEY or sessions and CSRF tokens reset on every restart.
SECRET_KEY = env('EGAZETTE_SECRET_KEY', 'dev-only-insecure-key-change-me')
DEBUG = env_bool('EGAZETTE_DEBUG', False)
ALLOWED_HOSTS = env_list('EGAZETTE_ALLOWED_HOSTS', ['localhost', '127.0.0.1'])
CSRF_TRUSTED_ORIGINS = env_list('EGAZETTE_CSRF_TRUSTED_ORIGINS', [])

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.postgres',
    'gazettes',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'egazette_site.urls'
WSGI_APPLICATION = 'egazette_site.wsgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'gazettes.context_processors.site',
                'gazettes.context_processors.account',
            ],
        },
    },
]

# --- database -------------------------------------------------------------

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('EGAZETTE_DB_NAME', 'egazette'),
        'USER': env('EGAZETTE_DB_USER', 'egazette'),
        'PASSWORD': env('EGAZETTE_DB_PASSWORD', 'egazette'),
        'HOST': env('EGAZETTE_DB_HOST', '127.0.0.1'),
        'PORT': env('EGAZETTE_DB_PORT', '5432'),
        'CONN_MAX_AGE': env_int('EGAZETTE_DB_CONN_MAX_AGE', 60),
    }
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- accounts -------------------------------------------------------------

# An account exists only so a reader can keep bookmarks; nothing else on the
# site is gated. @login_required therefore sends people to the site's own
# sign-in page rather than the admin's.
LOGIN_URL = 'gazettes:login'
LOGIN_REDIRECT_URL = 'gazettes:home'
LOGOUT_REDIRECT_URL = 'gazettes:home'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.'
             'UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.'
             'CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.'
             'NumericPasswordValidator'},
]

# Readers stay signed in across browser restarts; a session that ended with
# the window would make bookmarks pointless on a shared reading machine.
SESSION_COOKIE_AGE = env_int('EGAZETTE_SESSION_COOKIE_AGE', 60 * 60 * 24 * 30)
SESSION_SAVE_EVERY_REQUEST = True

# --- i18n / tz ------------------------------------------------------------

LANGUAGE_CODE = 'en-in'
TIME_ZONE = env('EGAZETTE_TIME_ZONE', 'Asia/Kolkata')
USE_I18N = True
USE_TZ = True

# --- static ---------------------------------------------------------------

STATIC_URL = '/static/'
STATIC_ROOT = Path(env('EGAZETTE_STATIC_ROOT', BASE_DIR / 'staticfiles'))
STATICFILES_DIRS = [BASE_DIR / 'static']

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'
        if not DEBUG
        else 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}

# --- gazette data ---------------------------------------------------------

# Directories laid out like the scraper's data dir (raw/, metatags/, html/,
# pymupdf/). They are searched in order when locating an asset, which is what
# lets the site read an existing gazette tree in place instead of copying
# hundreds of gigabytes: point EGAZETTE_DATA_ROOTS at /path/to/gzdl and the
# optional PDF and pymupdf renderings are served straight from there.
GAZETTE_DATA_ROOTS = [
    Path(p) for p in env_list('EGAZETTE_DATA_ROOTS', [str(BASE_DIR / 'data')])
]

# Where uploaded assets are written. Defaults to the first read root.
GAZETTE_WRITE_ROOT = Path(
    env('EGAZETTE_WRITE_ROOT', str(GAZETTE_DATA_ROOTS[0]))
)

# Postgres text search configuration used to build and query tsvectors.
# 'english' stems English but leaves Devanagari/Bengali/Tamil tokens intact, so
# it is a safe default for a bilingual corpus. Changing it requires a reindex
# (manage.py reindex_gazettes --all).
GAZETTE_TS_CONFIG = env('EGAZETTE_TS_CONFIG', 'english')

# A tsvector cannot exceed 1MB. Gazette HTML routinely runs to hundreds of
# pages, so only the first slice of extracted text is fed to to_tsvector. The
# full text is still stored for display and snippets.
GAZETTE_MAX_INDEX_BYTES = env_int('EGAZETTE_MAX_INDEX_BYTES', 700_000)

# Upper bound on the plain text kept in the database per gazette.
GAZETTE_MAX_TEXT_CHARS = env_int('EGAZETTE_MAX_TEXT_CHARS', 4_000_000)

# Largest upload the ingest endpoint will accept per asset, in bytes.
GAZETTE_MAX_UPLOAD_BYTES = env_int('EGAZETTE_MAX_UPLOAD_BYTES', 256 * 1024 * 1024)

# Shared secrets accepted by /api/ingest/. Empty means the API is disabled.
GAZETTE_INGEST_TOKENS = env_list('EGAZETTE_INGEST_TOKENS', [])

# Base URL for the Internet Archive item that shares the gazette's identifier.
GAZETTE_IA_DETAILS_URL = env(
    'EGAZETTE_IA_DETAILS_URL', 'https://archive.org/details/'
)

# When true, nginx serves the PDF via X-Accel-Redirect instead of Django
# streaming it. Requires the internal location block from deploy/nginx.conf.
GAZETTE_USE_X_ACCEL = env_bool('EGAZETTE_USE_X_ACCEL', False)
GAZETTE_X_ACCEL_PREFIX = env('EGAZETTE_X_ACCEL_PREFIX', '/protected/')

SITE_NAME = env('EGAZETTE_SITE_NAME', 'Indian Gazettes')
SITE_TAGLINE = env(
    'EGAZETTE_SITE_TAGLINE',
    'A searchable archive of gazettes published by the Union and State Governments of India',
)

RESULTS_PER_PAGE = env_int('EGAZETTE_RESULTS_PER_PAGE', 20)

# Uploaded gazette assets are large; keep them on disk rather than in memory.
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 4 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 200

# --- caching --------------------------------------------------------------

# Rendered gazette bodies are expensive to sanitise, so they are cached. The
# locmem default is per-process; production should point at memcached/redis.
CACHES = {
    'default': {
        'BACKEND': env(
            'EGAZETTE_CACHE_BACKEND',
            'django.core.cache.backends.locmem.LocMemCache',
        ),
        'LOCATION': env('EGAZETTE_CACHE_LOCATION', 'egazette-default'),
        'TIMEOUT': env_int('EGAZETTE_CACHE_TIMEOUT', 3600),
    }
}

# --- security -------------------------------------------------------------

# SAMEORIGIN rather than DENY: the alternate pymupdf rendering of a gazette is
# shown in a same-origin <iframe> (sandboxed, and served under a restrictive
# CSP -- see gazettes.views.pymupdf_frame). DENY would break that view.
X_FRAME_OPTIONS = 'SAMEORIGIN'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'

if not DEBUG:
    SESSION_COOKIE_SECURE = env_bool('EGAZETTE_SECURE_COOKIES', True)
    CSRF_COOKIE_SECURE = env_bool('EGAZETTE_SECURE_COOKIES', True)
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

    # deploy/nginx.conf already redirects to HTTPS and sends HSTS. These are
    # here so a deployment behind a different proxy -- or none -- can turn
    # them on without patching the code. Enable HSTS only once every hostname
    # the site answers on is serving HTTPS; it is hard to walk back.
    SECURE_SSL_REDIRECT = env_bool('EGAZETTE_SSL_REDIRECT', False)
    SECURE_HSTS_SECONDS = env_int('EGAZETTE_HSTS_SECONDS', 0)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(
        'EGAZETTE_HSTS_INCLUDE_SUBDOMAINS', False
    )
    SECURE_HSTS_PRELOAD = env_bool('EGAZETTE_HSTS_PRELOAD', False)

# --- logging --------------------------------------------------------------

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s %(name)s %(levelname)s %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': env('EGAZETTE_LOG_LEVEL', 'INFO'),
    },
}
