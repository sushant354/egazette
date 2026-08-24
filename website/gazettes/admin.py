from django.contrib import admin

from gazettes.models import Bookmark, Gazette, Source


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'title', 'authority', 'gazette_count',
                    'earliest_date', 'latest_date')
    search_fields = ('name', 'title', 'authority')
    ordering = ('name',)
    # Source rows are rebuilt from srcinfos by `manage.py sync_sources`;
    # editing them here would be overwritten on the next sync.
    readonly_fields = ('name', 'title', 'authority', 'languages', 'ia_prefix',
                       'start_date', 'gazette_count', 'earliest_date',
                       'latest_date')

    def has_add_permission(self, request):
        return False


@admin.register(Gazette)
class GazetteAdmin(admin.ModelAdmin):
    list_display = ('identifier', 'source', 'date', 'has_pdf', 'has_pymupdf',
                    'updated_at')
    list_filter = ('source', 'has_pdf', 'has_pymupdf', 'text_truncated')
    search_fields = ('identifier', 'relurl', 'title', 'subject')
    date_hierarchy = 'date'
    ordering = ('-date',)
    raw_id_fields = ('source',)
    exclude = ('search_vector',)
    readonly_fields = ('text', 'html_sha256', 'metadata_sha256', 'metadata',
                       'created_at', 'updated_at')

    def has_add_permission(self, request):
        return False


@admin.register(Bookmark)
class BookmarkAdmin(admin.ModelAdmin):
    list_display = ('user', 'gazette', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'gazette__identifier', 'gazette__title')
    raw_id_fields = ('user', 'gazette')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
