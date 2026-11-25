from django.urls import path

from . import views

app_name = "cuentas"
urlpatterns = [
    path("perfil/", views.perfil, name="perfil"),
    path("mi-historial/", views.mi_historial, name="mi_historial"),
    path("usuarios/", views.usuarios, name="usuarios"),
    path("usuarios/nuevo/", views.usuario_crear, name="usuario_crear"),
    path("usuarios/<int:pk>/", views.usuario_editar, name="usuario_editar"),
    path("usuarios/<int:pk>/activar/", views.usuario_activar, name="usuario_activar"),
    path("areas/<int:pk>/activar/", views.area_activar, name="area_activar"),
    path("auditoria/", views.auditoria, name="auditoria"),
]
