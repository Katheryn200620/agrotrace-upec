from django.urls import include, path

from cuentas.mixins import crud_urls

from . import views as v

app_name = "cosechas"
urlpatterns = crud_urls("cosecha", v.CosechaLista, v.CosechaDetalle, v.CosechaCrear, v.CosechaEditar,
                        v.CosechaEliminar, v.CosechaRevisar)
urlpatterns += [
    path("recepciones/", include(crud_urls("recepcion", v.RecepcionLista, v.RecepcionDetalle, v.RecepcionCrear,
                                           v.RecepcionEditar, v.RecepcionEliminar, v.RecepcionRevisar))),
    path("clasificaciones/", include(crud_urls("clasificacion", v.ClasificacionLista, v.ClasificacionDetalle,
                                               v.ClasificacionCrear, v.ClasificacionEditar, v.ClasificacionEliminar,
                                               v.ClasificacionRevisar))),
]
