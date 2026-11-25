from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from comercial.servicios import actualizar_estado
from cuentas import mixins as m
from cuentas import permissions as perm
from cuentas.auditoria import registrar
from cuentas.models import Area
from lotes.models import Lote
from trazabilidad.servicios import registrar_evento

from .forms import DespachoEditarForm, DespachoForm, EntregaForm, TransportistaForm
from .models import Despacho, Transportista


class BaseT:
    modelo = Transportista
    area = Area.TRANSPORTE
    area_datos_privados = Area.TRANSPORTE
    titulo = "Transportistas"
    titulo_singular = "Transportista"
    url_base = "transporte:transportista"
    form_class = TransportistaForm
    campos_detalle = [("nombre", "Nombre o empresa"), ("identificacion", "Cédula o RUC"), ("telefono", "Teléfono"),
                      ("vehiculo_placa", "Placa"), ("tipo_vehiculo", "Tipo de vehículo"), ("refrigerado", "Refrigerado"),
                      ("activo", "Activo"), ("responsable", "Registrado por")]
    campos_privados = ["identificacion", "telefono"]


class TLista(BaseT, m.ListaView):
    columnas = [("nombre", "Nombre"), ("vehiculo_placa", "Placa"), ("tipo_vehiculo", "Vehículo"), ("refrigerado", "Refrigerado"),
                ("activo", "Activo")]
    campos_busqueda = ["nombre", "vehiculo_placa"]


class TDetalle(BaseT, m.DetalleView):
    def extra_detalle(self, obj):
        return {"relacionados": [("Despachos", obj.despachos.all()[:10])]}


class TCrear(BaseT, m.CrearView):
    pass


class TEditar(BaseT, m.EditarView):
    pass


class TEliminar(BaseT, m.EliminarView):
    pass


class TRevisar(BaseT, m.RevisarView):
    pass


class BaseD:
    modelo = Despacho
    area = Area.TRANSPORTE
    titulo = "Despachos"
    titulo_singular = "Despacho"
    url_base = "transporte:despacho"
    form_class = DespachoForm
    permite_eliminar = False
    plantilla_detalle = "transporte/despacho_detalle.html"
    campos_detalle = [("venta", "Venta atendida"), ("responsable", "Operador responsable"), ("observaciones", "Observaciones"),
                      ("creado_en", "Registrado"), ("actualizado_en", "Última actualización")]


class DLista(BaseD, m.ListaView):
    columnas = [("codigo", "Código"), ("salida", "Salida"), ("lote.codigo", "Lote"), ("cantidad", "Cantidad"),
                ("get_tipo_destino_display", "Tipo de destino"), ("destino", "Destino"), ("get_estado_display", "Estado")]
    campos_busqueda = ["codigo", "lote__codigo", "destino"]
    filtros = [("estado", "Estado", Despacho.ESTADOS), ("tipo_destino", "Tipo de destino", Despacho.DESTINOS)]


class DDetalle(BaseD, m.DetalleView):
    def extra_detalle(self, obj):
        return {"form_entrega": EntregaForm(initial={"llegada": timezone.localtime().strftime("%Y-%m-%dT%H:%M")}),
                "eventos": obj.lote.eventos.filter(tipo__in=["despacho", "transporte", "recepcion_destino"])}


class DCrear(BaseD, m.CrearView):
    ayuda = "La cantidad se descuenta del lote al guardar. No se puede despachar más de lo disponible."

    def get(self, request):
        initial = {k: v for k, v in request.GET.items()}
        from comercial.models import Venta
        venta = Venta.objects.filter(pk=request.GET.get("venta") or 0, estado__in=["pendiente", "parcial"]).first()
        if venta:
            initial.update(venta=venta.pk, lote=venta.lote_id, cantidad=venta.por_despachar,
                           destino=f"{venta.cliente.nombre} – {venta.cliente.ciudad}",
                           tipo_destino="tienda" if venta.canal == "tienda" else "cliente")
        return self.render_form(self.preparar_form(self.form_class(initial=initial, usuario=request.user)))

    def antes_de_guardar(self, form, obj, creando):
        lote = Lote.objects.select_for_update().get(pk=obj.lote_id)
        if obj.cantidad > lote.cantidad_disponible:     # nueva verificación dentro de la transacción
            raise ValueError("cantidad")
        self._lote = lote

    def guardar(self, form, creando, antes=None):
        with transaction.atomic():        # el bloqueo del lote y el descuento van en la misma transacción
            return super().guardar(form, creando, antes)

    def post(self, request):
        form = self.preparar_form(self.form_class(request.POST, usuario=request.user))
        if form.is_valid():
            try:
                obj = self.guardar(form, creando=True)
            except ValueError:
                form.add_error("cantidad", "Mientras llenaba el formulario se despachó parte del lote. Revise lo disponible.")
            else:
                messages.success(request, f"Despacho {obj.codigo} registrado.")
                return redirect(obj)
        else:
            messages.error(request, "Revise los campos marcados en rojo.")
        return self.render_form(form)

    def despues_de_guardar(self, obj, creando):
        lote = self._lote
        lote.cantidad_disponible -= obj.cantidad
        lote.save(update_fields=["cantidad_disponible", "actualizado_en"])
        registrar_evento("despacho", obj.responsable,
                         f"Despacho {obj.codigo}: {obj.cantidad} {lote.unidad} hacia {obj.get_tipo_destino_display().lower()}",
                         lugar=obj.origen, lote=lote, cantidad=obj.cantidad, unidad=lote.unidad, fecha_hora=obj.salida,
                         disposicion="in_transit")
        if obj.venta_id:
            actualizar_estado(obj.venta)


