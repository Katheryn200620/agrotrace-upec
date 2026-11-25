from django.contrib import admin

from .models import MensajeAsistente


@admin.register(MensajeAsistente)
class MensajeAdmin(admin.ModelAdmin):
    list_display = ("fecha", "usuario", "canal", "intencion", "fuente", "resuelto", "pregunta")
    list_filter = ("canal", "fuente", "resuelto")
