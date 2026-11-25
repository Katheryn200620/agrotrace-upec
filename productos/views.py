from cuentas import mixins as m
from cuentas.models import Area

from .forms import ProductoForm
from .models import Producto


class Base:
    modelo = Producto
    area = Area.PRODUCTOS
    titulo = "Catálogo de productos"
    titulo_singular = "Producto"
    url_base = "productos:producto"
    form_class = ProductoForm
    campos_detalle = [("codigo", "Código"), ("nombre", "Nombre"), ("get_categoria_display", "Categoría"),
                      ("variedad", "Variedad"), ("get_unidad_display", "Unidad"), ("gtin", "GTIN-14"),
                      ("vida_util_dias", "Vida útil (días)"), ("precio", "Precio referencial ($)"), ("stock_minimo", "Stock mínimo"),
                      ("descripcion", "Descripción"), ("get_estado_display", "Estado"), ("foto", "Fotografía"), ("responsable", "Responsable")]


class Lista(Base, m.ListaView):
    columnas = [("codigo", "Código"), ("nombre", "Nombre"), ("get_categoria_display", "Categoría"),
                ("variedad", "Variedad"), ("get_unidad_display", "Unidad"), ("gtin", "GTIN"), ("get_estado_display", "Estado")]
    campos_busqueda = ["codigo", "nombre", "variedad", "gtin"]
    filtros = [("categoria", "Categoría", Producto.CATEGORIAS), ("estado", "Estado", Producto.ESTADOS)]


class Detalle(Base, m.DetalleView):
    def extra_detalle(self, obj):
        return {"relacionados": [("Lotes recientes", obj.lotes.all()[:10])]}


class Crear(Base, m.CrearView):
    pass


class Editar(Base, m.EditarView):
    pass


class Eliminar(Base, m.EliminarView):
    pass


class Revisar(Base, m.RevisarView):
    pass
