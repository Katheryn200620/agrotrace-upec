from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from cuentas import permissions as perm
from cuentas.mixins import FECHA, FECHA_HORA, FormularioBase
from parcelas.models import Parcela
from productores.models import Productor
from productos.models import Producto

from .models import Clasificacion, Cosecha, Recepcion

TOLERANCIA_PESO = Decimal("1.05")


class CosechaForm(FormularioBase):
    class Meta:
        model = Cosecha
        fields = ["parcela", "productor", "producto", "fecha", "cantidad", "unidad", "observaciones"]
        widgets = {"fecha": FECHA}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parcela"].queryset = Parcela.objects.exclude(estado_cultivo="descanso").select_related("productor", "cultivo")
        self.fields["productor"].queryset = Productor.objects.filter(estado="activo")
        self.fields["producto"].queryset = Producto.objects.filter(estado="activo").exclude(categoria="procesado")
        # Si la cosecha ya pasó a planta o a lotes, su origen y cantidad no se cambian
        if self.instance.pk and (self.instance.recibida or self.instance.lotes.exists()):
            for c in ("parcela", "productor", "producto", "cantidad", "unidad"):
                self.fields[c].disabled = True
                self.fields[c].help_text = "Bloqueado: la cosecha ya fue recibida en planta."

    def clean(self):
        d = super().clean()
        p, prod, prd = d.get("parcela"), d.get("productor"), d.get("producto")
        if p and prod and p.productor_id != prod.id:
            self.add_error("productor", f"La parcela {p.codigo} pertenece a {p.productor.nombre}, no a este productor.")
        if p and prd and p.cultivo_id != prd.id:
            self.add_error("producto", f"En la parcela {p.codigo} se cultiva {p.cultivo.nombre}.")
        c = d.get("cantidad")
        if c is not None and c <= 0:
            self.add_error("cantidad", "La cantidad debe ser mayor que 0.")
        f = d.get("fecha")
        if f and f > timezone.localdate():
            self.add_error("fecha", "La fecha de cosecha no puede estar en el futuro.")
        if f and p and p.fecha_siembra and f < p.fecha_siembra:
            self.add_error("fecha", f"Es anterior a la siembra ({p.fecha_siembra:%d/%m/%Y}).")
        return d


class RecepcionForm(FormularioBase):
    class Meta:
        model = Recepcion
        fields = ["cosecha", "fecha_hora", "peso_recibido", "temperatura", "minutos_recepcion", "observaciones"]
        widgets = {"fecha_hora": FECHA_HORA}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Cosecha.objects.filter(recepcion__isnull=True)
        if self.instance.pk:
            qs = Cosecha.objects.filter(pk=self.instance.cosecha_id)
            self.fields["cosecha"].disabled = True
        elif not perm.es_admin(self.usuario):
            qs = qs.filter(responsable=self.usuario)
        self.fields["cosecha"].queryset = qs

    def clean(self):
        d = super().clean()
        c, peso, t, fh = d.get("cosecha"), d.get("peso_recibido"), d.get("temperatura"), d.get("fecha_hora")
        if peso is not None and peso <= 0:
            self.add_error("peso_recibido", "Debe ser mayor que 0.")
        if c and peso and c.unidad == "kg" and peso > c.cantidad * TOLERANCIA_PESO:
            self.add_error("peso_recibido", f"Supera en más de 5 % lo cosechado ({c.cantidad} kg). Revise la báscula.")
        if t is not None and not (Decimal("-5") <= t <= Decimal("40")):
            self.add_error("temperatura", "La temperatura debe estar entre −5 y 40 °C.")
        if fh and fh > timezone.now() + timedelta(minutes=5):
            self.add_error("fecha_hora", "No puede estar en el futuro.")
        if c and fh and timezone.localtime(fh).date() < c.fecha:
            self.add_error("fecha_hora", "La recepción no puede ser anterior a la cosecha.")
        if self.instance.pk and peso is not None and peso < self.instance.kg_clasificados:
            self.add_error("peso_recibido", f"Ya se clasificaron {self.instance.kg_clasificados} kg.")
        return d


class ClasificacionForm(FormularioBase):
    class Meta:
        model = Clasificacion
        fields = ["recepcion", "categoria", "cantidad", "metodo", "confianza_modelo", "causa_rechazo", "foto"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Recepcion.objects.select_related("cosecha")
        if self.instance.pk:
            qs = qs.filter(pk=self.instance.recepcion_id)
            self.fields["recepcion"].disabled = True
        elif not perm.es_admin(self.usuario):
            qs = qs.filter(responsable=self.usuario)
        self.fields["recepcion"].queryset = qs

    def clean(self):
        d = super().clean()
        if d.get("categoria") == "rechazo" and not d.get("causa_rechazo"):
            self.add_error("causa_rechazo", "Indique la causa del rechazo.")
        kg, r = d.get("cantidad"), d.get("recepcion")
        if kg is not None and kg <= 0:
            self.add_error("cantidad", "Debe ser mayor que 0.")
        if r and kg:
            ya = r.kg_clasificados - (self.instance.cantidad if self.instance.pk else 0)
            if ya + kg > r.peso_recibido:
                self.add_error("cantidad", f"Quedan {r.peso_recibido - ya} kg por clasificar de {r.peso_recibido} kg recibidos.")
        conf = d.get("confianza_modelo")
        if d.get("metodo") == "modelo" and conf is None:
            self.add_error("confianza_modelo", "Indique la confianza que reportó el modelo.")
        if conf is not None and not (0 <= conf <= 1):
            self.add_error("confianza_modelo", "Debe estar entre 0 y 1.")
        return d
