"""Reportes con filtros y exportación. Solo administrador general y área de reportes (consulta sin edición)."""
import csv

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from cosechas.models import Clasificacion, Cosecha, Recepcion
from cuentas import permissions as perm
from cuentas.auditoria import registrar
from cuentas.models import Area
from lotes.models import Lote
from parcelas.models import Labor, Parcela
from productores.models import Productor
from productos.models import Producto
from trazabilidad.models import EscaneoQR, EventoTrazabilidad, SimulacroRetiro
from transporte.models import Despacho


def _acceso(request):
    perm.exigir(perm.es_admin(request.user) or perm.area_de(request.user) == Area.REPORTES, request, "Acceso a reportes")


def _lotes_filtrados(g):
    qs = Lote.objects.select_related("producto").prefetch_related("cosechas__parcela", "cosechas__productor", "despachos")
    if g.get("productor"):
        qs = qs.filter(Q(cosechas__productor_id=g["productor"]) | Q(origenes__origen__cosechas__productor_id=g["productor"]))
    if g.get("parcela"):
        qs = qs.filter(Q(cosechas__parcela_id=g["parcela"]) | Q(origenes__origen__cosechas__parcela_id=g["parcela"]))
    if g.get("producto"):
        qs = qs.filter(producto_id=g["producto"])
    if g.get("desde"):
        qs = qs.filter(cosechas__fecha__gte=g["desde"])
    if g.get("hasta"):
        qs = qs.filter(cosechas__fecha__lte=g["hasta"])
    if g.get("lote"):
        qs = qs.filter(codigo__icontains=g["lote"])
    if g.get("ubicacion"):
        qs = qs.filter(Q(cosechas__productor__canton__icontains=g["ubicacion"]) |
                       Q(cosechas__productor__parroquia__icontains=g["ubicacion"]))
    if g.get("estado"):
        qs = qs.filter(estado=g["estado"])
    if g.get("destino"):
        qs = qs.filter(despachos__tipo_destino=g["destino"])
    return qs.distinct().order_by("-fecha_creacion", "-id")


def _fila(l, ver_privado):
    cos = list(l.todas_las_cosechas())
    prod = l.productores()
    return [l.codigo, l.producto.nombre, ", ".join((p.nombre if ver_privado else p.nombre_publico) for p in prod),
            ", ".join(sorted({c.parcela.codigo for c in cos})), ", ".join(sorted({p.ubicacion for p in prod})),
            min((c.fecha for c in cos), default=""), l.cantidad_inicial, l.cantidad_disponible, l.unidad,
            l.get_estado_display(), "; ".join(f"{d.destino} ({d.get_estado_display().lower()})" for d in l.despachos.all()),
            f"{l.completitud} %"]


ENCABEZADO = ["Lote", "Producto", "Productor", "Parcelas", "Ubicación", "Fecha de cosecha", "Cantidad inicial",
              "Disponible", "Unidad", "Estado", "Movimientos y destinos", "Trazabilidad"]


@login_required
def inicio(request):
    _acceso(request)
    g = {k: request.GET.get(k, "").strip() for k in ("productor", "parcela", "producto", "desde", "hasta", "lote",
                                                      "ubicacion", "estado", "destino")}
    qs = _lotes_filtrados(g)
    ver_privado = perm.ve_datos_personales(request.user)
    if request.GET.get("exportar") == "csv":
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="reporte_procedencia_{timezone.localdate():%Y%m%d}.csv"'
        resp.write("﻿")
        w = csv.writer(resp, delimiter=";")
        w.writerow(ENCABEZADO)
        filas = [_fila(l, ver_privado) for l in qs]
        w.writerows(filas)
        registrar(request, "exportar", detalle=f"Reporte de procedencia: {len(filas)} lotes. Filtros: {g}")
        return resp
    pagina = Paginator(qs, 12).get_page(request.GET.get("page"))
    params = request.GET.copy(); params.pop("page", None)
    simul = list(SimulacroRetiro.objects.all())
    e1 = {}
    for m, nombre in SimulacroRetiro.METODOS:
        grupo = [s for s in simul if s.metodo == m]
        if grupo:
            e1[nombre] = (round(sum(s.minutos for s in grupo) / len(grupo), 2), round(sum(s.completitud_pct for s in grupo) / len(grupo)), len(grupo))
    return render(request, "reportes/inicio.html", {
        "titulo": "Reportes de procedencia", "g": g, "pagina": pagina, "filas": [_fila(l, ver_privado) + [l] for l in pagina],
        "encabezado": ENCABEZADO, "params": params.urlencode(), "total": qs.count(),
        "productores": Productor.objects.all(), "parcelas": Parcela.objects.all(), "productos": Producto.objects.all(),
        "estados": Lote.ESTADOS, "destinos": Despacho.DESTINOS, "datasets": [(k, v[0]) for k, v in DATASETS.items()],
        "e1": e1, "escaneos": EscaneoQR.objects.count(),
    })


def _privado(ver, valor):
    return valor if ver else "(reservado)"


