from django.contrib import admin

from .models import Productor

for m in (Productor,):
    admin.site.register(m)
