from django.contrib import admin

from .models import Cosecha,Recepcion,Clasificacion

for m in (Cosecha,Recepcion,Clasificacion,):
    admin.site.register(m)
