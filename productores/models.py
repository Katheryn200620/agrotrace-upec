from django.db import models
from django.urls import reverse

from cuentas.models import RegistroResponsable


class Productor(RegistroResponsable):
    TIPOS = [("centro", "Centro experimental"), ("persona", "Persona natural"), ("organizacion", "Asociación u organización")]
    ESTADOS = [("activo", "Activo"), ("inactivo", "Inactivo")]
    codigo = models.CharField("Código del productor", max_length=20, unique=True, blank=True,
                              help_text="Se genera solo si se deja vacío (PR-001)")
    nombre = models.CharField("Nombres y apellidos o razón social", max_length=150)
    tipo = models.CharField(max_length=15, choices=TIPOS, default="persona")
    identificacion = models.CharField("Cédula o RUC", max_length=13, blank=True)
    provincia = models.CharField(max_length=50, default="Carchi")
    canton = models.CharField("Cantón", max_length=50, default="Tulcán")
    parroquia = models.CharField(max_length=50, blank=True)
    telefono = models.CharField("Teléfono", max_length=20, blank=True)
    correo = models.EmailField(blank=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default="activo")
    mostrar_nombre_publico = models.BooleanField(
        "Autoriza mostrar su nombre en la consulta pública", default=False,
        help_text="Si no autoriza, el QR solo muestra el cantón y la parroquia.")

    class Meta:
        ordering = ["codigo"]
        verbose_name = "productor"
        verbose_name_plural = "productores"

    def __str__(self):
        return f"{self.codigo} · {self.nombre}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.codigo:
            self.codigo = f"PR-{self.pk:03d}"
            super().save(update_fields=["codigo"])

    def get_absolute_url(self):
        return reverse("productores:productor_detalle", args=[self.pk])

    @property
    def ubicacion(self):
        return ", ".join(x for x in [self.parroquia, self.canton, self.provincia] if x)

    @property
    def nombre_publico(self):
        if self.tipo == "centro" or self.mostrar_nombre_publico:
            return self.nombre
        return f"Productor de {self.ubicacion}"

    @property
    def datos_incompletos(self):
        return not (self.identificacion and self.parroquia and (self.telefono or self.correo))
