import re

from cuentas.mixins import FormularioBase

from .models import Productor


class ProductorForm(FormularioBase):
    class Meta:
        model = Productor
        fields = ["codigo", "nombre", "tipo", "identificacion", "provincia", "canton", "parroquia",
                  "telefono", "correo", "estado", "mostrar_nombre_publico"]

    def clean_identificacion(self):
        v = self.cleaned_data.get("identificacion", "").strip()
        if v and not re.fullmatch(r"\d{10}|\d{13}", v):
            self.add_error("identificacion", "La cédula tiene 10 dígitos y el RUC 13.")
        return v

    def clean_telefono(self):
        v = self.cleaned_data.get("telefono", "").strip()
        if v and not re.fullmatch(r"[0-9+ ]{7,15}", v):
            self.add_error("telefono", "Escriba solo números (7 a 15 dígitos).")
        return v
