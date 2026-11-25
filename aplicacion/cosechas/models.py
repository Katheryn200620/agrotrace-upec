from decimal import Decimal

from django.db import models
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from cuentas.models import RegistroResponsable


class Cosecha(RegistroResponsable):
    codigo = models.CharField("Código de cosecha", max_length=40, unique=True, blank=True)
    parcela = models.ForeignKey("parcelas.Parcela", on_delete=models.PROTECT, related_name="cosechas",
                                verbose_name="Parcela de origen")
    productor = models.ForeignKey("productores.Productor", on_delete=models.PROTECT, related_name="cosechas")
    producto = models.ForeignKey("productos.Producto", on_delete=models.PROTECT, related_name="cosechas",
                                 verbose_name="Producto cosechado")
    fecha = models.DateField("Fecha de cosecha", default=timezone.localdate)
    cantidad = models.DecimalField("Cantidad recolectada", max_digits=10, decimal_places=2)
    UNIDADES = [("kg", "Kilogramos (kg)"), ("und", "Unidades"), ("caja", "Cajas"), ("saco", "Sacos")]
    unidad = models.CharField("Unidad de medida", max_length=5, choices=UNIDADES, default="kg")
    observaciones = models.TextField(blank=True)

    class Meta:
        ordering = ["-fecha", "-id"]
        verbose_name = "cosecha"
        verbose_name_plural = "cosechas"
        constraints = [models.CheckConstraint(condition=models.Q(cantidad__gt=0), name="cosecha_cantidad_positiva")]

    def __str__(self):
        return self.codigo or "Cosecha nueva"

    def save(self, *args, **kwargs):
        if not self.codigo:
            n = Cosecha.objects.filter(parcela=self.parcela, fecha=self.fecha).count() + 1
            self.codigo = f"C-{self.parcela.codigo}-{self.fecha:%Y%m%d}-{n}"
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("cosechas:cosecha_detalle", args=[self.pk])

    @property
    def recibida(self):
        return hasattr(self, "recepcion")

    @property
    def kg_aprovechables(self):
        """Lo recibido menos lo rechazado: lo que puede pasar a lotes."""
        if not self.recibida:
            return Decimal("0")
        return self.recepcion.peso_recibido - self.recepcion.kg_rechazo


class Recepcion(RegistroResponsable):
    cosecha = models.OneToOneField(Cosecha, on_delete=models.PROTECT, related_name="recepcion")
    fecha_hora = models.DateTimeField("Fecha y hora de recepción", default=timezone.now)
    peso_recibido = models.DecimalField("Peso recibido (kg)", max_digits=10, decimal_places=2)
    temperatura = models.DecimalField("Temperatura (°C)", max_digits=4, decimal_places=1, null=True, blank=True)
    minutos_recepcion = models.PositiveIntegerField("Tiempo de recepción (min)", null=True, blank=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        ordering = ["-fecha_hora"]
        verbose_name = "recepción en planta"
        verbose_name_plural = "recepciones en planta"

    def __str__(self):
        return f"Recepción de {self.cosecha.codigo}"

    def get_absolute_url(self):
        return reverse("cosechas:recepcion_detalle", args=[self.pk])

    @property
    def kg_clasificados(self):
        return self.clasificaciones.aggregate(t=Sum("cantidad"))["t"] or Decimal("0")

    @property
    def kg_rechazo(self):
        return self.clasificaciones.filter(categoria="rechazo").aggregate(t=Sum("cantidad"))["t"] or Decimal("0")

    @property
    def porcentaje_rechazo(self):
        return round(self.kg_rechazo * 100 / self.peso_recibido, 1) if self.peso_recibido else Decimal("0")


class Clasificacion(RegistroResponsable):
    CATEGORIAS = [("extra", "Extra"), ("primera", "Primera"), ("segunda", "Segunda"), ("rechazo", "Rechazo")]
    METODOS = [("visual", "Visual (operador)"), ("modelo", "Modelo de visión artificial")]
    recepcion = models.ForeignKey(Recepcion, on_delete=models.CASCADE, related_name="clasificaciones")
    categoria = models.CharField("Categoría", max_length=10, choices=CATEGORIAS)
    cantidad = models.DecimalField("Cantidad (kg)", max_digits=10, decimal_places=2)
    metodo = models.CharField("Método", max_length=10, choices=METODOS, default="visual")
    confianza_modelo = models.DecimalField("Confianza del modelo", max_digits=4, decimal_places=2, null=True, blank=True,
                                           help_text="De 0 a 1, solo si clasificó el modelo")
    foto = models.ImageField(upload_to="clasificacion/", null=True, blank=True,
                             help_text="Sirve para el dataset de visión artificial")
    causa_rechazo = models.CharField("Causa del rechazo", max_length=100, blank=True,
                                     help_text="Golpe, pudrición, plaga, calibre…")

    class Meta:
        ordering = ["-id"]
        verbose_name = "clasificación de calidad"
        verbose_name_plural = "clasificaciones de calidad"

    def __str__(self):
        return f"{self.get_categoria_display()} · {self.cantidad} kg · {self.recepcion.cosecha.codigo}"

    def get_absolute_url(self):
        return reverse("cosechas:clasificacion_detalle", args=[self.pk])
