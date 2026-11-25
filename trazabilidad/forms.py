from datetime import timedelta
from decimal import Decimal

from django import forms
from django.utils import timezone

from cuentas.mixins import FECHA_HORA
from lotes.models import Lote

from .models import EventoTrazabilidad, SimulacroRetiro

C = {"class": "form-control"}
S = {"class": "form-select"}


class EventoForm(forms.Form):
    lote = forms.ModelChoiceField(queryset=Lote.objects.exclude(estado="retirado"), widget=forms.Select(attrs=S),
                                  empty_label="— Seleccione —")
    tipo = forms.ChoiceField(label="Tipo de evento",
                             choices=[("", "— Seleccione —")] + [t for t in EventoTrazabilidad.TIPOS if t[0] in EventoTrazabilidad.TIPOS_MANUALES],
                             widget=forms.Select(attrs=S))
    fecha_hora = forms.DateTimeField(label="Fecha y hora", widget=forms.DateTimeInput(attrs={**C, "type": "datetime-local"}),
                                     initial=lambda: timezone.localtime().strftime("%Y-%m-%dT%H:%M"))
    lugar = forms.CharField(max_length=150, initial="Planta Hortofrutícola UPEC, Tulcán", widget=forms.TextInput(attrs=C))
    cantidad = forms.DecimalField(label="Cantidad involucrada", required=False, min_value=Decimal("0.01"),
                                  widget=forms.NumberInput(attrs=C))
    descripcion = forms.CharField(label="Qué ocurrió", max_length=250, widget=forms.TextInput(attrs=C))
    observaciones = forms.CharField(required=False, widget=forms.Textarea(attrs={**C, "rows": 2}))

    def clean(self):
        d = super().clean()
        fh, lote, c = d.get("fecha_hora"), d.get("lote"), d.get("cantidad")
        if fh and fh > timezone.now() + timedelta(minutes=5):
            self.add_error("fecha_hora", "No puede registrar eventos en el futuro.")
        if fh and lote and timezone.localtime(fh).date() < lote.fecha_creacion:
            self.add_error("fecha_hora", "Es anterior a la creación del lote.")
        if c and lote and c > lote.cantidad_inicial:
            self.add_error("cantidad", f"Supera la cantidad del lote ({lote.cantidad_inicial} {lote.unidad}).")
        return d


class CorreccionForm(forms.Form):
    descripcion = forms.CharField(label="Dato correcto", max_length=250, widget=forms.TextInput(attrs=C),
                                  help_text="Escriba cómo debió registrarse. El evento original se conserva.")
    observaciones = forms.CharField(label="Motivo de la corrección", max_length=500, widget=forms.Textarea(attrs={**C, "rows": 2}))


class SimulacroForm(forms.ModelForm):
    class Meta:
        model = SimulacroRetiro
        fields = ["lote", "metodo", "minutos", "completitud_pct", "observaciones"]
        widgets = {"lote": forms.Select(attrs=S), "metodo": forms.Select(attrs=S), "minutos": forms.NumberInput(attrs=C),
                   "completitud_pct": forms.NumberInput(attrs=C), "observaciones": forms.Textarea(attrs={**C, "rows": 2})}

    def clean(self):
        d = super().clean()
        if d.get("minutos") is not None and d["minutos"] <= 0:
            self.add_error("minutos", "Debe ser mayor que 0.")
        if d.get("completitud_pct") is not None and d["completitud_pct"] > 100:
            self.add_error("completitud_pct", "Debe estar entre 0 y 100.")
        return d
