from django import template
from django.core.paginator import Paginator

register = template.Library()

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
