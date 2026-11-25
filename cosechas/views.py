from cuentas import mixins as m
from cuentas.models import Area

from .forms import ClasificacionForm, CosechaForm, RecepcionForm
from .models import Clasificacion, Cosecha, Recepcion


class BaseCosecha:
    modelo = Cosecha
    area = Area.COSECHAS
    titulo = "Cosechas"
    titulo_singular = "Cosecha"
    url_base = "cosechas:cosecha"
    form_class = CosechaForm
    plantilla_detalle = "cosechas/cosecha_detalle.html"
    campos_detalle = [("codigo", "Código"), ("producto", "Producto cosechado"), ("productor", "Productor"),
                      ("parcela", "Parcela de origen"), ("fecha", "Fecha de cosecha"), ("cantidad", "Cantidad"),
                      ("unidad", "Unidad"), ("observaciones", "Observaciones"), ("responsable", "Operador responsable")]


class CosechaLista(BaseCosecha, m.ListaView):
    columnas = [("codigo", "Código"), ("fecha", "Fecha"), ("producto.nombre", "Producto"), ("parcela.codigo", "Parcela"),
                ("productor.nombre", "Productor"), ("cantidad", "Cantidad"), ("unidad", "Unidad")]
    campos_busqueda = ["codigo", "producto__nombre", "parcela__codigo", "productor__nombre"]
    filtros = [("estado_revision", "Revisión", Cosecha.REVISION)]


class CosechaDetalle(BaseCosecha, m.DetalleView):
    def extra_detalle(self, obj):
        rec = getattr(obj, "recepcion", None) if obj.recibida else None
        return {"recepcion": rec, "clasificaciones": rec.clasificaciones.all() if rec else [],
                "lotes": obj.lotes.all(), "eventos": obj.eventos.all()}


class CosechaCrear(BaseCosecha, m.CrearView):
    ayuda = "La parcela, el productor y el producto deben coincidir. El código se genera solo."


class CosechaEditar(BaseCosecha, m.EditarView):
    pass


class CosechaEliminar(BaseCosecha, m.EliminarView):
    pass


class CosechaRevisar(BaseCosecha, m.RevisarView):
    pass


class BaseRecepcion:
    modelo = Recepcion
    area = Area.COSECHAS
    titulo = "Recepción en planta"
    titulo_singular = "Recepción"
    url_base = "cosechas:recepcion"
    form_class = RecepcionForm
    campos_detalle = [("cosecha", "Cosecha"), ("fecha_hora", "Fecha y hora"), ("peso_recibido", "Peso recibido (kg)"),
                      ("temperatura", "Temperatura (°C)"), ("minutos_recepcion", "Tiempo de recepción (min)"),
                      ("kg_clasificados", "Kg clasificados"), ("kg_rechazo", "Kg rechazados"),
                      ("porcentaje_rechazo", "% de rechazo"), ("observaciones", "Observaciones"), ("responsable", "Recibido por")]


class RecepcionLista(BaseRecepcion, m.ListaView):
    columnas = [("cosecha.codigo", "Cosecha"), ("fecha_hora", "Fecha y hora"), ("peso_recibido", "Kg recibidos"),
                ("temperatura", "T °C"), ("porcentaje_rechazo", "% rechazo")]
    campos_busqueda = ["cosecha__codigo"]


class RecepcionDetalle(BaseRecepcion, m.DetalleView):
    def extra_detalle(self, obj):
        return {"relacionados": [("Clasificaciones", obj.clasificaciones.all())]}


class RecepcionCrear(BaseRecepcion, m.CrearView):
    ayuda = "Solo aparecen sus cosechas que aún no se han recibido. El peso no puede superar en más de 5 % lo cosechado."


class RecepcionEditar(BaseRecepcion, m.EditarView):
    pass


class RecepcionEliminar(BaseRecepcion, m.EliminarView):
    pass


class RecepcionRevisar(BaseRecepcion, m.RevisarView):
    pass


class BaseClasificacion:
    modelo = Clasificacion
    area = Area.COSECHAS
    titulo = "Clasificación de calidad"
    titulo_singular = "Clasificación"
    url_base = "cosechas:clasificacion"
    form_class = ClasificacionForm
    campos_detalle = [("recepcion", "Recepción"), ("get_categoria_display", "Categoría"), ("cantidad", "Cantidad (kg)"),
                      ("get_metodo_display", "Método"), ("confianza_modelo", "Confianza del modelo"),
                      ("causa_rechazo", "Causa del rechazo"), ("foto", "Foto"), ("responsable", "Clasificado por")]


class ClasificacionLista(BaseClasificacion, m.ListaView):
    columnas = [("recepcion.cosecha.codigo", "Cosecha"), ("get_categoria_display", "Categoría"), ("cantidad", "Kg"),
                ("get_metodo_display", "Método"), ("causa_rechazo", "Causa del rechazo")]
    campos_busqueda = ["recepcion__cosecha__codigo", "causa_rechazo"]
    filtros = [("categoria", "Categoría", Clasificacion.CATEGORIAS), ("metodo", "Método", Clasificacion.METODOS)]


class ClasificacionDetalle(BaseClasificacion, m.DetalleView):
    pass


class ClasificacionCrear(BaseClasificacion, m.CrearView):
    ayuda = "Registre una fila por categoría. Si es rechazo, indique la causa. La foto alimenta el modelo de visión artificial (F8)."


class ClasificacionEditar(BaseClasificacion, m.EditarView):
    pass


class ClasificacionEliminar(BaseClasificacion, m.EliminarView):
    pass


class ClasificacionRevisar(BaseClasificacion, m.RevisarView):
    pass
