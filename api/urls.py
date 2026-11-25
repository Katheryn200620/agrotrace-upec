from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from . import views as v

router = DefaultRouter()
for prefijo, vs in [("productores", v.Productores), ("parcelas", v.Parcelas), ("labores", v.Labores), ("productos", v.Productos),
                    ("cosechas", v.Cosechas), ("recepciones", v.Recepciones), ("clasificaciones", v.Clasificaciones),
                    ("lotes", v.Lotes), ("transportistas", v.Transportistas), ("despachos", v.Despachos),
                    ("clientes", v.Clientes), ("ventas", v.Ventas), ("eventos", v.Eventos)]:
    router.register(prefijo, vs, basename=prefijo)

urlpatterns = [
    path("token/", obtain_auth_token, name="api_token"),
    path("trazabilidad/<str:codigo>/", v.trazabilidad_lote, name="api_trazabilidad"),
    path("indicadores/", v.indicadores, name="api_indicadores"),
    path("", include(router.urls)),
]
