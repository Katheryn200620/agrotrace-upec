from cuentas.mixins import crud_urls

from . import views

app_name = "productores"
urlpatterns = crud_urls("productor", views.Lista, views.Detalle, views.Crear, views.Editar, views.Eliminar, views.Revisar)
