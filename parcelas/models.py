from django.db import models
from django.urls import reverse
from django.utils import timezone

from agrotrace.gs1 import generar_gln
from cuentas.models import RegistroResponsable


class Parcela(RegistroResponsable):
    UNIDADES = [("ha", "Hectáreas"), ("m2", "Metros cuadrados")]
    ESTADOS = [("preparacion", "En preparación"), ("sembrado", "Sembrado"), ("desarrollo", "En desarrollo"),
               ("cosecha", "En cosecha"), ("cosechado", "Cosechado"), ("descanso", "En descanso")]
    codigo = models.CharField("Código de parcela", max_length=20, unique=True)
    nombre = models.CharField("Nombre de la parcela", max_length=100)
    productor = models.ForeignKey("productores.Productor", on_delete=models.PROTECT, related_name="parcelas")
    cultivo = models.ForeignKey("productos.Producto", on_delete=models.PROTECT, related_name="parcelas",
                                verbose_name="Tipo de cultivo", limit_choices_to={"estado": "activo"})
    variedad = models.CharField(max_length=60, blank=True)
    latitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    altitud_msnm = models.PositiveIntegerField("Altitud (m s. n. m.)", null=True, blank=True)
    superficie = models.DecimalField(max_digits=10, decimal_places=2)
    unidad_superficie = models.CharField("Unidad", max_length=3, choices=UNIDADES, default="ha")
    fecha_siembra = models.DateField("Fecha de siembra", null=True, blank=True)
    estado_cultivo = models.CharField("Estado del cultivo", max_length=12, choices=ESTADOS, default="sembrado")
    gln = models.CharField("GLN", max_length=13, blank=True, editable=False)

    class Meta:
        ordering = ["codigo"]
        verbose_name = "parcela"
        verbose_name_plural = "parcelas"

    def __str__(self):
        return f"{self.codigo} · {self.nombre}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.gln:
            self.gln = generar_gln(self.pk)
            super().save(update_fields=["gln"])

    def get_absolute_url(self):
        return reverse("parcelas:parcela_detalle", args=[self.pk])


class Labor(RegistroResponsable):
    TIPOS = [("siembra", "Siembra"), ("riego", "Riego"), ("fertilizacion", "Fertilización"),
             ("fitosanitario", "Control fitosanitario"), ("deshierbe", "Deshierbe"), ("poda", "Poda o tutorado"),
             ("otro", "Otra labor")]
    parcela = models.ForeignKey(Parcela, on_delete=models.CASCADE, related_name="labores")
    tipo = models.CharField("Labor", max_length=15, choices=TIPOS)
    fecha = models.DateField(default=timezone.localdate)
    insumo = models.CharField(max_length=100, blank=True)
    dosis = models.CharField(max_length=50, blank=True)
    descripcion = models.TextField("Observaciones", blank=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "labor agrícola"
        verbose_name_plural = "labores agrícolas"

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.parcela.codigo} · {self.fecha:%d/%m/%Y}"

    def get_absolute_url(self):
        return reverse("parcelas:labor_detalle", args=[self.pk])
