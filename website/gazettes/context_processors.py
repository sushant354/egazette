from django.conf import settings
from django.utils.functional import SimpleLazyObject

from gazettes.models import Bookmark

# How many saved gazettes the header dropdown lists before sending the reader
# to the full page. Enough to recognise recent work, short enough that the
# menu stays a menu.
NAV_BOOKMARK_LIMIT = 6


def site(request):
    """Site-wide names used by the masthead and page titles."""
    return {
        'site_name': settings.SITE_NAME,
        'site_tagline': settings.SITE_TAGLINE,
    }


def _nav_bookmarks(user):
    """Recent bookmarks and the total, for the header dropdown.

    One row over the limit is fetched so that a reader with a short list is
    counted from the rows already in hand -- the COUNT only runs for the
    readers whose list is actually longer than the menu.
    """
    recent = list(
        Bookmark.objects.filter(user=user)
        .select_related('gazette', 'gazette__source')[:NAV_BOOKMARK_LIMIT + 1]
    )

    if len(recent) > NAV_BOOKMARK_LIMIT:
        total = Bookmark.objects.filter(user=user).count()
    else:
        total = len(recent)

    return {
        'bookmarks': recent[:NAV_BOOKMARK_LIMIT],
        'count': total,
        'limit': NAV_BOOKMARK_LIMIT,
    }


def account(request):
    """The signed-in reader's account menu contents.

    Lazy on purpose: this runs for every rendered page, and the queries should
    only happen on the ones that actually draw the menu -- which is the HTML
    pages, not the sandboxed pymupdf frame or a JSON reply.
    """
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}

    return {'account_nav': SimpleLazyObject(lambda: _nav_bookmarks(user))}
