from django.contrib import admin

from .models import Parcela,Labor

for m in (Parcela,Labor,):
    admin.site.register(m)