class DEditar(BaseD, m.EditarView):
    form_class = DespachoEditarForm


class DRevisar(BaseD, m.RevisarView):
    pass


def _despacho_propio(request, pk):
    d = get_object_or_404(Despacho, pk=pk)
    perm.exigir(perm.puede_editar_obj(request.user, d, Area.TRANSPORTE), request,
                f"Intento de actualizar el despacho {d.codigo} de otro operador")
    return d


@login_required
@require_POST
def salir(request, pk):
    d = _despacho_propio(request, pk)
    if d.estado == "programado":
        with transaction.atomic():
            d.estado = "transito"
            d.save(update_fields=["estado", "actualizado_en"])
            lote = d.lote
            if lote.cantidad_disponible == 0 and lote.estado != "retirado":
                lote.estado = "transporte"
                lote.save(update_fields=["estado", "actualizado_en"])
            registrar_evento("transporte", request.user, f"Salida del despacho {d.codigo} hacia {d.destino}",
                             lugar=d.origen, lote=lote, cantidad=d.cantidad, unidad=lote.unidad, disposicion="in_transit")
            registrar(request, "editar", d, detalle="Despacho en tránsito")
        messages.success(request, f"Despacho {d.codigo} en tránsito.")
    return redirect(d)


@login_required
@require_POST
def entregar(request, pk):
    d = _despacho_propio(request, pk)
    form = EntregaForm(request.POST, despacho=d)
    if d.estado != "transito" or not form.is_valid():
        messages.error(request, "Revise la fecha de llegada. Solo se entregan despachos en tránsito.")
        return redirect(d)
    with transaction.atomic():
        d.estado = "entregado"
        d.llegada = form.cleaned_data["llegada"]
        d.entregado_a_tiempo = form.cleaned_data["entregado_a_tiempo"]
        d.km_recorridos = form.cleaned_data["km_recorridos"]
        d.save()
        lote = d.lote
        registrar_evento("recepcion_destino", request.user, f"Recepción en destino ({d.destino}) del despacho {d.codigo}",
                         lugar=d.destino, lote=lote, cantidad=d.cantidad, unidad=lote.unidad, fecha_hora=d.llegada,
                         disposicion="active")
        if lote.cantidad_disponible == 0 and not lote.despachos.exclude(estado__in=["entregado", "cancelado"]).exists() \
                and lote.estado != "retirado":
            lote.estado = "entregado"
            lote.save(update_fields=["estado", "actualizado_en"])
        if d.venta_id:
            actualizar_estado(d.venta)
        registrar(request, "editar", d, detalle="Despacho entregado")
    messages.success(request, f"Despacho {d.codigo} entregado.")
    return redirect(d)


@login_required
@require_POST
def cancelar(request, pk):
    d = _despacho_propio(request, pk)
    if d.estado != "programado":
        messages.error(request, "Solo se cancelan despachos que aún no salen.")
        return redirect(d)
    with transaction.atomic():
        lote = Lote.objects.select_for_update().get(pk=d.lote_id)
        lote.cantidad_disponible += d.cantidad
        if lote.estado in ("agotado", "transporte"):
            lote.estado = "almacenamiento"
        lote.save(update_fields=["cantidad_disponible", "estado", "actualizado_en"])
        d.estado = "cancelado"
        d.save(update_fields=["estado", "actualizado_en"])
        ev = lote.eventos.filter(tipo="despacho", descripcion__startswith=f"Despacho {d.codigo}").first()
        registrar_evento("correccion", request.user, f"Despacho {d.codigo} cancelado; {d.cantidad} {lote.unidad} vuelven al lote",
                         lote=lote, cantidad=d.cantidad, unidad=lote.unidad, corrige=ev,
                         observaciones=request.POST.get("motivo", ""))
        if d.venta_id:
            actualizar_estado(d.venta)
        registrar(request, "editar", d, detalle="Despacho cancelado", justificacion=request.POST.get("motivo", ""))
    messages.success(request, f"Despacho {d.codigo} cancelado. La cantidad volvió al lote.")
    return redirect(d)
