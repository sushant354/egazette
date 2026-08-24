from urllib.parse import urlencode

from django import template
from django.core.paginator import Paginator
from django.urls import reverse

register = template.Library()

# Sending a reader back to one of these after signing in would either bounce
# them straight out again or, for the login page itself, trip Django's
# redirect-loop guard.
NO_RETURN_TO = {'login', 'logout', 'signup'}

ELLIPSIS = Paginator.ELLIPSIS


@register.simple_tag
def elided_page_range(page, on_each_side=2, on_ends=1):
    """Page numbers around the current one, with ellipses.

    ``Paginator.get_elided_page_range`` takes arguments, which the template
    language cannot pass, so it is wrapped here.
    """
    return list(
        page.paginator.get_elided_page_range(
            page.number, on_each_side=on_each_side, on_ends=on_ends
        )
    )


@register.filter
def is_ellipsis(value):
    return value == ELLIPSIS


@register.filter
def without(values, item):
    """The list minus one entry.

    Lets a 'remove this filter' link drop a single selected series while
    keeping the rest, since {% querystring %} can only set a parameter to a
    whole new value.
    """
    return [value for value in values or [] if value != item]


@register.filter
def intcomma_in(value):
    """Group digits the Indian way: 1,23,45,678.

    Counts on this site run into the lakhs, and Django's humanize intcomma
    groups in thousands, which reads wrong for the audience.
    """
    if value is None:
        return ''
    try:
        number = int(value)
    except (TypeError, ValueError):
        return value

    sign = '-' if number < 0 else ''
    digits = str(abs(number))

    if len(digits) <= 3:
        return sign + digits

    last3 = digits[-3:]
    rest = digits[:-3]

    groups = []
    while len(rest) > 2:
        groups.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        groups.insert(0, rest)

    return sign + ','.join(groups + [last3])


@register.filter
def in_set(value, container):
    """True when ``value`` is in ``container``.

    The bookmark button needs that answer in a ``{% with %}`` so the markup is
    written once for both states, and the ``in`` operator of ``{% if %}``
    cannot be assigned to a variable.
    """
    try:
        return value in (container or ())
    except TypeError:
        return False


@register.simple_tag(takes_context=True)
def signin_url(context, name='gazettes:login'):
    """The sign-in (or signup) URL, carrying the current page as ``next``.

    A reader who signs in from a gazette page should land back on it, ready to
    bookmark it. The account pages themselves are excluded: returning to them
    is either pointless or, for login, a redirect loop.
    """
    url = reverse(name)
    request = context.get('request')
    if request is None:
        return url

    match = getattr(request, 'resolver_match', None)
    if match is not None and match.url_name in NO_RETURN_TO:
        return url

    return '%s?%s' % (url, urlencode({'next': request.get_full_path()}))
