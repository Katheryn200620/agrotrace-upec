import random
from datetime import datetime
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from cuentas import permissions as perm
from cuentas.auditoria import registrar
from cuentas.models import Area
from lotes.models import Lote
from lotes.views import historia_lote

from . import contratos
from .forms import CorreccionForm, EventoForm, SimulacroForm
from .models import EscaneoQR, EventoTrazabilidad, SimulacroRetiro
from .servicios import registrar_evento


def _ve_todo(user):
    return perm.es_admin(user) or perm.area_de(user) in (Area.TRAZABILIDAD, Area.REPORTES)


# ---------------------------------------------------------------------------
# Historial de eventos (solo lectura; los eventos no se editan ni se borran)
# ---------------------------------------------------------------------------
@login_required
def evento_lista(request):
    qs = EventoTrazabilidad.objects.select_related("lote", "cosecha", "responsable").order_by("-fecha_hora", "-id")
    if not _ve_todo(request.user):
        qs = qs.filter(responsable=request.user)   # cada operador ve el historial de sus propias acciones
    q, tipo = request.GET.get("q", "").strip(), request.GET.get("tipo", "")
    if q:
        qs = qs.filter(lote__codigo__icontains=q) | qs.filter(cosecha__codigo__icontains=q) | qs.filter(descripcion__icontains=q)
    if tipo:
        qs = qs.filter(tipo=tipo)
    pagina = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "trazabilidad/evento_lista.html", {
        "pagina": pagina, "q": q, "tipo": tipo, "tipos": EventoTrazabilidad.TIPOS, "titulo": "Historial de trazabilidad",
        "puede_registrar": perm.puede(request.user, "crear", Area.TRAZABILIDAD),
    })


@login_required
def evento_detalle(request, pk):
    ev = get_object_or_404(EventoTrazabilidad.objects.select_related("lote", "cosecha", "responsable"), pk=pk)
    perm.exigir(_ve_todo(request.user) or ev.responsable_id == request.user.id
                or (ev.lote and perm.consulta_area(request.user, Area.LOTES)), request, f"Intento de ver el evento #{pk}")
    puede_corregir = ev.tipo != "correccion" and (perm.es_admin(request.user) or (
        perm.puede(request.user, "crear", Area.TRAZABILIDAD) and ev.responsable_id == request.user.id))
    return render(request, "trazabilidad/evento_detalle.html", {
        "ev": ev, "correcciones": ev.correcciones.all(), "puede_corregir": puede_corregir,
        "form": CorreccionForm(), "titulo": "Evento de trazabilidad"})


@login_required
def evento_crear(request):
    perm.exigir(perm.puede(request.user, "crear", Area.TRAZABILIDAD), request, "Intento de registrar un evento sin permiso")
    form = EventoForm(request.POST or None, initial={"lote": request.GET.get("lote")})
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        ev = registrar_evento(d["tipo"], request.user, d["descripcion"], lugar=d["lugar"], lote=d["lote"],
                              cantidad=d["cantidad"], unidad=d["lote"].unidad if d["cantidad"] else "",
                              observaciones=d["observaciones"], fecha_hora=d["fecha_hora"], origen="manual")
        registrar(request, "evento", ev, detalle=f"{ev.get_tipo_display()} del lote {d['lote'].codigo}")
        messages.success(request, "Evento registrado en el historial del lote.")
        return redirect("lotes:lote_detalle", pk=d["lote"].pk)
    return render(request, "comun/formulario.html", {
        "form": form, "titulo": "Registrar evento de trazabilidad", "titulo_singular": "Evento",
        "ayuda": "Los eventos no se pueden editar ni borrar. Si se equivoca, registre una corrección desde el evento.",
        "volver": "/trazabilidad/"})


