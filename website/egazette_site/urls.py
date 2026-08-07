from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('gazettes.urls')),
]

handler404 = 'gazettes.views.page_not_found'
handler500 = 'gazettes.views.server_error'
