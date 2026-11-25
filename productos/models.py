from django.db import models
from django.urls import reverse

from agrotrace.gs1 import generar_gtin
from cuentas.models import RegistroResponsable


class Producto(RegistroResponsable):
    CATEGORIAS = [("fruta", "Fruta"), ("hortaliza", "Hortaliza"), ("tuberculo", "Tubérculo"),
                  ("grano", "Grano o leguminosa"), ("procesado", "Producto procesado")]
    UNIDADES = [("kg", "Kilogramos (kg)"), ("und", "Unidades"), ("caja", "Cajas"), ("saco", "Sacos")]
    ESTADOS = [("activo", "Activo"), ("inactivo", "Inactivo")]
    codigo = models.CharField("Código del producto", max_length=20, unique=True, blank=True)
    nombre = models.CharField(max_length=100)
    categoria = models.CharField("Tipo o categoría", max_length=12, choices=CATEGORIAS)
    variedad = models.CharField(max_length=60, blank=True)
    unidad = models.CharField("Unidad de medida", max_length=5, choices=UNIDADES, default="kg")
    descripcion = models.TextField("Descripción", blank=True)
    vida_util_dias = models.PositiveIntegerField("Vida útil (días)", default=7)
    precio = models.DecimalField("Precio referencial ($)", max_digits=8, decimal_places=2, default=0)
    stock_minimo = models.DecimalField("Stock mínimo", max_digits=10, decimal_places=2, default=0,
                                       help_text="Si las existencias bajan de este valor se muestra una alerta (0 = sin alerta)")
    gtin = models.CharField("GTIN-14", max_length=14, unique=True, blank=True, help_text="Se genera solo si se deja vacío")
    estado = models.CharField(max_length=10, choices=ESTADOS, default="activo")
    foto = models.ImageField("Fotografía", upload_to="productos/", null=True, blank=True,
                             help_text="Foto real del producto (JPG o PNG, máximo 5 MB). Se muestra en la página de Inicio.")
    odoo_id = models.IntegerField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "producto"
        verbose_name_plural = "productos"

    def __str__(self):
        return f"{self.nombre}{' ' + self.variedad if self.variedad else ''}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cambios = []
        if not self.codigo:
            self.codigo = f"PRD-{self.pk:03d}"; cambios.append("codigo")
        if not self.gtin:
            self.gtin = generar_gtin(self.pk); cambios.append("gtin")
        if cambios:
            super().save(update_fields=cambios)

    def get_absolute_url(self):
        return reverse("productos:producto_detalle", args=[self.pk])