@login_required
@require_POST
def evento_corregir(request, pk):
    ev = get_object_or_404(EventoTrazabilidad, pk=pk)
    perm.exigir(perm.es_admin(request.user) or (perm.puede(request.user, "crear", Area.TRAZABILIDAD)
                                                and ev.responsable_id == request.user.id),
                request, f"Intento de corregir el evento #{pk} de otro operador")
    form = CorreccionForm(request.POST)
    if form.is_valid():
        c = registrar_evento("correccion", request.user, form.cleaned_data["descripcion"], lugar=ev.lugar,
                             lote=ev.lote, cosecha=ev.cosecha, parcela=ev.parcela,
                             observaciones=form.cleaned_data["observaciones"], corrige=ev, origen="manual")
        registrar(request, "evento", c, detalle=f"Corrección del evento #{ev.pk}", justificacion=form.cleaned_data["observaciones"][:250],
                  cambios={"evento_original": {"descripcion": ev.descripcion, "fecha_hora": ev.fecha_hora.isoformat()}})
        messages.success(request, "Corrección registrada. El evento original se conserva en el historial.")
    return redirect("trazabilidad:evento_detalle", pk=pk)


# ---------------------------------------------------------------------------
# Consulta pública de procedencia (QR GS1 Digital Link). No muestra datos personales.
# ---------------------------------------------------------------------------
EVENTOS_PUBLICOS = {"cultivo", "cosecha", "recepcion", "clasificacion", "creacion_lote", "empaque", "almacenamiento",
                    "transformacion", "division", "combinacion", "despacho", "transporte", "recepcion_destino", "retiro"}


def _ficha_publica(request, lote):
    if not lote.publicado:
        raise Http404
    EscaneoQR.objects.create(lote=lote, agente_usuario=request.META.get("HTTP_USER_AGENT", "")[:255])
    eventos = [e for e in historia_lote(lote) if e.tipo in EVENTOS_PUBLICOS and not e.corregido]
    cosechas = list(lote.todas_las_cosechas())
    despachos = lote.despachos.exclude(estado="cancelado")
    return render(request, "trazabilidad/publica.html", {
        "lote": lote, "eventos": eventos, "cosechas": cosechas,
        "fecha_cosecha": min((c.fecha for c in cosechas), default=None),
        "parcelas": lote.parcelas(), "productores": lote.productores(), "despachos": despachos,
        "ultima": max((e.fecha_hora for e in eventos), default=lote.actualizado_en),
    })


def procedencia_gs1(request, gtin, codigo):
    lote = get_object_or_404(Lote.objects.select_related("producto"), producto__gtin=gtin, codigo=codigo)
    return _ficha_publica(request, lote)


def consulta(request):
    codigo = request.GET.get("codigo", "").strip().upper()
    if codigo:
        lote = Lote.objects.filter(codigo__iexact=codigo, publicado=True).first()
        if lote:
            return redirect("procedencia_gs1", gtin=lote.producto.gtin, codigo=lote.codigo)
        messages.warning(request, f"No se encontró un lote publicado con el código «{codigo}».")
    return render(request, "trazabilidad/consulta.html", {"codigo": codigo})


# ---------------------------------------------------------------------------
# Experimento E1: simulacro de retiro
# ---------------------------------------------------------------------------
@login_required
def simulacros(request):
    perm.exigir(_ve_todo(request.user), request, "Acceso a simulacros")
    datos = list(SimulacroRetiro.objects.select_related("lote", "responsable"))
    resumen = []
    for metodo, nombre in SimulacroRetiro.METODOS:
        g = [s for s in datos if s.metodo == metodo]
        if g:
            resumen.append({"metodo": nombre, "n": len(g), "minutos": round(sum(s.minutos for s in g) / len(g), 2),
                            "completitud": round(sum(s.completitud_pct for s in g) / len(g))})
    return render(request, "trazabilidad/simulacros.html", {
        "simulacros": datos[:100], "resumen": resumen, "activo": request.session.get("simulacro"),
        "puede": perm.puede(request.user, "crear", Area.TRAZABILIDAD), "titulo": "Simulacro de retiro (E1)"})


