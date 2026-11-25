from django.contrib import admin

from .models import Lote,RelacionLote

for m in (Lote,RelacionLote,):
    admin.site.register(m)
