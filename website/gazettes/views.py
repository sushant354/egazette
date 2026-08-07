"""Reader-facing views.

Every gazette is published at ``/details/<identifier>/`` where the identifier
is the same one the scraper uses for the Internet Archive, so a citation of
either resolves in the other.

The legallayout HTML is the canonical rendering: it is what gets indexed and
what the detail page shows. The pymupdf rendering is offered alongside it as
an alternate view for cases where the layout conversion lost something, and is
served into a sandboxed frame because it is a mass of absolutely positioned
divs that only holds together as a standalone document.
"""

import logging
import os

from django.conf import settings
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import (
    FileResponse,
    Http404,
    HttpResponse,
    HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404, render
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_safe

from gazettes.forms import SearchForm
from gazettes.models import Gazette, Source
from gazettes.services import render as render_service
from gazettes.services import sources as sources_service
from gazettes.services import storage as storage_service
from gazettes.services.search import SearchCriteria, SearchService, archive_stats

logger = logging.getLogger(__name__)

# A converted PDF has no business loading anything or running anything.
FRAME_CSP = (
    "default-src 'none'; img-src data:; style-src 'unsafe-inline'; "
    "font-src data:; sandbox"
)


def _storage():
    return storage_service.default_storage()


def _x_accel_path(storage, path):
    """Map an on-disk asset to its nginx internal location.

    Each data root is exposed as ``<prefix><index>/`` by deploy/nginx.conf, so
    the reply names the root the file was found in and the path within it.
    Returns None when the file is not under any configured root.
    """
    resolved = os.path.realpath(path)
    prefix = settings.GAZETTE_X_ACCEL_PREFIX.rstrip('/')

    for index, root in enumerate(storage.roots):
        root = os.path.realpath(root)
        if resolved == root or resolved.startswith(root + os.sep):
            relative = os.path.relpath(resolved, root)
            return '%s/%d/%s' % (prefix, index, relative)
    return None


@require_safe
def home(request):
    stats = archive_stats()

    recent = list(
        Gazette.objects.with_source()
        .exclude(date__isnull=True)
        .order_by('-date', '-id')[:8]
    )

    # Only sources that hold something, biggest first, for the browse panel.
    top_sources = list(
        Source.objects.filter(gazette_count__gt=0).order_by('-gazette_count')[:12]
    )

    return render(request, 'gazettes/home.html', {
        'form': SearchForm(),
        'stats': stats,
        'recent': recent,
        'top_sources': top_sources,
        'source_total': Source.objects.filter(gazette_count__gt=0).count(),
    })


@require_safe
def search(request):
    form = SearchForm(request.GET or None)
    criteria = form.criteria() if request.GET else SearchCriteria()

    service = SearchService()
    queryset = service.search(criteria)

    paginator = Paginator(queryset, settings.RESULTS_PER_PAGE)
    page = paginator.get_page(request.GET.get('page'))

    headlines = service.headlines(page.object_list, criteria)

    results = []
    for gazette in page.object_list:
        results.append({
            'gazette': gazette,
            'headline': headlines.get(gazette.pk),
        })

    return render(request, 'gazettes/search.html', {
        'form': form,
        'criteria': criteria,
        'page': page,
        'paginator': paginator,
        'results': results,
        'source_facets': service.source_facets(criteria, limit=15),
        'year_facets': service.year_facets(criteria, limit=25),
    })


def _get_gazette(identifier):
    return get_object_or_404(
        Gazette.objects.with_source(), identifier=identifier
    )


def _rendered_body(gazette, storage):
    """The sanitised legallayout body, cached on the content hash.

    Keying the cache on the HTML's sha256 means a re-ingested gazette picks up
    its new body without anything having to invalidate the entry.
    """
    cache_key = 'gazette:body:%s:%s' % (gazette.pk, gazette.html_sha256)
    cached = cache.get(cache_key)
    if cached is not None:
        return mark_safe(cached)

    data = storage.read('html', gazette.relurl)
    if data is None:
        return None

    body = render_service.sanitize(data)
    cache.set(cache_key, body)
    return mark_safe(body)


def _detail_context(request, gazette, storage):
    ia_url = settings.GAZETTE_IA_DETAILS_URL.rstrip('/') + '/' + gazette.identifier
    return {
        'gazette': gazette,
        'source': gazette.source,
        'languages': sources_service.language_names(gazette.source.languages),
        'ia_url': ia_url,
        'has_pdf': gazette.has_pdf and storage.find('raw', gazette.relurl),
        'has_pymupdf': gazette.has_pymupdf
        and storage.find('pymupdf', gazette.relurl),
    }


@require_safe
def detail(request, identifier):
    gazette = _get_gazette(identifier)
    storage = _storage()

    context = _detail_context(request, gazette, storage)
    body = _rendered_body(gazette, storage)

    context.update({
        'body': body,
        # The gazette is in the archive but its HTML has gone missing from
        # every data root; say so rather than showing a blank page.
        'body_missing': body is None,
        'view': 'html',
    })
    return render(request, 'gazettes/detail.html', context)


@require_safe
def detail_pymupdf(request, identifier):
    """The alternate pymupdf rendering, shown only on request."""
    gazette = _get_gazette(identifier)
    storage = _storage()

    if not storage.find('pymupdf', gazette.relurl):
        raise Http404('No pymupdf rendering for this gazette')

    context = _detail_context(request, gazette, storage)
    context.update({'view': 'pymupdf'})
    return render(request, 'gazettes/detail_pymupdf.html', context)


@require_safe
def pymupdf_frame(request, identifier):
    """The raw pymupdf document, for the sandboxed frame to load.

    Served with a restrictive CSP in addition to the frame's sandbox
    attribute, because this markup came out of an automated conversion of a
    third-party PDF and is never sanitised.
    """
    gazette = _get_gazette(identifier)
    data = _storage().read('pymupdf', gazette.relurl)
    if data is None:
        raise Http404('No pymupdf rendering for this gazette')

    response = HttpResponse(data, content_type='text/html; charset=utf-8')
    response['Content-Security-Policy'] = FRAME_CSP
    response['X-Content-Type-Options'] = 'nosniff'
    response['X-Frame-Options'] = 'SAMEORIGIN'
    return response


@require_safe
def gazette_pdf(request, identifier):
    """The gazette as published.

    The PDF corpus is far larger than the site's own data, so a deployment
    that does not hold it locally sends the reader to the Internet Archive
    item with the same identifier instead of 404ing.
    """
    gazette = _get_gazette(identifier)
    storage = _storage()
    path = storage.find('raw', gazette.relurl)

    if path is None:
        return HttpResponseRedirect(
            settings.GAZETTE_IA_DETAILS_URL.rstrip('/') + '/' + gazette.identifier
        )

    filename = '%s%s' % (gazette.identifier, os.path.splitext(path)[1])

    if settings.GAZETTE_USE_X_ACCEL:
        # Hand the file off to nginx; see the internal location block in
        # deploy/nginx.conf. The alias there is per-root, so the redirect has
        # to be relative to the root the file was actually found in -- with
        # several data roots configured it is often not the first one.
        internal = _x_accel_path(storage, path)
        if internal is None:
            logger.error('X-Accel is on but %s is outside every data root',
                         path)
            raise Http404('gazette file is not available')

        response = HttpResponse()
        del response['Content-Type']
        response['X-Accel-Redirect'] = internal
        response['Content-Disposition'] = 'inline; filename="%s"' % filename
        return response

    return FileResponse(
        open(path, 'rb'), content_type='application/pdf', filename=filename
    )


@require_safe
def source_list(request):
    sources = list(
        Source.objects.filter(gazette_count__gt=0).order_by('title')
    )
    empty_sources = list(
        Source.objects.filter(gazette_count=0).order_by('title')
    )
    return render(request, 'gazettes/source_list.html', {
        'sources': sources,
        'empty_sources': empty_sources,
        'total': sum(source.gazette_count for source in sources),
    })


@require_safe
def source_detail(request, name):
    source = get_object_or_404(Source, name=name)

    queryset = (
        Gazette.objects.with_source()
        .filter(source=source)
        .order_by('-date', '-id')
    )

    year = request.GET.get('year')
    selected_year = None
    if year and year.isdigit():
        selected_year = int(year)
        queryset = queryset.filter(year=selected_year)

    paginator = Paginator(queryset, settings.RESULTS_PER_PAGE)
    page = paginator.get_page(request.GET.get('page'))

    years = list(
        Gazette.objects.filter(source=source)
        .exclude(year__isnull=True)
        .values('year')
        .annotate(total=Count('id'))
        .order_by('-year')
    )

    return render(request, 'gazettes/source_detail.html', {
        'source': source,
        'languages': sources_service.language_names(source.languages),
        'page': page,
        'paginator': paginator,
        'years': years,
        'selected_year': selected_year,
        'form': SearchForm(initial={'source': [source.name]}),
    })


@require_safe
def about(request):
    return render(request, 'gazettes/about.html', {
        'stats': archive_stats(),
        'source_count': Source.objects.filter(gazette_count__gt=0).count(),
    })


def page_not_found(request, exception=None):
    return render(request, '404.html', status=404)


def server_error(request):
    return render(request, '500.html', status=500)
