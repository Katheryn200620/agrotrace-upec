import io
from datetime import timedelta

import qrcode
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from cuentas import mixins as m
from cuentas import permissions as perm
from cuentas.auditoria import registrar
from cuentas.models import Area
from trazabilidad.models import EventoTrazabilidad
from trazabilidad.servicios import PLANTA, registrar_evento

from .forms import (CombinarForm, CorregirOrigenForm, DividirForm, LoteCrearForm,
                    LoteEditarForm, MotivoForm, TransformarForm)
from .models import Lote, RelacionLote


def historia_lote(lote):
    """Línea de tiempo completa: cultivo → cosecha → planta → lote (y sus orígenes) → transporte."""
    lotes = [lote] + lote.lotes_origen()
    cosechas = lote.todas_las_cosechas()
    eventos = EventoTrazabilidad.objects.filter(lote__in=lotes) | EventoTrazabilidad.objects.filter(cosecha__in=cosechas)
    fechas = [c.fecha for c in cosechas]
    if fechas:
        eventos = eventos | EventoTrazabilidad.objects.filter(
            parcela__in=lote.parcelas(), tipo="cultivo",
            fecha_hora__date__gt=max(fechas) - timedelta(days=365), fecha_hora__date__lte=max(fechas))
    return eventos.distinct().select_related("responsable__perfil__area", "lote", "corrige").order_by("fecha_hora", "id")


class Base:
    modelo = Lote
    area = Area.LOTES
    titulo = "Lotes"
    titulo_singular = "Lote"
    url_base = "lotes:lote"
    form_class = LoteCrearForm
    permite_eliminar = False
    plantilla_detalle = "lotes/lote_detalle.html"


class Lista(Base, m.ListaView):
    orden = ["-fecha_creacion", "-id"]
    columnas = [("codigo", "Lote"), ("producto.nombre", "Producto"), ("get_categoria_display", "Categoría"),
                ("cantidad_disponible", "Disponible"), ("unidad", "Unidad"), ("fecha_vencimiento", "Vence"),
                ("get_estado_display", "Estado"), ("completitud", "Trazabilidad %")]
    campos_busqueda = ["codigo", "producto__nombre", "cosechas__parcela__codigo", "cosechas__productor__nombre"]
    filtros = [("estado", "Estado", Lote.ESTADOS), ("categoria", "Categoría", Lote.CATEGORIAS)]


class Detalle(Base, m.DetalleView):
    def extra_detalle(self, obj):
        u = self.request.user
        es_resp = perm.puede_editar_obj(u, obj, Area.LOTES)
        activo = obj.estado not in ("retirado", "agotado", "entregado") and obj.cantidad_disponible > 0
        propios = Lote.objects.filter(producto=obj.producto, cantidad_disponible__gt=0) \
            .exclude(estado__in=["retirado", "agotado", "entregado"])
        if not perm.es_admin(u):
            propios = propios.filter(responsable=u)
        return {
            "eventos": historia_lote(obj), "control": obj.control_eventos(),
            "origenes": obj.origenes.select_related("origen", "responsable"),
            "derivados": obj.derivados.select_related("resultado"),
            "despachos": obj.despachos.all(), "escaneos": obj.escaneos.count(),
            "cosechas": obj.todas_las_cosechas(), "parcelas": obj.parcelas(),
            "puede_operar": es_resp and activo,
            "puede_retirar": es_resp and obj.estado != "retirado",
            "form_dividir": DividirForm(), "form_transformar": TransformarForm(), "form_motivo": MotivoForm(),
            "form_combinar": CombinarForm(queryset=propios, initial={"lotes": [obj.pk]}),
            "form_corregir": CorregirOrigenForm(initial={"cosechas": list(obj.cosechas.values_list("pk", flat=True))}),
        }


class Crear(Base, m.CrearView):
    ayuda = "Al crear el lote se genera su código, su QR GS1 Digital Link y su ficha pública de procedencia."


class Editar(Base, m.EditarView):
    form_class = LoteEditarForm
    ayuda = "El producto, las cosechas de origen y las cantidades no se cambian aquí: eso protege la procedencia."

    def guardar(self, form, creando, antes=None):
        self._antes = antes or {}
        return super().guardar(form, creando, antes)

    def despues_de_guardar(self, obj, creando):
        if obj.estado == "proceso" and self._antes.get("estado") != "proceso":
            registrar_evento("almacenamiento", self.request.user, f"Lote {obj.codigo} en proceso: {obj.proceso or 'sin detalle'}",
                             lugar=f"{PLANTA} – {obj.ubicacion}", lote=obj, disposicion="in_progress")


