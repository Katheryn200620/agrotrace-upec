from django.contrib import admin

from .models import EventoTrazabilidad,EscaneoQR,SimulacroRetiro

for m in (EventoTrazabilidad,EscaneoQR,SimulacroRetiro,):
    admin.site.register(m)
