from django.urls import path, re_path

from gazettes import accounts, api, views

app_name = 'gazettes'

# Identifiers come from datasrcs_info.get_identifier: a dotted prefix followed
# by the source's own scheme, so letters, digits, dots, dashes and the
# occasional underscore. Matching explicitly keeps a stray slash out.
IDENTIFIER = r'(?P<identifier>[A-Za-z0-9][A-Za-z0-9._+-]*)'

urlpatterns = [
    path('', views.home, name='home'),
    path('search/', views.search, name='search'),
    path('sources/', views.source_list, name='source_list'),
    path('sources/<str:name>/', views.source_detail, name='source_detail'),
    path('about/', views.about, name='about'),

    path('accounts/login/', accounts.Login.as_view(), name='login'),
    path('accounts/logout/', accounts.Logout.as_view(), name='logout'),
    path('accounts/signup/', accounts.signup, name='signup'),
    path('account/', accounts.profile, name='account'),
    path('bookmarks/', accounts.bookmarks, name='bookmarks'),

    re_path(r'^details/%s/$' % IDENTIFIER, views.detail, name='detail'),
    re_path(r'^details/%s/pymupdf/$' % IDENTIFIER, views.detail_pymupdf,
            name='detail_pymupdf'),
    re_path(r'^details/%s/pymupdf/frame/$' % IDENTIFIER, views.pymupdf_frame,
            name='pymupdf_frame'),
    re_path(r'^details/%s/pdf/$' % IDENTIFIER, views.gazette_pdf,
            name='gazette_pdf'),
    re_path(r'^details/%s/bookmark/$' % IDENTIFIER, accounts.bookmark,
            name='bookmark'),

    path('api/ingest/', api.ingest, name='api_ingest'),
    path('api/ingest/status/', api.ingest_status, name='api_ingest_status'),
]
