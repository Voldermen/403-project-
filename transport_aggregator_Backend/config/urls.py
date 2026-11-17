"""One Django website; every route search delegates to Algorithm/main_alg.py."""
from django.contrib import admin
from django.urls import include, path
from django.views.generic.base import RedirectView
from planner import api

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/search/', api.search_api, name='search_api'),
    path('api/flights/', api.flights_api, name='flights_api'),
    path('api/saved/', api.saved_api, name='saved_api'),
    path('api/draft/', api.save_draft_api, name='save_draft_api'),
    path('api/clear/', api.clear_saved, name='clear_saved_api'),
    path('clear-saved/', api.clear_saved, name='clear_saved'),
    path('backend/', RedirectView.as_view(pattern_name='planner:home', permanent=False)),
    path('', include('planner.urls')),
]
