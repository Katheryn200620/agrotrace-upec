from decimal import Decimal

from django import forms
from django.utils import timezone

from cuentas import permissions as perm
from cuentas.mixins import FECHA, FormularioBase
from productores.models import Productor
from productos.models import Producto

from .models import Labor, Parcela

# Límites aproximados de la provincia del Carchi (diccionario de datos)
LAT = (Decimal("0.30"), Decimal("1.30"))
LON = (Decimal("-78.70"), Decimal("-77.40"))


class ParcelaForm(FormularioBase):
    class Meta:
        model = Parcela
        fields = ["codigo", "nombre", "productor", "cultivo", "variedad", "superficie", "unidad_superficie",
                  "fecha_siembra", "estado_cultivo", "latitud", "longitud", "altitud_msnm"]
        widgets = {"fecha_siembra": FECHA}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Consulta compartida: se eligen productores y productos activos sin poder editarlos
        self.fields["productor"].queryset = Productor.objects.filter(estado="activo")
        self.fields["cultivo"].queryset = Producto.objects.filter(estado="activo").exclude(categoria="procesado")

    def clean(self):
        d = super().clean()
        if d.get("superficie") is not None and d["superficie"] <= 0:
            self.add_error("superficie", "La superficie debe ser mayor que 0.")
        fs = d.get("fecha_siembra")
        if fs and fs > timezone.localdate():
            self.add_error("fecha_siembra", "La fecha de siembra no puede estar en el futuro.")
        lat, lon = d.get("latitud"), d.get("longitud")
        if (lat is None) != (lon is None):
            self.add_error("longitud", "Escriba latitud y longitud, o deje ambas vacías.")
        if lat is not None and not (LAT[0] <= lat <= LAT[1]):
            self.add_error("latitud", "Está fuera de la provincia del Carchi (≈ 0,3 a 1,3).")
        if lon is not None and not (LON[0] <= lon <= LON[1]):
            self.add_error("longitud", "Está fuera de la provincia del Carchi (≈ −78,7 a −77,4).")
        return d


class LaborForm(FormularioBase):
    class Meta:
        model = Labor
        fields = ["parcela", "tipo", "fecha", "insumo", "dosis", "descripcion"]
        widgets = {"fecha": FECHA}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Parcela.objects.all()
        if not perm.es_admin(self.usuario):
            qs = qs.filter(responsable=self.usuario)   # solo en sus propias parcelas
        self.fields["parcela"].queryset = qs

    def clean(self):
        d = super().clean()
        f, p = d.get("fecha"), d.get("parcela")
        if f and f > timezone.localdate():
            self.add_error("fecha", "La fecha no puede estar en el futuro.")
        if f and p and p.fecha_siembra and f < p.fecha_siembra and d.get("tipo") != "siembra":
            self.add_error("fecha", f"Es anterior a la siembra de la parcela ({p.fecha_siembra:%d/%m/%Y}).")
        return d
