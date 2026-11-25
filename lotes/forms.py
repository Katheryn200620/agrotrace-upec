from decimal import Decimal

from django import forms
from django.db.models import Sum
from django.utils import timezone

from cosechas.models import Cosecha
from cuentas.mixins import FECHA, FormularioBase
from productos.models import Producto

from .models import Lote


def _asignado(cosechas, excluir=None):
    """Cantidad ya usada en otros lotes creados con alguna de esas cosechas."""
    qs = Lote.objects.filter(cosechas__in=cosechas).distinct()
    if excluir:
        qs = qs.exclude(pk=excluir)
    return qs.aggregate(t=Sum("cantidad_inicial"))["t"] or Decimal("0")


class LoteCrearForm(FormularioBase):
    class Meta:
        model = Lote
        fields = ["producto", "cosechas", "categoria", "fecha_creacion", "cantidad_inicial", "ubicacion", "proceso", "publicado"]
        widgets = {"fecha_creacion": FECHA, "cosechas": forms.SelectMultiple(attrs={"size": 6})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["producto"].queryset = Producto.objects.filter(estado="activo").exclude(categoria="procesado")
        self.fields["cosechas"].queryset = Cosecha.objects.filter(recepcion__isnull=False).select_related("producto")
        self.fields["cosechas"].required = True
        self.fields["cosechas"].help_text = "Solo aparecen cosechas recibidas en planta. Mantenga Ctrl para elegir varias."
        self.fields["cantidad_inicial"].label = "Cantidad inicial"

    def clean(self):
        d = super().clean()
        prod, cos, cant, f = d.get("producto"), d.get("cosechas"), d.get("cantidad_inicial"), d.get("fecha_creacion")
        if cant is not None and cant <= 0:
            self.add_error("cantidad_inicial", "Debe ser mayor que 0.")
        if f and f > timezone.localdate():
            self.add_error("fecha_creacion", "No puede estar en el futuro.")
        if prod and cos:
            distintos = [c.codigo for c in cos if c.producto_id != prod.id]
            if distintos:
                self.add_error("cosechas", f"Estas cosechas no son de {prod.nombre}: {', '.join(distintos)}.")
            if f and any(c.fecha > f for c in cos):
                self.add_error("fecha_creacion", "El lote no puede crearse antes de la cosecha.")
            if cant and prod.unidad == "kg":
                aprovechable = sum((c.kg_aprovechables for c in cos), Decimal("0"))
                libre = aprovechable - _asignado(cos)
                if cant > libre:
                    self.add_error("cantidad_inicial", f"Solo quedan {libre} kg aprovechables de esas cosechas "
                                                       f"(recibido menos rechazo y menos lo ya asignado a otros lotes).")
        return d


class LoteEditarForm(FormularioBase):
    """Al editar no se cambia el origen, el producto ni las cantidades."""
    class Meta:
        model = Lote
        fields = ["categoria", "ubicacion", "proceso", "estado", "publicado"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["estado"].choices = [c for c in Lote.ESTADOS if c[0] in ("almacenamiento", "proceso")] \
            if self.instance.estado in ("almacenamiento", "proceso") else [(self.instance.estado, self.instance.get_estado_display())]
        self.fields["estado"].help_text = "Transporte, entrega y retiro se registran desde sus propias acciones."


class DividirForm(forms.Form):
    cantidad = forms.DecimalField(label="Cantidad para el nuevo lote", min_value=Decimal("0.01"), decimal_places=2,
                                  widget=forms.NumberInput(attrs={"class": "form-control"}))
    ubicacion = forms.CharField(label="Ubicación del nuevo lote", max_length=80, initial="Cámara de poscosecha",
                                widget=forms.TextInput(attrs={"class": "form-control"}))
    observaciones = forms.CharField(required=False, max_length=200, widget=forms.TextInput(attrs={"class": "form-control"}))


class TransformarForm(forms.Form):
    cantidad_origen = forms.DecimalField(label="Cantidad que se usa del lote", min_value=Decimal("0.01"), decimal_places=2,
                                         widget=forms.NumberInput(attrs={"class": "form-control"}))
    producto = forms.ModelChoiceField(label="Producto resultante", queryset=Producto.objects.filter(estado="activo", categoria="procesado"),
                                      widget=forms.Select(attrs={"class": "form-select"}))
    cantidad_resultado = forms.DecimalField(label="Cantidad obtenida", min_value=Decimal("0.01"), decimal_places=2,
                                            widget=forms.NumberInput(attrs={"class": "form-control"}))
    proceso = forms.CharField(label="Proceso aplicado", max_length=150, widget=forms.TextInput(attrs={"class": "form-control"}),
                              help_text="Ej.: despulpado, pasteurización y envasado de 500 g")


class CombinarForm(forms.Form):
    lotes = forms.ModelMultipleChoiceField(label="Lotes que se combinan", queryset=Lote.objects.none(),
                                           widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 6}))
    ubicacion = forms.CharField(label="Ubicación del lote combinado", max_length=80, initial="Cámara de poscosecha",
                                widget=forms.TextInput(attrs={"class": "form-control"}))

    def __init__(self, *args, queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lotes"].queryset = queryset

    def clean_lotes(self):
        lotes = self.cleaned_data["lotes"]
        if len(lotes) < 2:
            raise forms.ValidationError("Elija al menos dos lotes.")
        if len({l.producto_id for l in lotes}) > 1:
            raise forms.ValidationError("Solo se combinan lotes del mismo producto.")
        return lotes


class MotivoForm(forms.Form):
    motivo = forms.CharField(label="Motivo", max_length=200, widget=forms.TextInput(attrs={"class": "form-control"}))


class CorregirOrigenForm(forms.Form):
    cosechas = forms.ModelMultipleChoiceField(label="Cosechas de origen correctas",
                                              queryset=Cosecha.objects.filter(recepcion__isnull=False),
                                              widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 6}))
    justificacion = forms.CharField(label="Justificación (quedará en la auditoría)", max_length=250,
                                    widget=forms.TextInput(attrs={"class": "form-control"}))
