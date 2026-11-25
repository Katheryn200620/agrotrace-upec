from django.urls import path

from . import views
from .areas import AREAS

app_name = "dashboard"
urlpatterns = [
    path("alertas/", views.alertas, name="alertas"),
    path("hoja-de-ruta/", views.hoja_ruta, name="hoja_ruta"),
]
for _a in AREAS:
    urlpatterns.append(path(f"areas/{_a[0]}/", views.panel_area, {"clave": _a[0]}, name=f"area_{_a[0]}"))
