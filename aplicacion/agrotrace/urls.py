from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from cuentas.views import Ingreso
from api import views as api_views
from trazabilidad import views as traz

admin.site.site_header = "AgroTrace-UPEC · Administración técnica"
admin.site.site_title = "AgroTrace-UPEC"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("ingresar/", Ingreso.as_view(), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("cuentas/", include("cuentas.urls")),
    path("productores/", include("productores.urls")),
    path("parcelas/", include("parcelas.urls")),
    path("productos/", include("productos.urls")),
    path("cosechas/", include("cosechas.urls")),
    path("lotes/", include("lotes.urls")),
    path("trazabilidad/", include("trazabilidad.urls")),
    path("transporte/", include("transporte.urls")),
    path("reportes/", include("reportes.urls")),
    path("comercial/", include("comercial.urls")),
    path("api/v1/", include("api.urls")),
    path("asistente/", include("asistente.urls")),
    path("integracion/", include("integracion.urls")),
    path("api/docs/", api_views.documentacion, name="api_docs"),
    # Consulta pública de procedencia (lo que abre el QR)
    path("consulta/", traz.consulta, name="consulta"),
    path("01/<str:gtin>/10/<str:codigo>", traz.procedencia_gs1, name="procedencia_gs1"),
    path("panel/", include("dashboard.urls")),
    path("", include("dashboard.urls_raiz")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler403 = "dashboard.errores.error_403"
handler404 = "dashboard.errores.error_404"
handler500 = "dashboard.errores.error_500"