class Revisar(Base, m.RevisarView):
    pass


# ---------------------------------------------------------------------------
# Operaciones que conservan la procedencia
# ---------------------------------------------------------------------------
def _lote_operable(request, pk):
    lote = get_object_or_404(Lote, pk=pk)
    perm.exigir(perm.puede_editar_obj(request.user, lote, Area.LOTES), request,
                f"Intento de operar el lote {lote.codigo} de otro operador")
    return lote


@login_required
@require_POST
def dividir(request, pk):
    with transaction.atomic():
        lote = _lote_operable(request, pk)
        lote = Lote.objects.select_for_update().get(pk=lote.pk)
        form = DividirForm(request.POST)
        if not form.is_valid() or form.cleaned_data["cantidad"] >= lote.cantidad_disponible:
            messages.error(request, f"La cantidad debe ser mayor que 0 y menor que lo disponible ({lote.cantidad_disponible}).")
            return redirect(lote)
        c = form.cleaned_data["cantidad"]
        nuevo = Lote(producto=lote.producto, categoria=lote.categoria, cantidad_inicial=c, ubicacion=form.cleaned_data["ubicacion"],
                     proceso=lote.proceso, fecha_vencimiento=lote.fecha_vencimiento, responsable=request.user)
        nuevo._sin_evento = True
        nuevo.save()
        RelacionLote.objects.create(origen=lote, resultado=nuevo, tipo="division", cantidad=c, responsable=request.user,
                                    observaciones=form.cleaned_data["observaciones"])
        lote.cantidad_disponible -= c
        lote.save(update_fields=["cantidad_disponible", "actualizado_en"])
        for l, texto in ((lote, f"Se separaron {c} {lote.unidad} hacia el lote {nuevo.codigo}"),
                         (nuevo, f"Lote creado al dividir {lote.codigo} ({c} {lote.unidad})")):
            registrar_evento("division", request.user, texto, lote=l, cantidad=c, unidad=lote.unidad,
                             lugar=f"{PLANTA} – {l.ubicacion}")
        registrar(request, "operacion", lote, detalle=f"División: {c} {lote.unidad} → {nuevo.codigo}")
    messages.success(request, f"Lote dividido. Nuevo lote: {nuevo.codigo}.")
    return redirect(nuevo)


@login_required
@require_POST
def combinar(request, pk):
    base = _lote_operable(request, pk)
    qs = Lote.objects.filter(producto=base.producto, cantidad_disponible__gt=0).exclude(estado__in=["retirado", "agotado", "entregado"])
    if not perm.es_admin(request.user):
        qs = qs.filter(responsable=request.user)   # solo puede combinar sus propios lotes
    form = CombinarForm(request.POST, queryset=qs)
    if not form.is_valid():
        messages.error(request, " ".join(e for errs in form.errors.values() for e in errs))
        return redirect(base)
    with transaction.atomic():
        lotes = list(Lote.objects.select_for_update().filter(pk__in=[l.pk for l in form.cleaned_data["lotes"]]))
        total = sum(l.cantidad_disponible for l in lotes)
        peor = sorted(lotes, key=lambda l: ["extra", "primera", "segunda"].index(l.categoria))[-1].categoria
        nuevo = Lote(producto=base.producto, categoria=peor, cantidad_inicial=total, ubicacion=form.cleaned_data["ubicacion"],
                     fecha_vencimiento=min(l.fecha_vencimiento for l in lotes), responsable=request.user)
        nuevo._sin_evento = True
        nuevo.save()
        for l in lotes:
            RelacionLote.objects.create(origen=l, resultado=nuevo, tipo="combinacion", cantidad=l.cantidad_disponible,
                                        responsable=request.user)
            registrar_evento("combinacion", request.user, f"{l.cantidad_disponible} {l.unidad} pasaron al lote combinado {nuevo.codigo}",
                             lote=l, cantidad=l.cantidad_disponible, unidad=l.unidad)
            l.cantidad_disponible = 0
            l.estado = "agotado"
            l.save(update_fields=["cantidad_disponible", "estado", "actualizado_en"])
        registrar_evento("combinacion", request.user, f"Lote creado al combinar {', '.join(l.codigo for l in lotes)}",
                         lote=nuevo, cantidad=total, unidad=nuevo.unidad, lugar=f"{PLANTA} – {nuevo.ubicacion}")
        registrar(request, "operacion", nuevo, detalle=f"Combinación de {', '.join(l.codigo for l in lotes)}")
    messages.success(request, f"Lotes combinados en {nuevo.codigo}.")
    return redirect(nuevo)


