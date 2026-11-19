"""Combine the original backend API unchanged with the supplied frontend pages."""
from django.contrib import admin
from django.urls import include, path
from routes import views as backend_views

urlpatterns = [
    path("admin/", admin.site.urls),
    # Existing provider-backend API URLs and handlers (not replaced).
    path("api/search/", backend_views.search_api, name="search_api"),
    path("api/flights/", backend_views.flights_api, name="flights_api"),
    path("api/saved/", backend_views.saved_api, name="saved_api"),
    path("api/draft/", backend_views.save_draft_api, name="save_draft_api"),
    path("api/clear/", backend_views.clear_saved, name="clear_saved_api"),
    path("clear-saved/", backend_views.clear_saved, name="clear_saved"),
    # The backend's old testing webpage is available separately (no UI conflict).
    path("backend/", backend_views.home, name="home"),
    # Original frontend uses '/' and its existing templates/static styles.
    path("", include("planner.urls")),
]
