import re
from datetime import timedelta

from django import forms
from django.utils import timezone

from cuentas.mixins import FECHA_HORA, FormularioBase
from lotes.models import Lote

from .models import Despacho, Transportista


class TransportistaForm(FormularioBase):
    class Meta:
        model = Transportista
        fields = ["nombre", "identificacion", "telefono", "vehiculo_placa", "tipo_vehiculo", "refrigerado", "activo"]

    def clean_vehiculo_placa(self):
        v = self.cleaned_data.get("vehiculo_placa", "").strip().upper()
        if v and not re.fullmatch(r"[A-Z]{3}-?\d{3,4}", v):
            self.add_error("vehiculo_placa", "Formato de placa ecuatoriana: ABC-1234.")
        return v


class DespachoForm(FormularioBase):
    class Meta:
        model = Despacho
        fields = ["venta", "lote", "cantidad", "transportista", "vehiculo", "salida", "origen", "tipo_destino", "destino",
                  "observaciones"]
        widgets = {"salida": FECHA_HORA}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from comercial.models import Venta
        self.fields["venta"].queryset = Venta.objects.filter(estado__in=["pendiente", "parcial"]).select_related("cliente", "lote")
        self.fields["venta"].label_from_instance = lambda v: f"{v.codigo} · {v.cliente.nombre} · {v.por_despachar} {v.unidad} de {v.lote.codigo}"
        self.fields["venta"].empty_label = "— Sin venta (traslado o envío al CEDI) —"
        self.fields["lote"].queryset = Lote.objects.filter(cantidad_disponible__gt=0).exclude(
            estado__in=["retirado", "agotado", "entregado"]).select_related("producto")
        self.fields["lote"].required = False
        self.fields["transportista"].queryset = Transportista.objects.filter(activo=True)
        self.fields["lote"].help_text = "Solo aparecen lotes con cantidad disponible. Si eligió una venta, se usa su lote."

    def clean(self):
        from comercial.servicios import reservado
        d = super().clean()
        venta = d.get("venta")
        if venta:
            d["lote"] = venta.lote
            if not d.get("destino"):
                d["destino"] = f"{venta.cliente.nombre} – {venta.cliente.ciudad}"
                self.errors.pop("destino", None)
        lote, c, sal = d.get("lote"), d.get("cantidad"), d.get("salida")
        if not lote:
            self.add_error("lote", "Elija el lote o una venta.")
        if c is not None and c <= 0:
            self.add_error("cantidad", "Debe ser mayor que 0.")
        if venta and c and c > venta.por_despachar:
            self.add_error("cantidad", f"La venta {venta.codigo} tiene {venta.por_despachar} {venta.unidad} por despachar.")
        if lote and c and c > lote.cantidad_disponible:
            self.add_error("cantidad", f"Solo hay {lote.cantidad_disponible} {lote.unidad} disponibles en el lote {lote.codigo}.")
        elif lote and c and not venta and c > lote.cantidad_disponible - reservado(lote):
            self.add_error("cantidad", f"Del lote {lote.codigo} hay {reservado(lote)} {lote.unidad} reservados para ventas. "
                                       "Elija la venta o despache menos.")
        if lote and sal and timezone.localtime(sal).date() < lote.fecha_creacion:
            self.add_error("salida", "La salida no puede ser anterior a la creación del lote.")
        t = d.get("transportista")
        if t and not d.get("vehiculo"):
            d["vehiculo"] = t.vehiculo_placa
        return d


class DespachoEditarForm(FormularioBase):
    """Después de crearlo no se cambian el lote ni la cantidad (ya se descontaron del lote)."""
    class Meta:
        model = Despacho
        fields = ["transportista", "vehiculo", "destino", "observaciones"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["transportista"].queryset = Transportista.objects.filter(activo=True)
        if self.instance.estado != "programado":
            for c in ("transportista", "vehiculo", "destino"):
                self.fields[c].disabled = True


class EntregaForm(forms.Form):
    llegada = forms.DateTimeField(label="Fecha y hora de recepción", widget=forms.DateTimeInput(
        attrs={"class": "form-control", "type": "datetime-local"}))
    entregado_a_tiempo = forms.TypedChoiceField(label="¿Llegó a tiempo?", choices=[("1", "Sí"), ("0", "No")],
                                                coerce=lambda v: v == "1", widget=forms.Select(attrs={"class": "form-select"}))
    km_recorridos = forms.DecimalField(label="Km recorridos", required=False, min_value=0,
                                       widget=forms.NumberInput(attrs={"class": "form-control"}))

    def __init__(self, *args, despacho=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.despacho = despacho

    def clean_llegada(self):
        v = self.cleaned_data["llegada"]
        if v > timezone.now() + timedelta(minutes=5):
            raise forms.ValidationError("No puede estar en el futuro.")
        if self.despacho and v < self.despacho.salida:
            raise forms.ValidationError("La llegada no puede ser anterior a la salida.")
        return v