@login_required
@require_POST
def transformar(request, pk):
    with transaction.atomic():
        lote = _lote_operable(request, pk)
        lote = Lote.objects.select_for_update().get(pk=lote.pk)
        form = TransformarForm(request.POST)
        if not form.is_valid() or form.cleaned_data["cantidad_origen"] > lote.cantidad_disponible:
            messages.error(request, f"Revise los datos. Disponible: {lote.cantidad_disponible} {lote.unidad}.")
            return redirect(lote)
        d = form.cleaned_data
        nuevo = Lote(producto=d["producto"], categoria=lote.categoria, cantidad_inicial=d["cantidad_resultado"],
                     proceso=d["proceso"], ubicacion="Bodega de producto terminado", responsable=request.user)
        nuevo._sin_evento = True
        nuevo.save()
        RelacionLote.objects.create(origen=lote, resultado=nuevo, tipo="transformacion", cantidad=d["cantidad_origen"],
                                    responsable=request.user, observaciones=d["proceso"])
        lote.cantidad_disponible -= d["cantidad_origen"]
        if lote.cantidad_disponible == 0:
            lote.estado = "agotado"
        lote.save(update_fields=["cantidad_disponible", "estado", "actualizado_en"])
        registrar_evento("transformacion", request.user, f"{d['cantidad_origen']} {lote.unidad} transformados en el lote {nuevo.codigo}",
                         lote=lote, cantidad=d["cantidad_origen"], unidad=lote.unidad)
        registrar_evento("transformacion", request.user,
                         f"{d['cantidad_resultado']} {nuevo.unidad} de {nuevo.producto.nombre} obtenidos de {lote.codigo}: {d['proceso']}",
                         lote=nuevo, cantidad=d["cantidad_resultado"], unidad=nuevo.unidad, lugar=f"{PLANTA} – área de proceso")
        registrar(request, "operacion", lote, detalle=f"Transformación → {nuevo.codigo}")
    messages.success(request, f"Transformación registrada. Nuevo lote: {nuevo.codigo}.")
    return redirect(nuevo)


@login_required
@require_POST
def retirar(request, pk):
    lote = _lote_operable(request, pk)
    form = MotivoForm(request.POST)
    if not form.is_valid() or lote.estado == "retirado":
        messages.error(request, "Indique el motivo del retiro.")
        return redirect(lote)
    with transaction.atomic():
        afectados = [lote] + list(Lote.objects.filter(origenes__origen=lote))
        for l in afectados:
            registrar_evento("retiro", request.user, f"Retiro del mercado: {form.cleaned_data['motivo']}", lote=l,
                             disposicion="recalled")
            l.estado = "retirado"
            l.save(update_fields=["estado", "actualizado_en"])
        registrar(request, "operacion", lote, detalle=f"Retiro del lote. Motivo: {form.cleaned_data['motivo']}")
    destinos = sorted({d.destino for l in afectados for d in l.despachos.exclude(estado="cancelado")})
    messages.warning(request, f"Lote {lote.codigo} retirado"
                              + (f" junto con sus lotes derivados ({', '.join(l.codigo for l in afectados[1:])})" if len(afectados) > 1 else "")
                              + f". Destinos a contactar: {', '.join(destinos) or 'ninguno'}.")
    return redirect(lote)


@login_required
@require_POST
def corregir_origen(request, pk):
    """Solo el administrador general, con justificación: el cambio y el estado anterior quedan auditados."""
    lote = get_object_or_404(Lote, pk=pk)
    perm.exigir(perm.es_admin(request.user), request, f"Intento de cambiar el origen del lote {lote.codigo}")
    form = CorregirOrigenForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Elija las cosechas y escriba la justificación.")
        return redirect(lote)
    antes = sorted(lote.cosechas.values_list("codigo", flat=True))
    nuevas = form.cleaned_data["cosechas"]
    with transaction.atomic():
        lote.cosechas.set(nuevas)
        despues = sorted(c.codigo for c in nuevas)
        registrar_evento("correccion", request.user, f"Corrección del origen: {', '.join(antes)} → {', '.join(despues)}",
                         lote=lote, observaciones=form.cleaned_data["justificacion"], disposicion="active")
        registrar(request, "editar", lote, cambios={"cosechas": {"antes": antes, "despues": despues}},
                  justificacion=form.cleaned_data["justificacion"], detalle="Corrección administrativa del origen")
    messages.success(request, "Origen corregido y registrado en la auditoría.")
    return redirect(lote)


