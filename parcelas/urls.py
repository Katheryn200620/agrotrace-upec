from django.urls import path

from cuentas.mixins import crud_urls

from . import views

app_name = "parcelas"
urlpatterns = crud_urls("parcela", views.ParcelaLista, views.ParcelaDetalle, views.ParcelaCrear, views.ParcelaEditar,
                        views.ParcelaEliminar, views.ParcelaRevisar)
urlpatterns += [
    path("labores/", views.LaborLista.as_view(), name="labor_lista"),
    path("labores/nueva/", views.LaborCrear.as_view(), name="labor_crear"),
    path("labores/<int:pk>/", views.LaborDetalle.as_view(), name="labor_detalle"),
    path("labores/<int:pk>/editar/", views.LaborEditar.as_view(), name="labor_editar"),
    path("labores/<int:pk>/eliminar/", views.LaborEliminar.as_view(), name="labor_eliminar"),
    path("labores/<int:pk>/revisar/", views.LaborRevisar.as_view(), name="labor_revisar"),
    path("mapa.geojson", views.parcelas_geojson, name="geojson"),
]
