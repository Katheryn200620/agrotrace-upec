from cuentas.mixins import FormularioBase

from .models import Producto


class ProductoForm(FormularioBase):
    class Meta:
        model = Producto
        fields = ["codigo", "nombre", "categoria", "variedad", "unidad", "descripcion", "vida_util_dias",
                  "precio", "stock_minimo", "gtin", "estado", "foto"]

    def clean_foto(self):
        f = self.cleaned_data.get("foto")
        if f and hasattr(f, "size") and f.size > 5 * 1024 * 1024:
            self.add_error("foto", "La fotografía no debe pasar de 5 MB.")
        return f

    def clean_gtin(self):
        v = self.cleaned_data.get("gtin", "").strip()
        if v:
            from agrotrace.gs1 import digito_control
            if not (v.isdigit() and len(v) == 14 and digito_control(v[:13]) == v[13]):
                self.add_error("gtin", "El GTIN debe tener 14 dígitos y un dígito de control válido. Déjelo vacío para generarlo.")
        return v

    def clean_precio(self):
        v = self.cleaned_data.get("precio")
        if v is not None and v < 0:
            self.add_error("precio", "El precio no puede ser negativo.")
        return v
