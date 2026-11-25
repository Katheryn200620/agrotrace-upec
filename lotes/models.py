from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models
from django.urls import reverse
from django.utils import timezone

from agrotrace.gs1 import digital_link
from cuentas.models import RegistroResponsable


class Lote(RegistroResponsable):
    ESTADOS = [("almacenamiento", "En almacenamiento"), ("proceso", "En proceso"), ("transporte", "En transporte"),
               ("entregado", "Entregado"), ("agotado", "Agotado"), ("retirado", "Retirado del mercado")]
    CATEGORIAS = [("extra", "Extra"), ("primera", "Primera"), ("segunda", "Segunda")]
    codigo = models.CharField("Código del lote", max_length=20, unique=True, blank=True)
    producto = models.ForeignKey("productos.Producto", on_delete=models.PROTECT, related_name="lotes",
                                 verbose_name="Producto hortofrutícola")
    cosechas = models.ManyToManyField("cosechas.Cosecha", related_name="lotes", blank=True,
                                      verbose_name="Cosechas de origen")
    categoria = models.CharField("Categoría de calidad", max_length=10, choices=CATEGORIAS, default="primera")
    fecha_creacion = models.DateField("Fecha de creación", default=timezone.localdate)
    fecha_vencimiento = models.DateField(null=True, blank=True)
    cantidad_inicial = models.DecimalField(max_digits=10, decimal_places=2)
    cantidad_disponible = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    ubicacion = models.CharField("Ubicación en planta", max_length=80, default="Cámara de poscosecha")
    proceso = models.CharField("Proceso aplicado", max_length=150, blank=True,
                               help_text="Lavado, selección, despulpado, envasado…")
    estado = models.CharField(max_length=15, choices=ESTADOS, default="almacenamiento")
    publicado = models.BooleanField("Publicar ficha en el QR", default=True)
    odoo_id = models.IntegerField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-fecha_creacion", "-id"]
        verbose_name = "lote"
        verbose_name_plural = "lotes"
        constraints = [
            models.CheckConstraint(condition=models.Q(cantidad_inicial__gt=0), name="lote_cantidad_inicial_positiva"),
            models.CheckConstraint(condition=models.Q(cantidad_disponible__gte=0), name="lote_disponible_no_negativo"),
        ]

    def __str__(self):
        return f"{self.codigo} · {self.producto.nombre}" if self.codigo else "Lote nuevo"

    def save(self, *args, **kwargs):
        if not self.codigo:
            n = Lote.objects.filter(fecha_creacion=self.fecha_creacion).count() + 1
            self.codigo = f"H{self.fecha_creacion:%y%m%d}{n:02d}"
            while Lote.objects.filter(codigo=self.codigo).exists():
                n += 1
                self.codigo = f"H{self.fecha_creacion:%y%m%d}{n:02d}"
        if self.cantidad_disponible is None:
            self.cantidad_disponible = self.cantidad_inicial
        if not self.fecha_vencimiento and self.producto_id:
            self.fecha_vencimiento = self.fecha_creacion + timedelta(days=self.producto.vida_util_dias)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("lotes:lote_detalle", args=[self.pk])

    @property
    def unidad(self):
        return self.producto.unidad

    @property
    def link_gs1(self):
        return digital_link(self.producto.gtin, self.codigo)

    # ---- Procedencia (incluye los lotes de los que proviene si fue dividido, combinado o transformado) ----
    def lotes_origen(self, _visitados=None):
        visitados = _visitados or set()
        res = []
        for rel in self.origenes.select_related("origen"):
            if rel.origen_id not in visitados:
                visitados.add(rel.origen_id)
                res.append(rel.origen)
                res.extend(rel.origen.lotes_origen(visitados))
        return res

    def todas_las_cosechas(self):
        from cosechas.models import Cosecha
        ids = set(self.cosechas.values_list("id", flat=True))
        for l in self.lotes_origen():
            ids |= set(l.cosechas.values_list("id", flat=True))
        return Cosecha.objects.filter(id__in=ids).select_related("parcela", "productor")

    def parcelas(self):
        from parcelas.models import Parcela
        return Parcela.objects.filter(cosechas__in=self.todas_las_cosechas()).distinct()

    def productores(self):
        from productores.models import Productor
        return Productor.objects.filter(cosechas__in=self.todas_las_cosechas()).distinct()

    # ---- Completitud de eventos (análisis 3.5.6 y experimento E1) ----
    PASOS_ESPERADOS = [("cosecha", "Cosecha"), ("recepcion", "Recepción"), ("clasificacion", "Clasificación"),
                       ("creacion_lote", "Creación del lote"), ("despacho", "Despacho o venta")]

    def control_eventos(self):
        from trazabilidad.models import EventoTrazabilidad
        lotes = [self] + self.lotes_origen()
        tipos = set(EventoTrazabilidad.objects.filter(cosecha__in=self.todas_las_cosechas()).values_list("tipo", flat=True))
        tipos |= set(EventoTrazabilidad.objects.filter(lote__in=lotes).values_list("tipo", flat=True))
        if tipos & {"division", "combinacion", "transformacion"}:
            tipos.add("creacion_lote")
        if "venta" in tipos:
            tipos.add("despacho")
        return [(c, n, c in tipos) for c, n in self.PASOS_ESPERADOS]

    @property
    def completitud(self):
        control = self.control_eventos()
        return round(100 * sum(1 for *_, ok in control if ok) / len(control))

    @property
    def por_vencer(self):
        return self.fecha_vencimiento and self.fecha_vencimiento <= timezone.localdate() + timedelta(days=2)


class RelacionLote(models.Model):
    """Conserva la procedencia cuando un lote se divide, se combina o se transforma. No se edita ni se borra."""
    TIPOS = [("division", "División"), ("combinacion", "Combinación"), ("transformacion", "Transformación")]
    origen = models.ForeignKey(Lote, on_delete=models.PROTECT, related_name="derivados")
    resultado = models.ForeignKey(Lote, on_delete=models.PROTECT, related_name="origenes")
    tipo = models.CharField(max_length=15, choices=TIPOS)
    cantidad = models.DecimalField("Cantidad tomada del lote de origen", max_digits=10, decimal_places=2)
    fecha = models.DateTimeField(default=timezone.now)
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    observaciones = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "relación entre lotes"
        verbose_name_plural = "relaciones entre lotes"

    def __str__(self):
        return f"{self.get_tipo_display()}: {self.origen.codigo} → {self.resultado.codigo}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionDenied("Las relaciones de procedencia no se modifican.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("Las relaciones de procedencia no se eliminan.")
