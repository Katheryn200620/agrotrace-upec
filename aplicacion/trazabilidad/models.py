"""
Historial de trazabilidad tipo EPCIS 2.0 (qué, cuándo, dónde, por qué, cómo).
Los eventos NO se modifican ni se borran: una corrección es un evento nuevo que apunta al anterior.
"""
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models
from django.urls import reverse
from django.utils import timezone


class EventoTrazabilidad(models.Model):
    TIPOS = [
        ("cultivo", "Labor de cultivo"), ("cosecha", "Registro de cosecha"), ("recepcion", "Recepción en planta"),
        ("clasificacion", "Clasificación de calidad"), ("creacion_lote", "Creación del lote"),
        ("empaque", "Empaque"), ("almacenamiento", "Almacenamiento"), ("transformacion", "Transformación"),
        ("division", "División de lote"), ("combinacion", "Combinación de lotes"),
        ("despacho", "Despacho"), ("venta", "Venta registrada"), ("transporte", "Transporte"), ("recepcion_destino", "Recepción en destino"),
        ("retiro", "Retiro del mercado"), ("correccion", "Corrección de registro"),
    ]
    # Tipos que el operador de trazabilidad registra a mano (los demás los crea el sistema)
    TIPOS_MANUALES = ["empaque", "almacenamiento", "transformacion", "transporte", "recepcion_destino"]
    # Paso de negocio del vocabulario CBV de GS1
    BIZSTEP = {
        "cultivo": "cultivating", "cosecha": "harvesting", "recepcion": "receiving", "clasificacion": "inspecting",
        "creacion_lote": "commissioning", "empaque": "packing", "almacenamiento": "storing",
        "transformacion": "transforming", "division": "transforming", "combinacion": "transforming",
        "despacho": "shipping", "venta": "retail_selling", "transporte": "departing", "recepcion_destino": "arriving",
        "retiro": "holding", "correccion": "inspecting",
    }
    tipo = models.CharField("Tipo de evento", max_length=20, choices=TIPOS)
    tipo_epcis = models.CharField(max_length=25, default="ObjectEvent")
    lote = models.ForeignKey("lotes.Lote", on_delete=models.PROTECT, null=True, blank=True, related_name="eventos")
    cosecha = models.ForeignKey("cosechas.Cosecha", on_delete=models.PROTECT, null=True, blank=True, related_name="eventos")
    parcela = models.ForeignKey("parcelas.Parcela", on_delete=models.PROTECT, null=True, blank=True, related_name="eventos")
    fecha_hora = models.DateTimeField("Fecha y hora", default=timezone.now)
    lugar = models.CharField(max_length=150)
    cantidad = models.DecimalField("Cantidad involucrada", max_digits=10, decimal_places=2, null=True, blank=True)
    unidad = models.CharField(max_length=5, blank=True)
    descripcion = models.CharField("Qué ocurrió", max_length=250)
    observaciones = models.TextField(blank=True)
    disposicion = models.CharField(max_length=30, blank=True)
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    origen = models.CharField(max_length=15, default="sistema",
                              choices=[("sistema", "Automático"), ("manual", "Registro manual"),
                                       ("sensor", "Sensor"), ("odoo", "Odoo")])
    corrige = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="correcciones",
                                verbose_name="Evento que corrige")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["fecha_hora", "id"]
        verbose_name = "evento de trazabilidad"
        verbose_name_plural = "eventos de trazabilidad"

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.fecha_hora:%d/%m/%Y %H:%M}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionDenied("El historial de trazabilidad no se modifica: registre una corrección.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("El historial de trazabilidad no se elimina.")

    def get_absolute_url(self):
        return reverse("trazabilidad:evento_detalle", args=[self.pk])

    @property
    def biz_step(self):
        return self.BIZSTEP.get(self.tipo, "")

    @property
    def area_responsable(self):
        p = getattr(self.responsable, "perfil", None)
        if p and p.area:
            return p.area.nombre
        return "Administración UPEC"

    @property
    def corregido(self):
        return self.correcciones.exists()

    def como_epcis(self):
        epc = [f"https://id.gs1.org/01/{self.lote.producto.gtin}/10/{self.lote.codigo}"] if self.lote else []
        return {
            "type": self.tipo_epcis, "eventTime": self.fecha_hora.isoformat(), "eventTimeZoneOffset": "-05:00",
            "epcList": epc, "action": "ADD" if self.tipo == "creacion_lote" else "OBSERVE",
            "bizStep": self.biz_step, "disposition": self.disposicion or "active",
            "readPoint": {"id": self.lugar}, "quantity": float(self.cantidad) if self.cantidad is not None else None,
            "what": self.descripcion,
        }


class EscaneoQR(models.Model):
    lote = models.ForeignKey("lotes.Lote", on_delete=models.CASCADE, related_name="escaneos")
    fecha_hora = models.DateTimeField(auto_now_add=True)
    agente_usuario = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-fecha_hora"]
        verbose_name = "escaneo de QR"
        verbose_name_plural = "escaneos de QR"


class SimulacroRetiro(models.Model):
    """Experimento E1: tiempo y completitud del rastreo parcela → cliente."""
    METODOS = [("actual", "Práctica actual (papel o memoria)"), ("aplicativo", "Aplicativo AgroTrace-UPEC")]
    lote = models.ForeignKey("lotes.Lote", on_delete=models.PROTECT, related_name="simulacros")
    metodo = models.CharField("Método", max_length=10, choices=METODOS)
    fecha = models.DateTimeField(default=timezone.now)
    minutos = models.DecimalField("Tiempo de rastreo (min)", max_digits=6, decimal_places=2)
    completitud_pct = models.PositiveIntegerField("Eventos completos (%)")
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    observaciones = models.TextField(blank=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "simulacro de retiro"
        verbose_name_plural = "simulacros de retiro"

    def __str__(self):
        return f"Simulacro {self.get_metodo_display()} · {self.lote.codigo}"
