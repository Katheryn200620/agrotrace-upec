from django.urls import path

from . import views
from .agentes import AGENTES, clase_agente

app_name = "asistente"
urlpatterns = [
    path("", views.chat, name="chat"),
    path("mensaje/", views.mensaje, name="mensaje"),
    path("mensaje/<int:pk>/valorar/", views.valorar, name="valorar"),
    path("voz/", views.voz, name="voz"),
    path("voz/registrar/", views.registrar_voz, name="registrar_voz"),
    path("agentes/", views.agentes, name="agentes"),
    path("agentes/trazabilidad/", views.agente_trazabilidad, name="agente_trazabilidad"),
    path("uso/", views.uso, name="uso"),
]
for _clave in AGENTES:
    urlpatterns.append(path(f"agentes/{_clave}/", clase_agente(_clave).as_view(), name=f"agente_{_clave}"))
