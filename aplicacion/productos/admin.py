from django.contrib import admin

from .models import Producto

for m in (Producto,):
    admin.site.register(m)