def qr_lote(request, pk):
    lote = get_object_or_404(Lote, pk=pk)
    img = qrcode.make(lote.link_gs1, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    resp = HttpResponse(buf.getvalue(), content_type="image/png")
    if request.GET.get("descargar"):
        resp["Content-Disposition"] = f'attachment; filename="QR_{lote.codigo}.png"'
    return resp


# ---------------------------------------------------------------------------
# Inventario (Área 5: almacenamiento e inventarios)
# ---------------------------------------------------------------------------
def _puede_inventario(request):
    perm.exigir(perm.administra_area(request.user, Area.LOTES) or perm.area_de(request.user) == Area.REPORTES,
                request, "Acceso al inventario")


@login_required
def inventario(request):
    from .inventario import alertas_inventario, existencias, lotes_visibles, por_ubicacion
    _puede_inventario(request)
    lotes = lotes_visibles(request.user)
    activos = lotes.filter(estado__in=["almacenamiento", "proceso", "transporte"], cantidad_disponible__gt=0).order_by("fecha_vencimiento")
    return render(request, "lotes/inventario.html", {
        "titulo": "Inventario actual", "existencias": existencias(lotes), "ubicaciones": por_ubicacion(lotes),
        "activos": activos, "alertas": alertas_inventario(lotes), "hoy": timezone.localdate()})


@login_required
def movimientos(request):
    from datetime import date
    from django.core.paginator import Paginator
    from .inventario import lotes_visibles, movimientos as calcular
    _puede_inventario(request)

    def fecha(n):
        try:
            return date.fromisoformat(request.GET.get(n, ""))
        except ValueError:
            return None
    lotes = lotes_visibles(request.user)
    codigo = request.GET.get("lote", "").strip()
    if codigo:
        lotes = lotes.filter(codigo__icontains=codigo)
    movs = calcular(lotes, fecha("desde"), fecha("hasta"))
    tipo = request.GET.get("tipo", "")
    if tipo in ("entrada", "salida"):
        movs = [x for x in movs if x["tipo"] == tipo]
    if request.GET.get("exportar") == "csv":
        import csv
        from django.http import HttpResponse
        from cuentas.auditoria import registrar
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="movimientos_inventario.csv"'
        resp.write("﻿")
        w = csv.writer(resp, delimiter=";")
        w.writerow(["Fecha", "Lote", "Producto", "Tipo", "Motivo", "Cantidad", "Unidad", "Documento"])
        for x in movs:
            w.writerow([timezone.localtime(x["fecha"]).strftime("%d/%m/%Y %H:%M"), x["lote"].codigo, x["lote"].producto.nombre,
                        x["tipo"], x["motivo"], x["cantidad"], x["unidad"], x["doc"]])
        registrar(request, "exportar", detalle=f"Exportó {len(movs)} movimientos de inventario")
        return resp
    params = request.GET.copy(); params.pop("page", None)
    return render(request, "lotes/movimientos.html", {
        "titulo": "Entradas y salidas", "pagina": Paginator(movs, 20).get_page(request.GET.get("page")),
        "total": len(movs), "f": request.GET, "params": params.urlencode()})


@login_required
def etiquetas(request):
    """Etiquetas de trazabilidad para imprimir y pegar en sacos, gavetas o envases (prototipo físico)."""
    from .inventario import lotes_visibles
    _puede_inventario(request)
    lotes = lotes_visibles(request.user).exclude(estado="retirado")
    elegidos = [int(x) for x in request.GET.getlist("lote") if x.isdigit()]
    if elegidos:
        lotes = lotes.filter(pk__in=elegidos)
    else:
        lotes = lotes.filter(cantidad_disponible__gt=0)
    copias = max(1, min(int(request.GET.get("copias", "1") or 1), 8)) if request.GET.get("copias", "1").isdigit() else 1
    lista = [l for l in lotes.order_by("codigo") for _ in range(copias)]
    registrar(request, "exportar", detalle=f"Imprimió {len(lista)} etiquetas QR")
    return render(request, "lotes/etiquetas.html", {"titulo": "Etiquetas QR", "lotes": lista,
                                                     "todos": lotes_visibles(request.user).exclude(estado="retirado").order_by("-fecha_creacion")[:40],
                                                     "elegidos": elegidos, "copias": copias})
