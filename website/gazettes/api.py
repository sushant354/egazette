"""HTTP ingest endpoint.

This is how the website is updated. ``tools/push_gazettes.py`` walks a gazette
data directory on the machine that runs the scraper and posts each gazette
here; the endpoint hands the payload to the same
:class:`~gazettes.services.ingest.IngestService` that the local
``manage.py ingest_gazettes`` command uses, so both routes agree on what a
valid gazette is.

    POST /api/ingest/status/   which relurls the site already holds
    POST /api/ingest/          upload one gazette

Requests authenticate with a shared secret from ``EGAZETTE_INGEST_TOKENS``,
sent as ``Authorization: Bearer <token>``. With no tokens configured the
endpoint is closed, so a site that is only ever updated locally does not
expose a write path at all.

Metadata and the legallayout HTML are required. The PDF and the pymupdf
rendering are optional, and can be left out entirely when the site can already
see them in one of its data roots -- which is the normal case when the site
and the scraper share a host.
"""

import hmac
import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from gazettes.models import Gazette
from gazettes.services import storage as storage_service
from gazettes.services.ingest import ERROR, IngestService

logger = logging.getLogger(__name__)

MAX_STATUS_RELURLS = 2000

# The extensions the scraper stores raw gazettes under; see
# egazette.utils.utils.get_file_extension. 'unkwn' is what it writes when the
# server sent a content type it does not recognise.
ALLOWED_RAW_EXTENSIONS = frozenset(
    ['.pdf', '.html', '.htm', '.txt', '.ps', '.png', '.unkwn']
)


def _unauthorized(message='authentication required'):
    response = JsonResponse({'error': message}, status=401)
    response['WWW-Authenticate'] = 'Bearer realm="gazette-ingest"'
    return response


def _authenticate(request):
    """Return None when the request may write, or an error response."""
    tokens = settings.GAZETTE_INGEST_TOKENS
    if not tokens:
        return JsonResponse(
            {'error': 'ingest API is disabled; set EGAZETTE_INGEST_TOKENS'},
            status=503,
        )

    header = request.headers.get('Authorization', '')
    presented = ''
    if header.lower().startswith('bearer '):
        presented = header[7:].strip()
    elif request.headers.get('X-Ingest-Token'):
        presented = request.headers['X-Ingest-Token'].strip()

    if not presented:
        return _unauthorized()

    # compare_digest against every configured token so that a rejected request
    # takes the same time whichever token it got wrong.
    matched = False
    for token in tokens:
        if hmac.compare_digest(presented, token):
            matched = True
    if not matched:
        return _unauthorized('invalid token')

    return None


def _too_large(name, size):
    return JsonResponse(
        {
            'error': '%s is %d bytes, over the %d byte limit'
                     % (name, size, settings.GAZETTE_MAX_UPLOAD_BYTES),
        },
        status=413,
    )


@csrf_exempt
@require_POST
def ingest(request):
    """Ingest a single gazette from an upload."""
    denied = _authenticate(request)
    if denied is not None:
        return denied

    relurl = (request.POST.get('relurl') or '').strip()
    try:
        relurl = storage_service.validate_relurl(relurl)
    except storage_service.InvalidRelurl as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    payload = {}
    for name in ('metatags', 'html', 'pymupdf', 'raw'):
        uploaded = request.FILES.get(name)
        if uploaded is None:
            continue
        if uploaded.size > settings.GAZETTE_MAX_UPLOAD_BYTES:
            return _too_large(name, uploaded.size)
        payload[name] = uploaded

    raw_extension = (request.POST.get('raw_extension') or '').strip() or None
    if raw_extension is None and 'raw' in payload:
        name = payload['raw'].name or ''
        raw_extension = ('.' + name.rsplit('.', 1)[1]) if '.' in name else '.pdf'
    if raw_extension is not None and not _is_safe_extension(raw_extension):
        return JsonResponse(
            {'error': 'unsupported raw_extension %r' % raw_extension},
            status=400,
        )

    force = (request.POST.get('force') or '').lower() in ('1', 'true', 'yes')

    service = IngestService()
    result = service.ingest(
        relurl,
        metatags=payload.get('metatags'),
        html=payload.get('html'),
        pymupdf=payload.get('pymupdf'),
        raw=payload.get('raw'),
        raw_extension=raw_extension,
        force=force,
    )

    if result.status != ERROR:
        status = 200
    elif result.client_error:
        # The gazette itself is at fault; retrying it unchanged will not help.
        status = 422
    else:
        status = 500
    return JsonResponse(result.as_dict(), status=status)


@csrf_exempt
@require_POST
def ingest_status(request):
    """Report what the site already holds for a batch of relurls.

    The push tool calls this first so it can skip gazettes whose HTML has not
    changed, rather than re-uploading hundreds of megabytes to find out.

    Body: {"relurls": ["central_extraordinary/2024-04-18/253767", ...]}
    """
    denied = _authenticate(request)
    if denied is not None:
        return denied

    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError) as exc:
        return JsonResponse({'error': 'invalid JSON: %s' % exc}, status=400)

    relurls = body.get('relurls')
    if not isinstance(relurls, list):
        return JsonResponse({'error': 'relurls must be a list'}, status=400)
    if len(relurls) > MAX_STATUS_RELURLS:
        return JsonResponse(
            {'error': 'at most %d relurls per request' % MAX_STATUS_RELURLS},
            status=400,
        )

    wanted = []
    for relurl in relurls:
        try:
            wanted.append(storage_service.validate_relurl(relurl))
        except storage_service.InvalidRelurl:
            continue

    known = {
        row['relurl']: row
        for row in Gazette.objects.filter(relurl__in=wanted).values(
            'relurl', 'identifier', 'html_sha256', 'metadata_sha256',
            'has_pdf', 'has_pymupdf',
        )
    }

    return JsonResponse({'gazettes': known})


def _is_safe_extension(extension):
    """Whether an uploaded raw file may be stored under this extension.

    An allowlist rather than a character check: the raw directory is served to
    readers, so the set of extensions that can be written into it should be
    exactly the set ``egazette.utils.utils.get_file_extension`` produces, and
    nothing an uploader invents.
    """
    return extension.lower() in ALLOWED_RAW_EXTENSIONS
