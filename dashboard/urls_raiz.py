from django.urls import path

from . import views

urlpatterns = [
    path("", views.portada, name="inicio"),                                   # página de Inicio (catálogo)
    path("panel-procedencia/", views.inicio, name="panel_procedencia"),      # panel de procedencia de siempre
    path("buscar/", views.buscar, name="buscar"),
]
