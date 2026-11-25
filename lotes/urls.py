from django.urls import path

from cuentas.mixins import crud_urls

from . import views

app_name = "lotes"
urlpatterns = crud_urls("lote", views.Lista, views.Detalle, views.Crear, views.Editar, None, views.Revisar)
urlpatterns += [
    path("inventario/", views.inventario, name="inventario"),
    path("inventario/movimientos/", views.movimientos, name="movimientos"),
    path("etiquetas/", views.etiquetas, name="etiquetas"),
    path("<int:pk>/qr.png", views.qr_lote, name="qr"),
    path("<int:pk>/dividir/", views.dividir, name="dividir"),
    path("<int:pk>/combinar/", views.combinar, name="combinar"),
    path("<int:pk>/transformar/", views.transformar, name="transformar"),
    path("<int:pk>/retirar/", views.retirar, name="retirar"),
    path("<int:pk>/corregir-origen/", views.corregir_origen, name="corregir_origen"),
]
