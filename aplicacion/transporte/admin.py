from django.contrib import admin

from .models import Transportista,Despacho

for m in (Transportista,Despacho,):
    admin.site.register(m)
