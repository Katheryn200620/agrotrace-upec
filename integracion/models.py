from django.conf import settings
from django.db import models


class SincronizacionERP(models.Model):
    """Bitácora de cada prueba de conexión o sincronización con Odoo."""
    fecha = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    modo = models.CharField(max_length=15, choices=[("prueba", "Prueba de conexión"), ("sincronizacion", "Sincronización")])
    exito = models.BooleanField(default=False)
    version_odoo = models.CharField(max_length=40, blank=True)
    resumen = models.JSONField(default=dict, blank=True)
    detalle = models.TextField(blank=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "sincronización con Odoo"
        verbose_name_plural = "sincronizaciones con Odoo"
