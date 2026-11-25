from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from cuentas import mixins as m
from cuentas import permissions as perm
from cuentas.auditoria import registrar
from cuentas.models import Area
from trazabilidad.servicios import registrar_evento

from .forms import ClienteForm, VentaEditarForm, VentaForm
from .models import Cliente, Venta
from .servicios import disponible_para_vender


class BaseC:
    modelo = Cliente
    area = Area.COMERCIAL
    area_datos_privados = Area.COMERCIAL
    titulo = "Clientes"
    titulo_singular = "Cliente"
    url_base = "comercial:cliente"
    form_class = ClienteForm
    campos_detalle = [("codigo", "Código"), ("nombre", "Nombre o razón social"), ("get_tipo_display", "Tipo"),
                      ("identificacion", "Cédula o RUC"), ("ciudad", "Ciudad"), ("direccion", "Dirección"),
                      ("telefono", "Teléfono"), ("correo", "Correo"), ("activo", "Activo"), ("responsable", "Registrado por")]
    campos_privados = ["identificacion", "telefono", "correo", "direccion"]


class CLista(BaseC, m.ListaView):
    columnas = [("codigo", "Código"), ("nombre", "Nombre"), ("get_tipo_display", "Tipo"), ("ciudad", "Ciudad"), ("activo", "Activo")]
    campos_busqueda = ["codigo", "nombre", "ciudad"]
    filtros = [("tipo", "Tipo", Cliente.TIPOS)]
    ayuda = "Mayoristas, minoristas, comercios y demás destinos de los lotes."


class CDetalle(BaseC, m.DetalleView):
    plantilla_detalle = "comercial/cliente_detalle.html"

    def extra_detalle(self, obj):
        ventas = obj.ventas.select_related("lote__producto")
        return {"ventas": ventas[:20],
                "lotes_entregados": sorted({v.lote.codigo for v in ventas if v.estado in ("despachada", "entregada", "parcial")})}


class CCrear(BaseC, m.CrearView):
    pass


class CEditar(BaseC, m.EditarView):
    pass


class CEliminar(BaseC, m.EliminarView):
    pass


class CRevisar(BaseC, m.RevisarView):
    pass


class BaseV:
    modelo = Venta
    area = Area.COMERCIAL
    titulo = "Ventas"
    titulo_singular = "Venta"
    url_base = "comercial:venta"
    form_class = VentaForm
    permite_eliminar = False
    plantilla_detalle = "comercial/venta_detalle.html"
    campos_detalle = [("responsable", "Operador responsable"), ("observaciones", "Observaciones"),
                      ("creado_en", "Registrada"), ("actualizado_en", "Última actualización")]


class VLista(BaseV, m.ListaView):
    columnas = [("codigo", "Código"), ("fecha", "Fecha"), ("cliente.nombre", "Cliente"), ("lote.codigo", "Lote"),
                ("cantidad", "Cantidad"), ("total", "Total ($)"), ("get_estado_display", "Estado")]
    campos_busqueda = ["codigo", "cliente__nombre", "lote__codigo", "referencia"]
    filtros = [("estado", "Estado", Venta.ESTADOS), ("canal", "Canal", Venta.CANALES)]
    ayuda = "La venta reserva la cantidad del lote; el inventario se descuenta cuando transporte la despacha."


class VDetalle(BaseV, m.DetalleView):
    def extra_detalle(self, obj):
        u = self.request.user
        return {"despachos": obj.despachos.select_related("transportista"),
                "puede_despachar": perm.puede(u, "crear", Area.TRANSPORTE) and obj.por_despachar > 0,
                "puede_anular": obj.estado == "pendiente" and perm.puede_editar_obj(u, obj, Area.COMERCIAL)}


class VCrear(BaseV, m.CrearView):
    ayuda = "Solo se puede vender lo que el lote tiene disponible y no está comprometido en otras ventas."

    def despues_de_guardar(self, obj, creando):
        lote = obj.lote
        registrar_evento("venta", obj.responsable,
                         f"Venta {obj.codigo}: {obj.cantidad} {lote.unidad} a {obj.cliente.get_tipo_display().lower()}",
                         lote=lote, cantidad=obj.cantidad, unidad=lote.unidad, disposicion="sellable_accessible")


class VEditar(BaseV, m.EditarView):
    form_class = VentaEditarForm


class VRevisar(BaseV, m.RevisarView):
    pass


@login_required
@require_POST
def anular(request, pk):
    v = get_object_or_404(Venta, pk=pk)
    perm.exigir(perm.puede_editar_obj(request.user, v, Area.COMERCIAL), request, f"Intento de anular la venta {v.codigo}")
    motivo = request.POST.get("motivo", "").strip()
    if v.estado != "pendiente" or not motivo:
        messages.error(request, "Solo se anulan ventas pendientes de despacho y con un motivo.")
        return redirect(v)
    with transaction.atomic():
        v.estado = "anulada"
        v.save(update_fields=["estado", "actualizado_en"])
        ev = v.lote.eventos.filter(tipo="venta", descripcion__startswith=f"Venta {v.codigo}").first()
        registrar_evento("correccion", request.user, f"Venta {v.codigo} anulada; se libera la reserva del lote",
                         lote=v.lote, corrige=ev, observaciones=motivo)
        registrar(request, "editar", v, detalle="Venta anulada", justificacion=motivo)
    messages.success(request, f"Venta {v.codigo} anulada.")
    return redirect(v)


@login_required
def disponible(request, lote_pk):
    """Cantidad que aún se puede vender de un lote (para el formulario)."""
    from django.http import JsonResponse
    from lotes.models import Lote
    perm.exigir(perm.administra_area(request.user, Area.COMERCIAL), request, "Consulta de disponibilidad comercial")
    lote = get_object_or_404(Lote, pk=lote_pk)
    return JsonResponse({"lote": lote.codigo, "disponible": float(disponible_para_vender(lote)), "unidad": lote.unidad,
                         "precio": float(lote.producto.precio)})
