from cuentas.mixins import crud_urls

from . import views

app_name = "productos"
urlpatterns = crud_urls("producto", views.Lista, views.Detalle, views.Crear, views.Editar, views.Eliminar, views.Revisar)
