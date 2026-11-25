from django.urls import include, path

from cuentas.mixins import crud_urls

from . import views as v

app_name = "comercial"
urlpatterns = crud_urls("venta", v.VLista, v.VDetalle, v.VCrear, v.VEditar, None, v.VRevisar)
urlpatterns += [
    path("<int:pk>/anular/", v.anular, name="venta_anular"),
    path("disponible/<int:lote_pk>/", v.disponible, name="disponible"),
    path("clientes/", include(crud_urls("cliente", v.CLista, v.CDetalle, v.CCrear, v.CEditar, v.CEliminar, v.CRevisar))),
]
