from django.urls import path
from . import views

app_name = "planner"
urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("results/", views.results, name="results"),
    path("api/addresses/", views.addresses, name="addresses"),
]
