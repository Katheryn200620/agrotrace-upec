from cuentas import mixins as m
from cuentas.models import Area

from .forms import ProductorForm
from .models import Productor


class Base:
    modelo = Productor
    area = Area.PRODUCTORES
    titulo = "Productores"
    titulo_singular = "Productor"
    url_base = "productores:productor"
    form_class = ProductorForm
    ayuda = "Los datos personales (cédula, teléfono y correo) solo los ven el área de productores y el administrador general."
    campos_detalle = [("codigo", "Código"), ("nombre", "Nombre o razón social"), ("get_tipo_display", "Tipo"),
                      ("identificacion", "Cédula o RUC"), ("ubicacion", "Ubicación"), ("telefono", "Teléfono"),
                      ("correo", "Correo"), ("get_estado_display", "Estado"),
                      ("mostrar_nombre_publico", "Nombre visible en el QR"), ("responsable", "Operador responsable"),
                      ("creado_en", "Creado"), ("actualizado_en", "Actualizado")]
    campos_privados = ["identificacion", "telefono", "correo"]


class Lista(Base, m.ListaView):
    columnas = [("codigo", "Código"), ("nombre", "Nombre"), ("get_tipo_display", "Tipo"), ("canton", "Cantón"),
                ("parroquia", "Parroquia"), ("get_estado_display", "Estado"), ("get_estado_revision_display", "Revisión")]
    campos_busqueda = ["codigo", "nombre", "canton", "parroquia"]
    filtros = [("estado", "Estado", Productor.ESTADOS), ("tipo", "Tipo", Productor.TIPOS),
               ("estado_revision", "Revisión", Productor.REVISION)]


class Detalle(Base, m.DetalleView):
    def extra_detalle(self, obj):
        return {"relacionados": [("Parcelas", obj.parcelas.all()), ("Cosechas", obj.cosechas.all()[:10])]}


class Crear(Base, m.CrearView):
    pass


class Editar(Base, m.EditarView):
    pass


class Eliminar(Base, m.EliminarView):
    pass


class Revisar(Base, m.RevisarView):
    pass
