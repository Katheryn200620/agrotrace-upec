from django.urls import include, path

from cuentas.mixins import crud_urls

from . import views as v

app_name = "transporte"
urlpatterns = crud_urls("despacho", v.DLista, v.DDetalle, v.DCrear, v.DEditar, None, v.DRevisar)
urlpatterns += [
    path("<int:pk>/salir/", v.salir, name="despacho_salir"),
    path("<int:pk>/entregar/", v.entregar, name="despacho_entregar"),
    path("<int:pk>/cancelar/", v.cancelar, name="despacho_cancelar"),
    path("transportistas/", include(crud_urls("transportista", v.TLista, v.TDetalle, v.TCrear, v.TEditar,
                                              v.TEliminar, v.TRevisar))),
]
