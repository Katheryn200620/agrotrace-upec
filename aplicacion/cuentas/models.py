"""
Cuentas, áreas de trabajo y auditoría.

- Area: áreas de trabajo que el administrador general habilita y asigna.
- Perfil: datos de seguridad de cada usuario (administrador general u operador de un área).
- RegistroResponsable: modelo base para todos los registros que tienen un operador responsable.
- RegistroAuditoria: bitácora no editable de acciones importantes.
"""
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models
from django.utils import timezone


class Area(models.Model):
    PRODUCTORES = "productores"
    PARCELAS = "parcelas"
    PRODUCTOS = "productos"
    COSECHAS = "cosechas"
    LOTES = "lotes"
    TRAZABILIDAD = "trazabilidad"
    TRANSPORTE = "transporte"
    REPORTES = "reportes"
    COMERCIAL = "comercial"
    CODIGOS = [
        (PRODUCTORES, "Productores"),
        (PARCELAS, "Parcelas y cultivos"),
        (PRODUCTOS, "Productos hortofrutícolas"),
        (COSECHAS, "Cosechas"),
        (LOTES, "Lotes"),
        (TRAZABILIDAD, "Trazabilidad"),
        (TRANSPORTE, "Transporte y destinos"),
        (REPORTES, "Consulta, reportes y auditoría"),
        (COMERCIAL, "Clientes y ventas"),
    ]
    codigo = models.CharField(max_length=20, choices=CODIGOS, unique=True)
    nombre = models.CharField(max_length=60)
    descripcion = models.CharField(max_length=200, blank=True)
    activa = models.BooleanField(default=True, help_text="Solo las áreas activas pueden asignarse a operadores")

    class Meta:
        ordering = ["id"]
        verbose_name = "área de trabajo"
        verbose_name_plural = "áreas de trabajo"

    def __str__(self):
        return self.nombre


class Perfil(models.Model):
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil")
    es_admin_general = models.BooleanField("Administrador general", default=False)
    area = models.ForeignKey(Area, on_delete=models.PROTECT, null=True, blank=True, related_name="operadores")
    puede_crear = models.BooleanField(default=True)
    puede_editar = models.BooleanField(default=True)
    puede_eliminar = models.BooleanField(default=False)
    cargo = models.CharField(max_length=80, blank=True)
    actualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name="+")
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "perfil"
        verbose_name_plural = "perfiles"

    def __str__(self):
        return f"{self.usuario.get_username()} · {self.rol_legible}"

    @property
    def rol_legible(self):
        if self.es_admin_general:
            return "Administrador general"
        return f"Operador de {self.area.nombre.lower()}" if self.area else "Sin área asignada"


class RegistroResponsable(models.Model):
    """Base para los registros con un operador responsable y revisión del administrador."""
    REVISION = [("pendiente", "Pendiente de revisión"), ("aprobado", "Aprobado"), ("observado", "Observado")]
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+",
                                    verbose_name="Operador responsable")
    creado_en = models.DateTimeField("Fecha de creación", auto_now_add=True)
    actualizado_en = models.DateTimeField("Última actualización", auto_now=True)
    estado_revision = models.CharField("Revisión", max_length=10, choices=REVISION, default="pendiente")
    revisado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="+")
    revisado_en = models.DateTimeField(null=True, blank=True)
    nota_revision = models.CharField(max_length=200, blank=True)

    class Meta:
        abstract = True


class RegistroAuditoria(models.Model):
    """Bitácora de acciones. No se puede editar ni borrar desde la aplicación."""
    ACCIONES = [
        ("crear", "Creación"), ("editar", "Modificación"), ("eliminar", "Eliminación"),
        ("revisar", "Revisión"), ("evento", "Evento de trazabilidad"), ("operacion", "Operación de lote"),
        ("cuenta", "Gestión de cuentas"), ("ingreso", "Inicio de sesión"), ("salida", "Cierre de sesión"),
        ("ingreso_fallido", "Inicio de sesión fallido"), ("acceso_denegado", "Acceso denegado"),
        ("exportar", "Exportación de datos"),
    ]
    fecha = models.DateTimeField(default=timezone.now, db_index=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="acciones")
    usuario_nombre = models.CharField(max_length=150, blank=True)
    area = models.CharField(max_length=60, blank=True)
    accion = models.CharField(max_length=20, choices=ACCIONES)
    modulo = models.CharField(max_length=60, blank=True)
    objeto_id = models.CharField(max_length=40, blank=True)
    objeto = models.CharField(max_length=200, blank=True)
    detalle = models.TextField(blank=True)
    cambios = models.JSONField(default=dict, blank=True)
    justificacion = models.CharField(max_length=250, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "registro de auditoría"
        verbose_name_plural = "registros de auditoría"
        default_permissions = ("view",)

    def __str__(self):
        return f"{self.fecha:%d/%m/%Y %H:%M} · {self.usuario_nombre} · {self.get_accion_display()}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionDenied("Los registros de auditoría no se pueden modificar.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("Los registros de auditoría no se pueden eliminar.")
