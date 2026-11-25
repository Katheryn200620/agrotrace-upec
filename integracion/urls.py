from django.urls import path

from . import views

app_name = "integracion"
urlpatterns = [
    path("", views.estado, name="estado"),
    path("ejecutar/", views.ejecutar, name="ejecutar"),
]
