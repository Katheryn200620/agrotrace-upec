"""
Clientes y ventas (Área 8: Clientes y comercialización).

Una venta compromete (reserva) una cantidad de un lote. El inventario se descuenta cuando
el área de transporte despacha esa venta, así no se descuenta dos veces.
"""
from decimal import Decimal

from django.db import models
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from cuentas.models import RegistroResponsable


class Cliente(RegistroResponsable):
    TIPOS = [("mayorista", "Mayorista"), ("minorista", "Minorista"), ("comercio", "Comercio o restaurante"),
             ("institucion", "Institución"), ("consumidor", "Consumidor final"), ("tienda", "Tienda en línea")]
    codigo = models.CharField("Código del cliente", max_length=20, unique=True, blank=True,
                              help_text="Se genera solo si se deja vacío (CL-001)")
    nombre = models.CharField("Nombre o razón social", max_length=150)
    tipo = models.CharField("Tipo de cliente", max_length=12, choices=TIPOS, default="minorista")
    identificacion = models.CharField("Cédula o RUC", max_length=13, blank=True)
    ciudad = models.CharField(max_length=60, default="Tulcán")
    direccion = models.CharField("Dirección de entrega", max_length=150, blank=True)
    telefono = models.CharField("Teléfono", max_length=20, blank=True)
    correo = models.EmailField(blank=True)
    activo = models.BooleanField(default=True)
    odoo_id = models.IntegerField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "cliente"
        verbose_name_plural = "clientes"

    def __str__(self):
        return f"{self.codigo} · {self.nombre}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.codigo:
            self.codigo = f"CL-{self.pk:03d}"
            super().save(update_fields=["codigo"])

    def get_absolute_url(self):
        return reverse("comercial:cliente_detalle", args=[self.pk])


class Venta(RegistroResponsable):
    CANALES = [("directa", "Venta directa en planta"), ("mayorista", "Mayorista o distribuidor"),
               ("tienda", "Tienda en línea"), ("pedido", "Pedido por teléfono o mensaje")]
    ESTADOS = [("pendiente", "Pendiente de despacho"), ("parcial", "Despachada en parte"),
               ("despachada", "Despachada"), ("entregada", "Entregada"), ("anulada", "Anulada")]
    codigo = models.CharField("Código de venta", max_length=20, unique=True, blank=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="ventas")
    lote = models.ForeignKey("lotes.Lote", on_delete=models.PROTECT, related_name="ventas", verbose_name="Lote vendido")
    fecha = models.DateField("Fecha de la venta", default=timezone.localdate)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    precio_unitario = models.DecimalField("Precio unitario ($)", max_digits=8, decimal_places=2)
    canal = models.CharField(max_length=10, choices=CANALES, default="directa")
    referencia = models.CharField("Factura o referencia", max_length=40, blank=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default="pendiente")
    observaciones = models.TextField(blank=True)
    odoo_id = models.IntegerField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-fecha", "-id"]
        verbose_name = "venta"
        verbose_name_plural = "ventas"
        constraints = [models.CheckConstraint(condition=models.Q(cantidad__gt=0), name="venta_cantidad_positiva"),
                       models.CheckConstraint(condition=models.Q(precio_unitario__gte=0), name="venta_precio_no_negativo")]

    def __str__(self):
        return self.codigo or "Venta nueva"

    def save(self, *args, **kwargs):
        if not self.codigo:
            n = Venta.objects.filter(fecha=self.fecha).count() + 1
            self.codigo = f"V-{self.fecha:%Y%m%d}-{n:02d}"
            while Venta.objects.filter(codigo=self.codigo).exists():
                n += 1
                self.codigo = f"V-{self.fecha:%Y%m%d}-{n:02d}"
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("comercial:venta_detalle", args=[self.pk])

    @property
    def unidad(self):
        return self.lote.producto.unidad

    @property
    def total(self):
        return (self.cantidad * self.precio_unitario).quantize(Decimal("0.01"))

    @property
    def despachado(self):
        return self.despachos.exclude(estado="cancelado").aggregate(t=Sum("cantidad"))["t"] or Decimal("0")

    @property
    def por_despachar(self):
        return max(self.cantidad - self.despachado, Decimal("0")) if self.estado != "anulada" else Decimal("0")
