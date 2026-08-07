from django.conf import settings


def site(request):
    """Site-wide names used by the masthead and page titles."""
    return {
        'site_name': settings.SITE_NAME,
        'site_tagline': settings.SITE_TAGLINE,
    }
