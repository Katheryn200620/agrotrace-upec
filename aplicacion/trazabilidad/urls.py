from django.urls import path

from . import views

app_name = "trazabilidad"
urlpatterns = [
    path("", views.evento_lista, name="evento_lista"),
    path("nuevo/", views.evento_crear, name="evento_crear"),
    path("<int:pk>/", views.evento_detalle, name="evento_detalle"),
    path("<int:pk>/corregir/", views.evento_corregir, name="evento_corregir"),
    path("simulacros/", views.simulacros, name="simulacros"),
    path("simulacros/registrar/", views.simulacro_registrar, name="simulacro_registrar"),
    path("simulacros/iniciar/", views.simulacro_iniciar, name="simulacro_iniciar"),
    path("simulacros/terminar/", views.simulacro_terminar, name="simulacro_terminar"),
    path("api/lotes/<int:pk>/epcis/", views.lote_epcis, name="lote_epcis"),
    path("api/contratos/cosecha/<int:pk>/", views.contrato_cosecha, name="contrato_cosecha"),
    path("api/contratos/despacho/<int:pk>/", views.contrato_despacho, name="contrato_despacho"),
]