@login_required
def simulacro_registrar(request):
    perm.exigir(perm.puede(request.user, "crear", Area.TRAZABILIDAD), request, "Registro de simulacro sin permiso")
    form = SimulacroForm(request.POST or None, initial={"metodo": "actual"})
    if request.method == "POST" and form.is_valid():
        s = form.save(commit=False)
        s.responsable = request.user
        s.save()
        registrar(request, "crear", s, detalle="Simulacro de retiro (práctica actual)")
        messages.success(request, "Simulacro registrado.")
        return redirect("trazabilidad:simulacros")
    return render(request, "comun/formulario.html", {
        "form": form, "titulo": "Registrar simulacro (práctica actual)", "titulo_singular": "Simulacro",
        "ayuda": "Cronometre cuánto tarda el personal, sin el aplicativo, en decir de qué parcela vino el lote y a qué "
                 "clientes fue. Anote el % de eslabones que tenían registro escrito.",
        "volver": "/trazabilidad/simulacros/"})


@login_required
@require_POST
def simulacro_iniciar(request):
    perm.exigir(perm.puede(request.user, "crear", Area.TRAZABILIDAD), request, "Inicio de simulacro sin permiso")
    ids = list(Lote.objects.values_list("pk", flat=True))
    if not ids:
        messages.error(request, "No hay lotes registrados.")
        return redirect("trazabilidad:simulacros")
    lote = Lote.objects.get(pk=random.choice(ids))
    request.session["simulacro"] = {"lote": lote.pk, "codigo": lote.codigo, "inicio": timezone.now().isoformat()}
    messages.info(request, f"Simulacro iniciado. Rastree el lote {lote.codigo} con el buscador superior y, cuando tenga "
                           "sus parcelas de origen y destinos, pulse «Terminar simulacro».")
    return redirect("inicio")


@login_required
@require_POST
def simulacro_terminar(request):
    sim = request.session.pop("simulacro", None)
    if not sim:
        return redirect("trazabilidad:simulacros")
    lote = get_object_or_404(Lote, pk=sim["lote"])
    minutos = Decimal(str(round((timezone.now() - datetime.fromisoformat(sim["inicio"])).total_seconds() / 60, 2)))
    SimulacroRetiro.objects.create(lote=lote, metodo="aplicativo", minutos=max(minutos, Decimal("0.01")),
                                   completitud_pct=lote.completitud, responsable=request.user,
                                   observaciones="Registrado automáticamente por el aplicativo")
    messages.success(request, f"Simulacro terminado: {str(minutos).replace('.', ',')} min y {lote.completitud} % de eventos completos.")
    return redirect("trazabilidad:simulacros")


# ---------------------------------------------------------------------------
# Datos en JSON para otros sistemas (solo lectura y con control de acceso)
# ---------------------------------------------------------------------------
@login_required
def lote_epcis(request, pk):
    lote = get_object_or_404(Lote, pk=pk)
    perm.exigir(perm.consulta_area(request.user, Area.LOTES) or lote.responsable_id == request.user.id, request,
                f"Intento de exportar EPCIS del lote {lote.codigo}")
    return JsonResponse({"@context": ["https://ref.gs1.org/standards/epcis/2.0.0/epcis-context.jsonld"],
                         "type": "EPCISDocument", "schemaVersion": "2.0",
                         "epcisBody": {"eventList": [e.como_epcis() for e in historia_lote(lote)]}},
                        json_dumps_params={"ensure_ascii": False, "indent": 2})


@login_required
def contrato_cosecha(request, pk):
    from cosechas.models import Cosecha
    c = get_object_or_404(Cosecha, pk=pk)
    perm.exigir(perm.consulta_area(request.user, Area.COSECHAS), request, "Contrato de cosecha sin permiso")
    return JsonResponse(contratos.cosecha_a_planta(c), json_dumps_params={"ensure_ascii": False, "indent": 2})


@login_required
def contrato_despacho(request, pk):
    from transporte.models import Despacho
    d = get_object_or_404(Despacho, pk=pk)
    perm.exigir(perm.consulta_area(request.user, Area.TRANSPORTE) or d.responsable_id == request.user.id, request,
                "Contrato de despacho sin permiso")
    return JsonResponse(contratos.despacho_a_cedi(d), json_dumps_params={"ensure_ascii": False, "indent": 2})
