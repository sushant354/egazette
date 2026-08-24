"""Reader accounts and bookmarks.

An account on this site buys exactly one thing: bookmarks that follow the
reader between devices. Nothing else is gated -- search, browsing and every
gazette page stay open to anonymous readers, and always should, because the
archive is a public record.

Sign-in and sign-out are Django's own views with the site's forms and
templates. Signup and the bookmark endpoints are here because they are the
parts that are ours.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST, require_safe

from gazettes.forms import LoginForm, SignupForm
from gazettes.models import Bookmark, Gazette


class Login(auth_views.LoginView):
    template_name = 'accounts/login.html'
    authentication_form = LoginForm
    # A reader who is already signed in has nothing to do on this page.
    redirect_authenticated_user = True

    def get_redirect_url(self):
        """Where to land after signing in.

        A hand-typed ``?next=/accounts/login/`` would send the reader back
        here -- and with redirect_authenticated_user on, Django treats that as
        a redirect loop and raises. Drop it and use the default instead.
        """
        url = super().get_redirect_url()
        return '' if url == self.request.path else url

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # LoginView fills site_name from the Sites framework, which without
        # django.contrib.sites is the bare hostname. The masthead and page
        # title read that variable, so restore the archive's own name.
        context['site_name'] = settings.SITE_NAME
        return context


class Logout(auth_views.LogoutView):
    # POST-only, which is Django's default: a GET sign-out can be triggered by
    # any page that manages to load a URL of ours.
    next_page = reverse_lazy('gazettes:home')


def _safe_next(request, fallback):
    """The ``next`` the request asked for, if it is a URL on this site.

    Both the bookmark button and signup carry the reader back where they came
    from, and either would otherwise be an open redirect.
    """
    target = request.POST.get('next') or request.GET.get('next') or ''
    if target and url_has_allowed_host_and_scheme(
        target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return target
    return fallback


def signup(request):
    """Create an account and sign straight in on it."""
    if request.user.is_authenticated:
        return redirect(_safe_next(request, reverse('gazettes:home')))

    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            messages.success(
                request,
                'Welcome, %s. Bookmarks you save are kept on your account.'
                % user.username,
            )
            return redirect(_safe_next(request, reverse('gazettes:home')))
    else:
        form = SignupForm()

    return render(request, 'accounts/signup.html', {
        'form': form,
        'next': _safe_next(request, ''),
    })


@login_required
@require_safe
def profile(request):
    """The reader's own account page, behind the header dropdown."""
    return render(request, 'accounts/profile.html', {
        'bookmark_count': Bookmark.objects.filter(user=request.user).count(),
    })


@login_required
@require_safe
def bookmarks(request):
    """Everything this reader has saved, newest first."""
    queryset = (
        Bookmark.objects.filter(user=request.user)
        .select_related('gazette', 'gazette__source')
    )

    paginator = Paginator(queryset, settings.RESULTS_PER_PAGE)
    page = paginator.get_page(request.GET.get('page'))

    return render(request, 'accounts/bookmarks.html', {
        'page': page,
        'paginator': paginator,
        'total': paginator.count,
        # Everything on this page is bookmarked by definition; the listing
        # partial still wants the set so its button reads "Bookmarked".
        'bookmarked_pks': {mark.gazette_id for mark in page.object_list},
    })


@login_required
@require_POST
def bookmark(request, identifier):
    """Save or drop one gazette.

    The form says which of the two it means, so that a resubmitted page (or a
    double tap on a slow connection) lands on the state the reader asked for
    instead of flipping it back. Anything else toggles.
    """
    gazette = get_object_or_404(Gazette, identifier=identifier)
    action = request.POST.get('action', '')

    if action == 'remove':
        saved = False
    elif action == 'add':
        saved = True
    else:
        saved = not Bookmark.objects.filter(
            user=request.user, gazette=gazette
        ).exists()

    if saved:
        # get_or_create resolves a race between two submits against the
        # unique constraint itself, so a double tap cannot 500 here.
        Bookmark.objects.get_or_create(user=request.user, gazette=gazette)
        messages.success(request, 'Bookmarked "%s".' % _short(gazette.title))
    else:
        Bookmark.objects.filter(user=request.user, gazette=gazette).delete()
        messages.info(request, 'Removed the bookmark on "%s".'
                      % _short(gazette.title))

    return redirect(_safe_next(request, gazette.get_absolute_url()))


def _short(title, limit=70):
    title = ' '.join(title.split())
    return title if len(title) <= limit else title[:limit - 1] + '…'
