"""
Inventario (Área 5): existencias, movimientos y alertas calculados a partir de los lotes,
sus relaciones de procedencia y los despachos. No se guarda un saldo aparte: así no se descuadra.
"""
from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from cuentas import permissions as perm
from cuentas.models import Area

from .models import Lote, RelacionLote

ACTIVOS = ["almacenamiento", "proceso", "transporte"]


def lotes_visibles(user):
    """El inventario lo ve el administrador, el área de lotes (sus lotes) y el área de consulta."""
    return perm.queryset_lista(user, Lote.objects.select_related("producto"), Area.LOTES)


def existencias(lotes):
    """Existencias por producto: solo lotes que pueden venderse o despacharse."""
    from productos.models import Producto
    filas = []
    disponibles = lotes.filter(estado__in=ACTIVOS, cantidad_disponible__gt=0)
    totales = disponibles.values("producto").annotate(t=Sum("cantidad_disponible"))
    por_producto = {r["producto"]: r["t"] for r in totales}
    for p in Producto.objects.filter(pk__in=por_producto.keys()) | Producto.objects.filter(stock_minimo__gt=0, estado="activo"):
        total = por_producto.get(p.pk, Decimal("0"))
        filas.append({"producto": p, "total": total, "unidad": p.get_unidad_display(),
                      "lotes": disponibles.filter(producto=p).count(), "minimo": p.stock_minimo,
                      "bajo": p.stock_minimo > 0 and total < p.stock_minimo})
    filas.sort(key=lambda f: (not f["bajo"], f["producto"].nombre))
    return filas


def por_ubicacion(lotes):
    res = defaultdict(lambda: {"lotes": 0, "kg": Decimal("0")})
    for l in lotes.filter(estado__in=ACTIVOS, cantidad_disponible__gt=0):
        res[l.ubicacion]["lotes"] += 1
        if l.producto.unidad == "kg":
            res[l.ubicacion]["kg"] += l.cantidad_disponible
    return sorted(res.items())


def _dt(fecha, hora=12):
    return timezone.make_aware(datetime.combine(fecha, time(hora, 0)))


def movimientos(lotes, desde=None, hasta=None):
    """Entradas y salidas de cada lote, en orden cronológico inverso."""
    ids = set(lotes.values_list("id", flat=True))
    movs = []
    con_origen = set(RelacionLote.objects.filter(resultado_id__in=ids).values_list("resultado_id", flat=True))
    for l in lotes:
        origen = "Ingreso desde cosecha" if l.pk not in con_origen else "Ingreso por división, combinación o transformación"
        movs.append({"fecha": _dt(l.fecha_creacion, 14), "lote": l, "tipo": "entrada", "motivo": origen,
                     "cantidad": l.cantidad_inicial, "unidad": l.unidad, "doc": l.codigo, "url": l.get_absolute_url()})
    for r in RelacionLote.objects.filter(origen_id__in=ids).select_related("origen__producto", "resultado"):
        movs.append({"fecha": r.fecha, "lote": r.origen, "tipo": "salida", "motivo": f"{r.get_tipo_display()} hacia {r.resultado.codigo}",
                     "cantidad": r.cantidad, "unidad": r.origen.unidad, "doc": r.resultado.codigo, "url": r.resultado.get_absolute_url()})
    from transporte.models import Despacho
    for d in Despacho.objects.filter(lote_id__in=ids).select_related("lote__producto"):
        movs.append({"fecha": d.salida, "lote": d.lote, "tipo": "salida", "motivo": f"Despacho a {d.destino}",
                     "cantidad": d.cantidad, "unidad": d.lote.unidad, "doc": d.codigo, "url": d.get_absolute_url()})
        if d.estado == "cancelado":
            movs.append({"fecha": d.actualizado_en, "lote": d.lote, "tipo": "entrada", "motivo": f"Devolución por cancelación de {d.codigo}",
                         "cantidad": d.cantidad, "unidad": d.lote.unidad, "doc": d.codigo, "url": d.get_absolute_url()})
    if desde:
        movs = [m for m in movs if timezone.localtime(m["fecha"]).date() >= desde]
    if hasta:
        movs = [m for m in movs if timezone.localtime(m["fecha"]).date() <= hasta]
    movs.sort(key=lambda m: m["fecha"], reverse=True)
    return movs


def _n(v):
    v = Decimal(v or 0)
    return f"{v.normalize():f}" if v == v.to_integral() else f"{v:.2f}".replace(".", ",")


def alertas_inventario(lotes):
    hoy = timezone.localdate()
    res = []
    for f in existencias(lotes):
        if f["bajo"]:
            res.append({"nivel": "alta", "icono": "bi-box-seam", "texto": f"Stock bajo de {f['producto']}: {_n(f['total'])} de un mínimo de {_n(f['minimo'])}",
                        "url": "/lotes/inventario/"})
    activos = lotes.filter(estado__in=["almacenamiento", "proceso"], cantidad_disponible__gt=0, fecha_vencimiento__isnull=False)
    for l in activos.filter(fecha_vencimiento__lt=hoy):
        res.append({"nivel": "alta", "icono": "bi-calendar-x", "texto": f"Lote {l.codigo} vencido el {l.fecha_vencimiento:%d/%m/%Y} con {_n(l.cantidad_disponible)} {l.unidad}",
                    "url": l.get_absolute_url()})
    for l in activos.filter(fecha_vencimiento__gte=hoy, fecha_vencimiento__lte=hoy + timedelta(days=2)):
        res.append({"nivel": "media", "icono": "bi-alarm", "texto": f"Lote {l.codigo} vence el {l.fecha_vencimiento:%d/%m/%Y}",
                    "url": l.get_absolute_url()})
    for l in lotes.filter(estado="retirado", cantidad_disponible__gt=0):
        res.append({"nivel": "media", "icono": "bi-sign-stop", "texto": f"Lote retirado {l.codigo} aún tiene {_n(l.cantidad_disponible)} {l.unidad} en planta (inmovilizado)",
                    "url": l.get_absolute_url()})
    return res
