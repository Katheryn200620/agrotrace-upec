from django.db import models
from django.urls import reverse
from django.utils import timezone

from cuentas.models import RegistroResponsable


class Transportista(RegistroResponsable):
    nombre = models.CharField("Nombre o empresa", max_length=120)
    identificacion = models.CharField("Cédula o RUC", max_length=13, blank=True)
    telefono = models.CharField("Teléfono", max_length=20, blank=True)
    vehiculo_placa = models.CharField("Placa del vehículo", max_length=10, blank=True)
    tipo_vehiculo = models.CharField(max_length=50, blank=True, help_text="Camioneta, camión, furgón…")
    refrigerado = models.BooleanField("Vehículo refrigerado", default=False)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "transportista"
        verbose_name_plural = "transportistas"

    def __str__(self):
        return f"{self.nombre}{' · ' + self.vehiculo_placa if self.vehiculo_placa else ''}"

    def get_absolute_url(self):
        return reverse("transporte:transportista_detalle", args=[self.pk])


class Despacho(RegistroResponsable):
    ESTADOS = [("programado", "Programado"), ("transito", "En tránsito"), ("entregado", "Entregado"),
               ("cancelado", "Cancelado")]
    DESTINOS = [("cliente", "Cliente directo"), ("cedi", "Centro de distribución (CEDI)"), ("tienda", "Tienda en línea")]
    codigo = models.CharField("Código de despacho", max_length=25, unique=True, blank=True)
    lote = models.ForeignKey("lotes.Lote", on_delete=models.PROTECT, related_name="despachos",
                             verbose_name="Lote transportado")
    venta = models.ForeignKey("comercial.Venta", on_delete=models.PROTECT, null=True, blank=True, related_name="despachos",
                              verbose_name="Venta que se despacha", help_text="Opcional: si el despacho atiende una venta registrada")
    cantidad = models.DecimalField("Cantidad despachada", max_digits=10, decimal_places=2)
    transportista = models.ForeignKey(Transportista, on_delete=models.PROTECT, null=True, blank=True,
                                      related_name="despachos")
    vehiculo = models.CharField("Vehículo (placa)", max_length=10, blank=True)
    salida = models.DateTimeField("Fecha y hora de salida", default=timezone.now)
    origen = models.CharField("Lugar de origen", max_length=120, default="Planta Hortofrutícola UPEC, Tulcán")
    tipo_destino = models.CharField("Tipo de destino", max_length=10, choices=DESTINOS, default="cliente")
    destino = models.CharField(max_length=150, help_text="Cliente, ciudad o dirección de entrega")
    llegada = models.DateTimeField("Fecha y hora de recepción", null=True, blank=True)
    estado = models.CharField("Estado del transporte", max_length=10, choices=ESTADOS, default="programado")
    entregado_a_tiempo = models.BooleanField(null=True, blank=True)
    km_recorridos = models.DecimalField("Km recorridos", max_digits=7, decimal_places=1, null=True, blank=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        ordering = ["-salida"]
        verbose_name = "despacho"
        verbose_name_plural = "despachos"
        constraints = [models.CheckConstraint(condition=models.Q(cantidad__gt=0), name="despacho_cantidad_positiva")]

    def __str__(self):
        return self.codigo or "Despacho nuevo"

    def save(self, *args, **kwargs):
        if not self.codigo:
            fecha = timezone.localtime(self.salida)
            n = Despacho.objects.filter(salida__date=fecha.date()).count() + 1
            self.codigo = f"D-{fecha:%Y%m%d}-{n:02d}"
            while Despacho.objects.filter(codigo=self.codigo).exists():
                n += 1
                self.codigo = f"D-{fecha:%Y%m%d}-{n:02d}"
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("transporte:despacho_detalle", args=[self.pk])