DATASETS = {
    "productores": ("Productores", lambda v: (["codigo", "nombre", "tipo", "cedula_ruc", "provincia", "canton", "parroquia", "telefono", "correo", "estado"],
                    [[p.codigo, p.nombre if v else p.nombre_publico, p.tipo, _privado(v, p.identificacion), p.provincia, p.canton,
                      p.parroquia, _privado(v, p.telefono), _privado(v, p.correo), p.estado] for p in Productor.objects.all()])),
    "parcelas": ("Parcelas", lambda v: (["codigo", "nombre", "productor", "cultivo", "superficie", "unidad", "latitud", "longitud", "gln", "estado"],
                 [[p.codigo, p.nombre, p.productor.codigo, p.cultivo.nombre, p.superficie, p.unidad_superficie, p.latitud,
                   p.longitud, p.gln, p.estado_cultivo] for p in Parcela.objects.select_related("productor", "cultivo")])),
    "labores": ("Labores agrícolas", lambda v: (["parcela", "tipo", "fecha", "insumo", "dosis"],
                [[l.parcela.codigo, l.tipo, l.fecha, l.insumo, l.dosis] for l in Labor.objects.select_related("parcela")])),
    "cosechas": ("Cosechas", lambda v: (["codigo", "parcela", "productor", "producto", "fecha", "cantidad", "unidad"],
                 [[c.codigo, c.parcela.codigo, c.productor.codigo, c.producto.nombre, c.fecha, c.cantidad, c.unidad]
                  for c in Cosecha.objects.select_related("parcela", "productor", "producto")])),
    "recepciones": ("Recepciones", lambda v: (["cosecha", "parcela", "fecha_hora", "kg_cosechados", "kg_recibidos", "temperatura_c", "minutos", "kg_rechazo", "pct_rechazo"],
                    [[r.cosecha.codigo, r.cosecha.parcela.codigo, timezone.localtime(r.fecha_hora).isoformat(), r.cosecha.cantidad,
                      r.peso_recibido, r.temperatura, r.minutos_recepcion, r.kg_rechazo, r.porcentaje_rechazo]
                     for r in Recepcion.objects.select_related("cosecha__parcela")])),
    "clasificaciones": ("Clasificaciones (dataset de imágenes, E2)", lambda v: (["cosecha", "parcela", "categoria", "kg", "metodo", "confianza", "causa_rechazo", "foto"],
                        [[c.recepcion.cosecha.codigo, c.recepcion.cosecha.parcela.codigo, c.categoria, c.cantidad, c.metodo,
                          c.confianza_modelo, c.causa_rechazo, c.foto.url if c.foto else ""]
                         for c in Clasificacion.objects.select_related("recepcion__cosecha__parcela")])),
    "lotes": ("Lotes", lambda v: (["codigo", "producto", "gtin", "categoria", "fecha_creacion", "vence", "inicial", "disponible", "estado", "parcelas", "completitud_pct", "escaneos"],
              [[l.codigo, l.producto.nombre, l.producto.gtin, l.categoria, l.fecha_creacion, l.fecha_vencimiento, l.cantidad_inicial,
                l.cantidad_disponible, l.estado, " ".join(p.codigo for p in l.parcelas()), l.completitud, l.escaneos.count()]
               for l in Lote.objects.select_related("producto")])),
    "eventos": ("Eventos de trazabilidad (EPCIS)", lambda v: (["fecha_hora", "tipo", "biz_step", "lote", "cosecha", "lugar", "cantidad", "descripcion", "origen", "corrige"],
                [[timezone.localtime(e.fecha_hora).isoformat(), e.tipo, e.biz_step, e.lote.codigo if e.lote else "",
                  e.cosecha.codigo if e.cosecha else "", e.lugar, e.cantidad, e.descripcion, e.origen, e.corrige_id or ""]
                 for e in EventoTrazabilidad.objects.select_related("lote", "cosecha")])),
    "despachos": ("Despachos y destinos", lambda v: (["codigo", "lote", "cantidad", "salida", "llegada", "tipo_destino", "destino", "estado", "a_tiempo", "km"],
                  [[d.codigo, d.lote.codigo, d.cantidad, timezone.localtime(d.salida).isoformat(),
                    timezone.localtime(d.llegada).isoformat() if d.llegada else "", d.tipo_destino, d.destino, d.estado,
                    d.entregado_a_tiempo, d.km_recorridos] for d in Despacho.objects.select_related("lote")])),
    "escaneos": ("Escaneos del QR (E3)", lambda v: (["fecha_hora", "lote", "producto"],
                 [[timezone.localtime(e.fecha_hora).isoformat(), e.lote.codigo, e.lote.producto.nombre]
                  for e in EscaneoQR.objects.select_related("lote__producto")])),
    "simulacros": ("Simulacros de retiro (E1)", lambda v: (["fecha", "lote", "metodo", "minutos", "completitud_pct"],
                   [[timezone.localtime(s.fecha).isoformat(), s.lote.codigo, s.metodo, s.minutos, s.completitud_pct]
                    for s in SimulacroRetiro.objects.select_related("lote")])),
}


@login_required
def dataset(request, nombre):
    _acceso(request)
    if nombre not in DATASETS:
        raise Http404
    titulo, fn = DATASETS[nombre]
    encabezado, filas = fn(perm.ve_datos_personales(request.user))
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{nombre}.csv"'
    resp.write("﻿")
    w = csv.writer(resp, delimiter=";")
    w.writerow(encabezado)
    w.writerows([["" if x is None else x for x in f] for f in filas])
    registrar(request, "exportar", detalle=f"Dataset {titulo}: {len(filas)} filas")
    return resp
