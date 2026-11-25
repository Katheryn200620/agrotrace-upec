from django.urls import path

from . import views

app_name = "reportes"
urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("datos/<str:nombre>.csv", views.dataset, name="dataset"),
]
