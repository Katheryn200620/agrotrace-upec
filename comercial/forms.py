import re

from django import forms

from cuentas.mixins import FECHA, FormularioBase
from lotes.models import Lote

from .models import Cliente, Venta
from .servicios import disponible_para_vender


class ClienteForm(FormularioBase):
    class Meta:
        model = Cliente
        fields = ["codigo", "nombre", "tipo", "identificacion", "ciudad", "direccion", "telefono", "correo", "activo"]

    def clean_identificacion(self):
        v = self.cleaned_data.get("identificacion", "").strip()
        if v and not re.fullmatch(r"\d{10}|\d{13}", v):
            self.add_error("identificacion", "La cédula tiene 10 dígitos y el RUC 13.")
        if v and Cliente.objects.filter(identificacion=v).exclude(pk=self.instance.pk).exists():
            self.add_error("identificacion", "Ya existe un cliente con esa cédula o RUC.")
        return v

    def clean_telefono(self):
        v = self.cleaned_data.get("telefono", "").strip()
        if v and not re.fullmatch(r"[0-9+ ]{7,15}", v):
            self.add_error("telefono", "Escriba solo números (7 a 15 dígitos).")
        return v


class VentaForm(FormularioBase):
    class Meta:
        model = Venta
        fields = ["cliente", "lote", "fecha", "cantidad", "precio_unitario", "canal", "referencia", "observaciones"]
        widgets = {"fecha": FECHA}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cliente"].queryset = Cliente.objects.filter(activo=True)
        self.fields["lote"].queryset = Lote.objects.filter(cantidad_disponible__gt=0, publicado=True).exclude(
            estado__in=["retirado", "agotado", "entregado"]).select_related("producto")
        self.fields["lote"].label_from_instance = lambda l: f"{l.codigo} · {l.producto} · {l.cantidad_disponible} {l.unidad} en planta"
        self.fields["lote"].help_text = "Solo lotes con existencias y sin retiro."
        self.fields["precio_unitario"].required = False
        self.fields["precio_unitario"].help_text = "Si lo deja vacío se usa el precio referencial del producto."

    def clean(self):
        d = super().clean()
        lote, c, f = d.get("lote"), d.get("cantidad"), d.get("fecha")
        if c is not None and c <= 0:
            self.add_error("cantidad", "Debe ser mayor que 0.")
        if lote and c:
            libre = disponible_para_vender(lote, self.instance)
            if c > libre:
                self.add_error("cantidad", f"Del lote {lote.codigo} quedan {libre} {lote.unidad} sin comprometer en otras ventas.")
        if lote and f and f < lote.fecha_creacion:
            self.add_error("fecha", "La venta no puede ser anterior a la creación del lote.")
        if lote and d.get("precio_unitario") in (None, ""):
            d["precio_unitario"] = lote.producto.precio
        return d


class VentaEditarForm(FormularioBase):
    """Una venta registrada no cambia de lote ni de cantidad (queda en el historial)."""
    class Meta:
        model = Venta
        fields = ["cliente", "precio_unitario", "canal", "referencia", "observaciones"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cliente"].queryset = Cliente.objects.filter(activo=True)
