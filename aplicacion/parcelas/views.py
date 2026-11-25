from django.db.models import Sum
from django.http import JsonResponse

from cosechas.models import Clasificacion, Recepcion
from cuentas import mixins as m
from cuentas.models import Area

from .forms import LaborForm, ParcelaForm
from .models import Labor, Parcela


class BaseParcela:
    modelo = Parcela
    area = Area.PARCELAS
    titulo = "Parcelas y cultivos"
    titulo_singular = "Parcela"
    url_base = "parcelas:parcela"
    form_class = ParcelaForm
    plantilla_detalle = "parcelas/parcela_detalle.html"
    campos_detalle = [("codigo", "Código"), ("nombre", "Nombre"), ("productor", "Productor"), ("cultivo", "Cultivo"),
                      ("variedad", "Variedad"), ("superficie", "Superficie"), ("get_unidad_superficie_display", "Unidad"),
                      ("fecha_siembra", "Fecha de siembra"), ("get_estado_cultivo_display", "Estado del cultivo"),
                      ("latitud", "Latitud"), ("longitud", "Longitud"), ("altitud_msnm", "Altitud (m s. n. m.)"),
                      ("gln", "GLN (GS1)"), ("responsable", "Operador responsable")]


class ParcelaLista(BaseParcela, m.ListaView):
    columnas = [("codigo", "Código"), ("nombre", "Nombre"), ("productor.nombre", "Productor"), ("cultivo.nombre", "Cultivo"),
                ("superficie", "Superficie"), ("get_estado_cultivo_display", "Estado"), ("get_estado_revision_display", "Revisión")]
    campos_busqueda = ["codigo", "nombre", "productor__nombre", "cultivo__nombre"]
    filtros = [("estado_cultivo", "Estado del cultivo", Parcela.ESTADOS), ("estado_revision", "Revisión", Parcela.REVISION)]


class ParcelaDetalle(BaseParcela, m.DetalleView):
    def extra_detalle(self, obj):
        rec = Recepcion.objects.filter(cosecha__parcela=obj).aggregate(t=Sum("peso_recibido"))["t"] or 0
        rch = Clasificacion.objects.filter(recepcion__cosecha__parcela=obj, categoria="rechazo").aggregate(t=Sum("cantidad"))["t"] or 0
        return {"labores": obj.labores.all()[:15], "cosechas": obj.cosechas.select_related("producto").prefetch_related("lotes")[:15],
                "pct_rechazo": round(rch * 100 / rec, 1) if rec else None}


class ParcelaCrear(BaseParcela, m.CrearView):
    ayuda = "Las coordenadas se usan en el mapa de QGIS. Tómelas con el GPS del celular en la parcela."


class ParcelaEditar(BaseParcela, m.EditarView):
    pass


class ParcelaEliminar(BaseParcela, m.EliminarView):
    pass


class ParcelaRevisar(BaseParcela, m.RevisarView):
    pass


class BaseLabor:
    modelo = Labor
    area = Area.PARCELAS
    titulo = "Labores agrícolas"
    titulo_singular = "Labor"
    url_base = "parcelas:labor"
    form_class = LaborForm
    campos_detalle = [("parcela", "Parcela"), ("get_tipo_display", "Labor"), ("fecha", "Fecha"), ("insumo", "Insumo"),
                      ("dosis", "Dosis"), ("descripcion", "Observaciones"), ("responsable", "Registrada por")]


class LaborLista(BaseLabor, m.ListaView):
    columnas = [("fecha", "Fecha"), ("parcela.codigo", "Parcela"), ("get_tipo_display", "Labor"), ("insumo", "Insumo"),
                ("dosis", "Dosis")]
    campos_busqueda = ["parcela__codigo", "insumo"]
    filtros = [("tipo", "Labor", Labor.TIPOS)]


class LaborDetalle(BaseLabor, m.DetalleView):
    pass


class LaborCrear(BaseLabor, m.CrearView):
    ayuda = "Solo puede registrar labores en las parcelas a su cargo. Cada labor queda en el historial de trazabilidad."


class LaborEditar(BaseLabor, m.EditarView):
    pass


class LaborEliminar(BaseLabor, m.EliminarView):
    pass


class LaborRevisar(BaseLabor, m.RevisarView):
    pass


def parcelas_geojson(request):
    """Capa de parcelas para QGIS (Capa > Añadir capa vectorial > HTTP). No incluye datos personales."""
    features = []
    for p in Parcela.objects.exclude(latitud=None).select_related("cultivo"):
        rec = Recepcion.objects.filter(cosecha__parcela=p).aggregate(t=Sum("peso_recibido"))["t"] or 0
        rch = Clasificacion.objects.filter(recepcion__cosecha__parcela=p, categoria="rechazo").aggregate(t=Sum("cantidad"))["t"] or 0
        cos = p.cosechas.aggregate(t=Sum("cantidad"))["t"] or 0
        features.append({"type": "Feature",
                         "geometry": {"type": "Point", "coordinates": [float(p.longitud), float(p.latitud)]},
                         "properties": {"codigo": p.codigo, "nombre": p.nombre, "cultivo": p.cultivo.nombre,
                                        "superficie": float(p.superficie), "unidad": p.unidad_superficie, "gln": p.gln,
                                        "estado": p.get_estado_cultivo_display(), "kg_cosechados": float(cos),
                                        "kg_recibidos": float(rec), "kg_rechazo": float(rch),
                                        "pct_rechazo": round(float(rch) * 100 / float(rec), 1) if rec else None}})
    return JsonResponse({"type": "FeatureCollection", "features": features})
