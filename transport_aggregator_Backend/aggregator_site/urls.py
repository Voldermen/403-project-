"""Public Django routes, including saved search/draft APIs."""
from django.urls import path
from routes import views

urlpatterns = [
    path("", views.home, name="home"),
    path("api/search/", views.search_api, name="search_api"),
    path("api/flights/", views.flights_api, name="flights_api"),
    path("api/saved/", views.saved_api, name="saved_api"),
    path("api/draft/", views.save_draft_api, name="save_draft_api"),
    path("api/clear/", views.clear_saved, name="clear_saved_api"),
    path("clear-saved/", views.clear_saved, name="clear_saved"),
]
