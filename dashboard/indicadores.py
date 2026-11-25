"""
Indicadores y gráficas por área, calculados con consultas reales a la base de datos.

Reglas:
- No se inventan datos: si no hay registros, las series quedan vacías y la plantilla lo indica.
- Cada panel filtra los datos según el usuario: el administrador y el área de consulta ven todo;
  un operador ve lo que está a su cargo (los registros de los que es responsable).
"""
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from django.urls import reverse
from django.utils import timezone

from cosechas.models import Clasificacion, Cosecha, Recepcion
from cuentas import permissions as perm
from cuentas.models import Area, RegistroAuditoria
from lotes.models import Lote, RelacionLote
from parcelas.models import Labor, Parcela
from productores.models import Productor
from productos.models import Producto
from trazabilidad.models import EscaneoQR, EventoTrazabilidad, SimulacroRetiro
from transporte.models import Despacho, Transportista

SEMANAS = 8


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def todo(user):
    return perm.es_admin(user) or perm.area_de(user) == Area.REPORTES


def propios(user, qs, area):
    """Todos para administrador/consulta; los suyos si es su área; ninguno en otro caso."""
    if todo(user):
        return qs
    if perm.area_de(user) == area:
        return qs.filter(responsable=user)
    return qs.none()


def semanas(n=SEMANAS):
    hoy = timezone.localdate()
    inicio = hoy - timedelta(days=hoy.weekday()) - timedelta(weeks=n - 1)
    return [(inicio + timedelta(weeks=i), inicio + timedelta(weeks=i, days=6)) for i in range(n)]


def etiquetas_semanas(n=SEMANAS):
    return [f"{a:%d/%m}" for a, _ in semanas(n)]


def serie(qs, campo_fecha, campo_suma=None, fecha_hora=False, n=SEMANAS):
    filtro = f"{campo_fecha}__date__range" if fecha_hora else f"{campo_fecha}__range"
    res = []
    for a, b in semanas(n):
        sub = qs.filter(**{filtro: (a, b)})
        res.append(float(sub.aggregate(t=Sum(campo_suma))["t"] or 0) if campo_suma else sub.count())
    return res


def num(v):
    return float(v or 0)


def grafico(gid, titulo, tipo, etiquetas, series, unidad="", nota=""):
    """tipo: barra | barra_h | linea | dona | apilada. series: [(nombre, valores)]."""
    valores = [x for _, s in series for x in s]
    return {"id": gid, "titulo": titulo, "tipo": tipo, "etiquetas": [str(e) for e in etiquetas],
            "series": [{"nombre": n, "valores": [float(x) for x in s]} for n, s in series],
            "unidad": unidad, "nota": nota, "vacio": not valores or not any(valores)}


def agrupar(pares, top=8):
    """[(etiqueta, valor)] → las 'top' mayores."""
    c = Counter()
    for k, v in pares:
        c[k] += float(v or 0)
    comunes = c.most_common(top)
    return [k for k, _ in comunes], [round(v, 2) for _, v in comunes]


def kpi(valor, etiqueta, icono, color="verde", pie=""):
    return {"valor": valor, "etiqueta": etiqueta, "icono": icono, "color": color, "pie": pie}


def url(nombre, *args):
    return reverse(nombre, args=args)


# --------------------------------------------------------------------------
# Área 1. Panel general (indicadores de toda la cadena)
# --------------------------------------------------------------------------
def panel_general(user):
    hoy = timezone.localdate()
    mes = hoy.replace(day=1)
    cosechas = Cosecha.objects.all()
    kg_rec = num(Recepcion.objects.aggregate(t=Sum("peso_recibido"))["t"])
    kg_rch = num(Clasificacion.objects.filter(categoria="rechazo").aggregate(t=Sum("cantidad"))["t"])
    despachos = Despacho.objects.exclude(estado="cancelado")
    estados = dict(Lote.objects.values_list("estado").annotate(n=Count("id")).values_list("estado", "n"))
    por_estado_desp = dict(despachos.values_list("estado").annotate(n=Count("id")).values_list("estado", "n"))
    from lotes.inventario import alertas_inventario
    return {
        "kpis": [
            kpi(Productor.objects.filter(estado="activo").count(), "Productores registrados", "bi-people"),
            kpi(Parcela.objects.exclude(estado_cultivo__in=["descanso", "cosechado"]).count(), "Parcelas activas", "bi-geo-alt", "tierra"),
            kpi(cosechas.filter(fecha__gte=mes).count(), "Cosechas este mes", "bi-basket", "ambar"),
            kpi(f"{num(cosechas.aggregate(t=Sum('cantidad'))['t']):,.0f}".replace(",", " "), "Kg cosechados", "bi-flower1"),
            kpi(Lote.objects.filter(estado__in=["almacenamiento", "proceso"], cantidad_disponible__gt=0).count(), "Lotes en inventario", "bi-box-seam", "azul"),
            kpi(f"{kg_rec:,.0f}".replace(",", " "), "Kg recibidos en planta", "bi-box-arrow-in-down", "tierra"),
            kpi(f"{round(100 - kg_rch * 100 / kg_rec, 1) if kg_rec else 0} %", "Aceptación en recepción", "bi-check2-circle",
                pie=f"Rechazo {round(kg_rch * 100 / kg_rec, 1) if kg_rec else 0} %"),
            kpi(despachos.count(), "Despachos realizados", "bi-truck", "azul"),
            kpi(despachos.filter(estado__in=["programado", "transito"]).count(), "Entregas pendientes", "bi-hourglass-split", "ambar"),
            kpi(len(alertas_inventario(Lote.objects.all())), "Alertas de inventario o calidad", "bi-bell", "peligro"),
        ],
        "graficos": [
            grafico("g-prod", "Producción cosechada por semana", "linea", etiquetas_semanas(),
                    [("Kg cosechados", serie(cosechas, "fecha", "cantidad"))], "kg"),
            grafico("g-estados", "Lotes por estado", "dona", [dict(Lote.ESTADOS)[k] for k in estados], [("Lotes", list(estados.values()))]),
            grafico("g-acep", "Aceptación y rechazo en recepción", "dona", ["Aceptado", "Rechazado"],
                    [("Kg", [round(kg_rec - kg_rch, 1), round(kg_rch, 1)])], "kg"),
            grafico("g-desp", "Despachos y entregas", "barra", [dict(Despacho.ESTADOS)[k] for k in por_estado_desp],
                    [("Despachos", list(por_estado_desp.values()))]),
        ],
    }


# --------------------------------------------------------------------------
# Área 2. Abastecimiento y proveedores
# --------------------------------------------------------------------------
def panel_abastecimiento(user):
    area = perm.area_de(user)
    if todo(user):
        productores = Productor.objects.all()
    elif area == Area.PRODUCTORES:
        productores = Productor.objects.filter(responsable=user)
    else:  # parcelas: productores de sus parcelas
        productores = Productor.objects.filter(parcelas__responsable=user).distinct()
    recepciones = Recepcion.objects.filter(cosecha__productor__in=productores).select_related("cosecha__productor")
    kg = agrupar([(r.cosecha.productor.nombre, r.peso_recibido) for r in recepciones])
    n = agrupar([(r.cosecha.productor.nombre, 1) for r in recepciones])
    est = dict(productores.values_list("estado").annotate(n=Count("id")).values_list("estado", "n"))
    incompletos = [p for p in productores if p.datos_incompletos]
    return {
        "kpis": [kpi(productores.count(), "Productores", "bi-people"),
                 kpi(productores.filter(estado="activo").count(), "Activos", "bi-check-circle", "tierra"),
                 kpi(Parcela.objects.filter(productor__in=productores).count(), "Parcelas que abastecen", "bi-geo-alt", "azul"),
                 kpi(f"{num(recepciones.aggregate(t=Sum('peso_recibido'))['t']):,.0f}".replace(",", " "), "Kg recibidos de estos productores", "bi-box-arrow-in-down", "ambar")],
        "graficos": [
            grafico("g-kgprod", "Kilogramos recibidos por productor", "barra_h", kg[0], [("Kg recibidos", kg[1])], "kg"),
            grafico("g-estprod", "Productores por estado", "dona", [dict(Productor.ESTADOS)[k] for k in est], [("Productores", list(est.values()))]),
            grafico("g-recprod", "Recepciones por productor", "barra", n[0], [("Recepciones", n[1])]),
            grafico("g-evorec", "Evolución de la recepción", "linea", etiquetas_semanas(),
                    [("Kg recibidos", serie(recepciones, "fecha_hora", "peso_recibido", fecha_hora=True))], "kg"),
        ],
        "tabla": ("Procedencia de la materia prima (últimas recepciones)", ["Cosecha", "Productor", "Parcela", "Kg recibidos"],
                  [(r.get_absolute_url() if perm.consulta_area(user, Area.COSECHAS) else "",
                    [r.cosecha.codigo, r.cosecha.productor.nombre_publico if not perm.ve_datos_personales(user) else r.cosecha.productor.nombre,
                     r.cosecha.parcela.codigo, r.peso_recibido]) for r in recepciones.select_related("cosecha__parcela")[:8]]),
        "aviso": f"{len(incompletos)} productor(es) con datos de contacto por completar." if incompletos and perm.ve_datos_personales(user) else "",
    }


# --------------------------------------------------------------------------
# Área 3. Producción agrícola
# --------------------------------------------------------------------------
def panel_produccion(user):
    area = perm.area_de(user)
    if todo(user):
        parcelas, cosechas = Parcela.objects.all(), Cosecha.objects.all()
    elif area == Area.PARCELAS:
        parcelas = Parcela.objects.filter(responsable=user)
        cosechas = Cosecha.objects.filter(parcela__in=parcelas)
    else:
        cosechas = Cosecha.objects.filter(responsable=user)
        parcelas = Parcela.objects.filter(cosechas__in=cosechas).distinct()
    labores = Labor.objects.filter(parcela__in=parcelas)
    cultivo = agrupar([(c.producto.nombre, c.cantidad) for c in cosechas.select_related("producto")])
    parcela = agrupar([(c.parcela.codigo, c.cantidad) for c in cosechas.select_related("parcela")])
    insumos = labores.exclude(insumo="").select_related("parcela")[:8]
    return {
        "kpis": [kpi(parcelas.exclude(estado_cultivo__in=["descanso", "cosechado"]).count(), "Cultivos activos", "bi-flower2"),
                 kpi(f"{num(parcelas.filter(unidad_superficie='ha').aggregate(t=Sum('superficie'))['t']):.2f} ha", "Superficie cultivada", "bi-bounding-box", "tierra"),
                 kpi(cosechas.count(), "Cosechas registradas", "bi-basket", "ambar"),
                 kpi(labores.filter(fecha__gte=timezone.localdate() - timedelta(days=30)).count(), "Labores en 30 días", "bi-tools", "azul")],
        "graficos": [
            grafico("g-kgsem", "Kilogramos cosechados por semana", "linea", etiquetas_semanas(), [("Kg", serie(cosechas, "fecha", "cantidad"))], "kg"),
            grafico("g-cult", "Producción por cultivo", "dona", cultivo[0], [("Kg", cultivo[1])], "kg"),
            grafico("g-parc", "Producción por parcela", "barra", parcela[0], [("Kg", parcela[1])], "kg"),
            grafico("g-lab", "Labores agrícolas por semana", "barra", etiquetas_semanas(), [("Labores", serie(labores, "fecha"))]),
        ],
        "tabla": ("Insumos utilizados (últimas labores)", ["Fecha", "Parcela", "Labor", "Insumo", "Dosis"],
                  [(l.get_absolute_url() if perm.consulta_area(user, Area.PARCELAS) else "",
                    [l.fecha, l.parcela.codigo, l.get_tipo_display(), l.insumo, l.dosis]) for l in insumos]),
    }


# --------------------------------------------------------------------------
# Área 4. Recepción y clasificación
# --------------------------------------------------------------------------
def panel_recepcion(user):
    recepciones = propios(user, Recepcion.objects.all(), Area.COSECHAS)
    clases = Clasificacion.objects.filter(recepcion__in=recepciones)
    kg_rec = num(recepciones.aggregate(t=Sum("peso_recibido"))["t"])
    kg_rch = num(clases.filter(categoria="rechazo").aggregate(t=Sum("cantidad"))["t"])
    motivos = agrupar([((c.causa_rechazo or "Sin causa registrada").capitalize(), c.cantidad) for c in clases.filter(categoria="rechazo")])
    cat = dict(clases.values_list("categoria").annotate(t=Sum("cantidad")).values_list("categoria", "t"))
    orden = [k for k, _ in Clasificacion.CATEGORIAS if k in cat]
    sin_clasificar = [r for r in recepciones.select_related("cosecha") if r.kg_clasificados < r.peso_recibido]
    pendientes_recibir = propios(user, Cosecha.objects.filter(recepcion__isnull=True), Area.COSECHAS)
    return {
        "kpis": [kpi(f"{kg_rec:,.0f}".replace(",", " "), "Kg recibidos", "bi-box-arrow-in-down"),
                 kpi(f"{round(100 - kg_rch * 100 / kg_rec, 1) if kg_rec else 0} %", "Aceptados", "bi-check2-circle", "tierra"),
                 kpi(f"{round(kg_rch * 100 / kg_rec, 1) if kg_rec else 0} %", "Rechazados", "bi-x-octagon", "peligro"),
                 kpi(len(sin_clasificar) + pendientes_recibir.count(), "Pendientes de recibir o clasificar", "bi-hourglass-split", "ambar")],
        "graficos": [
            grafico("g-recsem", "Productos recibidos por semana", "barra", etiquetas_semanas(),
                    [("Kg recibidos", serie(recepciones, "fecha_hora", "peso_recibido", fecha_hora=True))], "kg"),
            grafico("g-acre", "Aceptados frente a rechazados", "dona", ["Aceptados", "Rechazados"], [("Kg", [round(kg_rec - kg_rch, 1), round(kg_rch, 1)])], "kg"),
            grafico("g-motivos", "Motivos de rechazo más frecuentes", "barra_h", motivos[0], [("Kg rechazados", motivos[1])], "kg"),
            grafico("g-cat", "Cantidad recibida por categoría", "barra", [dict(Clasificacion.CATEGORIAS)[k] for k in orden],
                    [("Kg", [num(cat[k]) for k in orden])], "kg"),
        ],
        "tabla": ("Recepciones pendientes de clasificar", ["Cosecha", "Recibido", "Clasificado"],
                  [(r.get_absolute_url(), [r.cosecha.codigo, f"{r.peso_recibido} kg", f"{r.kg_clasificados} kg"]) for r in sin_clasificar[:8]]),
    }


# --------------------------------------------------------------------------
# Área 5. Almacenamiento e inventarios
# --------------------------------------------------------------------------
def panel_almacenamiento(user):
    from lotes.inventario import alertas_inventario, existencias, lotes_visibles, movimientos
    lotes = lotes_visibles(user)
    ex = existencias(lotes)
    estados = dict(lotes.values_list("estado").annotate(n=Count("id")).values_list("estado", "n"))
    movs = movimientos(lotes)
    ent, sal = [], []
    for a, b in semanas():
        ent.append(sum(num(m["cantidad"]) for m in movs if m["tipo"] == "entrada" and m["unidad"] == "kg"
                       and a <= timezone.localtime(m["fecha"]).date() <= b))
        sal.append(sum(num(m["cantidad"]) for m in movs if m["tipo"] == "salida" and m["unidad"] == "kg"
                       and a <= timezone.localtime(m["fecha"]).date() <= b))
    hoy = timezone.localdate()
    rangos = [("0–7 días", 0, 7), ("8–15 días", 8, 15), ("16–30 días", 16, 30), ("Más de 30", 31, 10 ** 5)]
    activos = lotes.filter(estado__in=["almacenamiento", "proceso"], cantidad_disponible__gt=0)
    edades = [sum(1 for l in activos if a <= (hoy - l.fecha_creacion).days <= b) for _, a, b in rangos]
    bajos = [f for f in ex if f["bajo"]]
    return {
        "kpis": [kpi(activos.count(), "Lotes con existencias", "bi-box-seam"),
                 kpi(f"{sum(num(f['total']) for f in ex if f['producto'].unidad == 'kg'):,.0f}".replace(",", " ") + " kg", "Existencias en kg", "bi-boxes", "tierra"),
                 kpi(len(bajos), "Productos con stock bajo", "bi-exclamation-triangle", "peligro"),
                 kpi(sum(1 for l in activos if l.por_vencer), "Lotes por vencer", "bi-alarm", "ambar")],
        "graficos": [
            grafico("g-exist", "Existencias por producto", "barra", [str(f["producto"]) for f in ex],
                    [("Existencias", [num(f["total"]) for f in ex]), ("Stock mínimo", [num(f["minimo"]) for f in ex])]),
            grafico("g-lotest", "Lotes según su estado", "dona", [dict(Lote.ESTADOS)[k] for k in estados], [("Lotes", list(estados.values()))]),
            grafico("g-mov", "Entradas y salidas por semana (kg)", "barra", etiquetas_semanas(), [("Entradas", ent), ("Salidas", sal)], "kg"),
            grafico("g-edad", "Antigüedad de los lotes almacenados", "barra", [r[0] for r in rangos], [("Lotes", edades)]),
        ],
        "tabla": ("Alertas de stock y vencimiento", ["Alerta"], [(a["url"], [a["texto"]]) for a in alertas_inventario(lotes)[:8]]),
    }


# --------------------------------------------------------------------------
# Área 6. Transformación y empaque
# --------------------------------------------------------------------------
def panel_transformacion(user):
    if todo(user) or perm.area_de(user) == Area.TRAZABILIDAD:
        lotes = Lote.objects.all()
    else:
        lotes = Lote.objects.filter(responsable=user)
    rel = RelacionLote.objects.filter(Q(origen__in=lotes) | Q(resultado__in=lotes)).select_related("origen__producto", "resultado__producto").distinct()
    transf = rel.filter(tipo="transformacion")
    empaques = EventoTrazabilidad.objects.filter(tipo="empaque", lote__in=lotes)
    pres = agrupar([(f"{l.producto.nombre} ({l.producto.get_unidad_display().lower()})", 1) for l in lotes.select_related("producto")])
    procesados = lotes.exclude(proceso="")
    return {
        "kpis": [kpi(transf.count(), "Transformaciones registradas", "bi-recycle"),
                 kpi(f"{num(transf.aggregate(t=Sum('cantidad'))['t']):,.0f}".replace(",", " "), "Cantidad procesada (unidad de origen)", "bi-gear", "tierra"),
                 kpi(empaques.count(), "Eventos de empaque", "bi-box2", "ambar"),
                 kpi(procesados.count(), "Lotes con proceso aplicado", "bi-check2-square", "azul")],
        "graficos": [
            grafico("g-proc", "Cantidad procesada por semana", "barra", etiquetas_semanas(),
                    [("Cantidad", serie(transf, "fecha", "cantidad", fecha_hora=True))]),
            grafico("g-emp", "Empaques registrados por semana", "linea", etiquetas_semanas(),
                    [("Empaques", serie(empaques, "fecha_hora", fecha_hora=True))]),
            grafico("g-pres", "Lotes por producto y presentación", "dona", pres[0], [("Lotes", pres[1])]),
            grafico("g-lproc", "Lotes procesados por semana", "barra", etiquetas_semanas(), [("Lotes", serie(procesados, "fecha_creacion"))]),
        ],
        "tabla": ("Lote de origen y lote resultante", ["Fecha", "Tipo", "Origen", "Resultado", "Cantidad"],
                  [(r.resultado.get_absolute_url(), [timezone.localtime(r.fecha).date(), r.get_tipo_display(),
                                                     f"{r.origen.codigo} · {r.origen.producto.nombre}",
                                                     f"{r.resultado.codigo} · {r.resultado.producto.nombre}", f"{r.cantidad} {r.origen.unidad}"])
                   for r in rel[:8]]),
        "aviso": "Solo se registran procesos que realmente se aplicaron a cada producto." ,
    }


# --------------------------------------------------------------------------
# Área 7. Distribución y transporte
# --------------------------------------------------------------------------
def panel_distribucion(user):
    desp = propios(user, Despacho.objects.all(), Area.TRANSPORTE).select_related("transportista", "lote__producto")
    activos = desp.exclude(estado="cancelado")
    completadas = activos.filter(estado="entregado", entregado_a_tiempo=True).count()
    retrasadas = activos.filter(estado="entregado", entregado_a_tiempo=False).count()
    pendientes = activos.filter(estado__in=["programado", "transito"]).count()
    dest = agrupar([(d.destino, d.cantidad) for d in activos if d.lote.producto.unidad == "kg"])
    tr = agrupar([(str(d.transportista or "Sin transportista"), 1) for d in activos])
    entregados = activos.filter(estado="entregado").count()
    return {
        "kpis": [kpi(activos.count(), "Despachos", "bi-truck"),
                 kpi(pendientes, "Entregas pendientes", "bi-hourglass-split", "ambar"),
                 kpi(f"{round(100 * completadas / entregados) if entregados else 0} %", "Entregas a tiempo", "bi-stopwatch", "tierra"),
                 kpi(Transportista.objects.filter(activo=True).count(), "Transportistas activos", "bi-person-vcard", "azul")],
        "graficos": [
            grafico("g-dsem", "Despachos por semana", "barra", etiquetas_semanas(), [("Despachos", serie(activos, "salida", fecha_hora=True))]),
            grafico("g-dest", "Entregas completadas, pendientes y retrasadas", "dona", ["A tiempo", "Pendientes", "Con retraso"],
                    [("Despachos", [completadas, pendientes, retrasadas])]),
            grafico("g-kgdest", "Kilogramos distribuidos por destino", "barra_h", dest[0], [("Kg", dest[1])], "kg"),
            grafico("g-transp", "Despachos por transportista", "barra", tr[0], [("Despachos", tr[1])]),
        ],
        "tabla": ("Seguimiento de despachos activos", ["Código", "Lote", "Destino", "Salida", "Estado"],
                  [(d.get_absolute_url(), [d.codigo, d.lote.codigo, d.destino, d.salida, d.get_estado_display()])
                   for d in activos.filter(estado__in=["programado", "transito"])[:8]]),
    }


# --------------------------------------------------------------------------
# Área 8. Clientes y comercialización
# --------------------------------------------------------------------------
def panel_comercial(user):
    from comercial.models import Cliente, Venta
    ventas = propios(user, Venta.objects.all(), Area.COMERCIAL).select_related("cliente", "lote__producto")
    validas = ventas.exclude(estado="anulada")
    est = dict(ventas.values_list("estado").annotate(n=Count("id")).values_list("estado", "n"))
    kg_cli = agrupar([(v.cliente.nombre, v.cantidad) for v in validas.filter(estado="entregada") if v.lote.producto.unidad == "kg"])
    top = agrupar([(v.cliente.nombre, 1) for v in validas.filter(estado__in=["entregada", "despachada", "parcial"])])
    monto = [round(sum(num(v.total) for v in validas if a <= v.fecha <= b), 2) for a, b in semanas()]
    return {
        "kpis": [kpi(propios(user, Cliente.objects.all(), Area.COMERCIAL).filter(activo=True).count(), "Clientes activos", "bi-person-lines-fill"),
                 kpi(validas.count(), "Ventas registradas", "bi-receipt", "tierra"),
                 kpi(validas.filter(estado__in=["pendiente", "parcial"]).count(), "Pendientes de despacho", "bi-hourglass-split", "ambar"),
                 kpi("$ " + f"{sum(num(v.total) for v in validas):,.2f}".replace(",", " ").replace(".", ","), "Monto vendido", "bi-cash-coin", "azul")],
        "graficos": [
            grafico("g-vest", "Pedidos por estado", "dona", [dict(Venta.ESTADOS)[k] for k in est], [("Ventas", list(est.values()))]),
            grafico("g-vcli", "Kilogramos entregados por cliente", "barra_h", kg_cli[0], [("Kg", kg_cli[1])], "kg"),
            grafico("g-vtop", "Clientes con más entregas", "barra", top[0], [("Ventas entregadas o despachadas", top[1])]),
            grafico("g-vevo", "Evolución de las ventas por semana", "linea", etiquetas_semanas(),
                    [("Ventas", serie(validas, "fecha")), ("Monto ($)", monto)]),
        ],
        "tabla": ("Ventas pendientes de despacho", ["Venta", "Cliente", "Lote", "Por despachar"],
                  [(v.get_absolute_url(), [v.codigo, v.cliente.nombre, v.lote.codigo, f"{v.por_despachar} {v.unidad}"])
                   for v in validas.filter(estado__in=["pendiente", "parcial"])[:8]]),
    }


# --------------------------------------------------------------------------
# Área 9. Trazabilidad digital
# --------------------------------------------------------------------------
def panel_trazabilidad(user):
    eventos = EventoTrazabilidad.objects.all() if todo(user) or perm.area_de(user) == Area.TRAZABILIDAD \
        else EventoTrazabilidad.objects.filter(responsable=user)
    tipos = dict(eventos.values_list("tipo").annotate(n=Count("id")).values_list("tipo", "n"))
    orden = sorted(tipos, key=lambda k: -tipos[k])
    lotes = list(Lote.objects.select_related("producto"))
    etapas = Counter(l.get_estado_display() for l in lotes)
    completos = sum(1 for l in lotes if l.completitud == 100)
    sim = SimulacroRetiro.objects.all()
    prom = {m: num(sim.filter(metodo=m).aggregate(t=Sum("minutos"))["t"]) / max(sim.filter(metodo=m).count(), 1) for m, _ in SimulacroRetiro.METODOS}
    return {
        "kpis": [kpi(eventos.count(), "Eventos registrados", "bi-clock-history"),
                 kpi(f"{round(100 * completos / len(lotes)) if lotes else 0} %", "Lotes con trazabilidad completa", "bi-list-check", "tierra"),
                 kpi(EscaneoQR.objects.count(), "Consultas del QR", "bi-qr-code-scan", "azul"),
                 kpi(sim.count(), "Simulacros de retiro", "bi-stopwatch", "ambar")],
        "graficos": [
            grafico("g-evtipo", "Eventos de trazabilidad por tipo", "barra_h", [dict(EventoTrazabilidad.TIPOS)[k] for k in orden],
                    [("Eventos", [tipos[k] for k in orden])]),
            grafico("g-qr", "Lotes consultados con el QR por semana", "linea", etiquetas_semanas(),
                    [("Escaneos", serie(EscaneoQR.objects.all(), "fecha_hora", fecha_hora=True))]),
            grafico("g-etapa", "Lotes por etapa del proceso", "dona", list(etapas.keys()), [("Lotes", list(etapas.values()))]),
            grafico("g-sim", "Simulacros de retiro: tiempo promedio de rastreo", "barra", [n for _, n in SimulacroRetiro.METODOS],
                    [("Minutos", [round(prom[m], 1) for m, _ in SimulacroRetiro.METODOS])], "min",
                    nota="Compara la práctica actual con el aplicativo (experimento E1)."),
        ],
        "tabla": ("Lotes con trazabilidad incompleta", ["Lote", "Producto", "Completitud"],
                  [(l.get_absolute_url(), [l.codigo, l.producto.nombre, f"{l.completitud} %"]) for l in lotes
                   if l.completitud < 100 and l.estado != "retirado"][:8]),
    }


# --------------------------------------------------------------------------
# Área 10. Personal y seguridad (solo administrador)
# --------------------------------------------------------------------------
def panel_seguridad(user):
    User = get_user_model()
    activos = User.objects.filter(is_active=True).select_related("perfil__area")
    roles = Counter("Administrador general" if perm.es_admin(u) else (u.perfil.area.nombre if u.perfil.area else "Sin área") for u in activos)
    desde = timezone.now() - timedelta(days=30)
    acc = RegistroAuditoria.objects.filter(fecha__gte=desde).exclude(accion__in=["ingreso", "salida", "ingreso_fallido"])
    por_usuario = agrupar([(a.usuario_nombre or "—", 1) for a in acc], top=10)
    fallidos = RegistroAuditoria.objects.filter(accion="ingreso_fallido")
    return {
        "kpis": [kpi(activos.count(), "Usuarios activos", "bi-person-check"),
                 kpi(User.objects.filter(is_active=False).count(), "Cuentas desactivadas", "bi-person-x", "ambar"),
                 kpi(acc.count(), "Acciones en 30 días", "bi-activity", "azul"),
                 kpi(RegistroAuditoria.objects.filter(accion="acceso_denegado", fecha__gte=desde).count(), "Accesos denegados (30 días)", "bi-shield-x", "peligro")],
        "graficos": [
            grafico("g-roles", "Usuarios activos por rol", "barra_h", list(roles.keys()), [("Usuarios", list(roles.values()))]),
            grafico("g-actu", "Actividad por usuario (30 días)", "barra", por_usuario[0], [("Acciones", por_usuario[1])]),
            grafico("g-accsem", "Acciones registradas por semana", "linea", etiquetas_semanas(),
                    [("Acciones", serie(RegistroAuditoria.objects.exclude(accion__in=["ingreso", "salida"]), "fecha", fecha_hora=True))]),
            grafico("g-fallos", "Intentos de acceso fallidos por semana", "barra", etiquetas_semanas(),
                    [("Intentos", serie(fallidos, "fecha", fecha_hora=True))],
                    nota="Se registran con la señal de inicio de sesión fallido de Django."),
        ],
        "tabla": ("Últimos accesos denegados", ["Fecha", "Usuario", "Detalle"],
                  [("", [a.fecha, a.usuario_nombre, a.detalle[:80]]) for a in RegistroAuditoria.objects.filter(accion="acceso_denegado")[:8]]),
    }


# --------------------------------------------------------------------------
# Área 11. Reportes y análisis (con filtro de fechas)
# --------------------------------------------------------------------------
def meses(n=6):
    hoy = timezone.localdate().replace(day=1)
    res = []
    for i in range(n - 1, -1, -1):
        y, m = hoy.year, hoy.month - i
        while m <= 0:
            m += 12; y -= 1
        ini = hoy.replace(year=y, month=m, day=1)
        fin = (ini.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        res.append((ini, fin))
    return res


NOMBRES_MES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def panel_reportes(user, desde=None, hasta=None):
    cos, rec, desp = Cosecha.objects.all(), Recepcion.objects.all(), Despacho.objects.exclude(estado="cancelado")
    if desde:
        cos, rec, desp = cos.filter(fecha__gte=desde), rec.filter(fecha_hora__date__gte=desde), desp.filter(salida__date__gte=desde)
    if hasta:
        cos, rec, desp = cos.filter(fecha__lte=hasta), rec.filter(fecha_hora__date__lte=hasta), desp.filter(salida__date__lte=hasta)
    ms = meses()
    etiq = [f"{NOMBRES_MES[a.month - 1]} {a:%y}" for a, _ in ms]
    prod = [num(cos.filter(fecha__range=r).aggregate(t=Sum("cantidad"))["t"]) for r in ms]
    calidad = []
    for a, b in ms:
        r = num(rec.filter(fecha_hora__date__range=(a, b)).aggregate(t=Sum("peso_recibido"))["t"])
        x = num(Clasificacion.objects.filter(recepcion__in=rec.filter(fecha_hora__date__range=(a, b)), categoria="rechazo").aggregate(t=Sum("cantidad"))["t"])
        calidad.append(round(x * 100 / r, 1) if r else 0)
    cumplimiento = []
    for a, b in ms:
        e = desp.filter(estado="entregado", llegada__date__range=(a, b))
        cumplimiento.append(round(100 * e.filter(entregado_a_tiempo=True).count() / e.count()) if e.count() else 0)
    from lotes.inventario import existencias
    ex = existencias(Lote.objects.all())
    kg_rec = num(rec.aggregate(t=Sum("peso_recibido"))["t"])
    kg_rch = num(Clasificacion.objects.filter(recepcion__in=rec, categoria="rechazo").aggregate(t=Sum("cantidad"))["t"])
    ent = desp.filter(estado="entregado")
    return {
        "kpis": [kpi(f"{num(cos.aggregate(t=Sum('cantidad'))['t']):,.0f}".replace(",", " ") + " kg", "Producción del período", "bi-flower1"),
                 kpi(f"{round(kg_rch * 100 / kg_rec, 1) if kg_rec else 0} %", "Rechazo en recepción", "bi-x-octagon", "peligro"),
                 kpi(sum(1 for f in ex if f["bajo"]), "Productos bajo el mínimo", "bi-box-seam", "ambar"),
                 kpi(f"{round(100 * ent.filter(entregado_a_tiempo=True).count() / ent.count()) if ent.count() else 0} %", "Entregas a tiempo", "bi-stopwatch", "azul")],
        "graficos": [
            grafico("g-rprod", "Producción por mes", "barra", etiq, [("Kg cosechados", prod)], "kg"),
            grafico("g-rcal", "Indicador de calidad: % de rechazo por mes", "linea", etiq, [("% rechazo", calidad)], "%"),
            grafico("g-rinv", "Indicador de inventario: existencias frente al mínimo", "barra", [str(f["producto"]) for f in ex],
                    [("Existencias", [num(f["total"]) for f in ex]), ("Mínimo", [num(f["minimo"]) for f in ex])]),
            grafico("g-rdis", "Cumplimiento de entregas por mes", "linea", etiq, [("% a tiempo", cumplimiento)], "%"),
        ],
    }


# --------------------------------------------------------------------------
# Área 12. Administración del sistema (solo administrador)
# --------------------------------------------------------------------------
def panel_administracion(user):
    from django.conf import settings
    User = get_user_model()
    from comercial.models import Cliente, Venta
    modulos = [("Productores", Productor), ("Parcelas", Parcela), ("Labores", Labor), ("Productos", Producto),
               ("Cosechas", Cosecha), ("Recepciones", Recepcion), ("Clasificaciones", Clasificacion), ("Lotes", Lote),
               ("Despachos", Despacho), ("Clientes", Cliente), ("Ventas", Venta), ("Eventos", EventoTrazabilidad)]
    conf = [("Odoo (ERP)", bool(settings.ODOO_URL and settings.ODOO_DB and settings.ODOO_USER)),
            ("Asistente con IA externa", bool(getattr(settings, "IA_PROVEEDOR", "") not in ("", "ninguno"))),
            ("Aviso de cosecha por n8n", bool(settings.N8N_WEBHOOK_COSECHA)),
            ("Modo de depuración apagado", not settings.DEBUG),
            ("Clave secreta propia", settings.SECRET_KEY != "solo-para-desarrollo-cambie-esta-clave")]
    pendientes = sum(m.objects.filter(estado_revision="pendiente").count() for _, m in modulos if hasattr(m, "estado_revision"))
    return {
        "kpis": [kpi(sum(1 for _, m in modulos if m.objects.exists()), f"Módulos con datos (de {len(modulos)})", "bi-grid-3x3-gap"),
                 kpi(User.objects.filter(is_active=True).count(), "Usuarios activos", "bi-people", "tierra"),
                 kpi(sum(1 for _, ok in conf if ok), f"Configuraciones listas (de {len(conf)})", "bi-gear", "azul"),
                 kpi(pendientes, "Registros por revisar", "bi-hourglass-split", "ambar")],
        "graficos": [
            grafico("g-mod", "Registros por módulo", "barra_h", [n for n, _ in modulos], [("Registros", [m.objects.count() for _, m in modulos])]),
            grafico("g-adm-roles", "Usuarios y roles registrados", "dona", ["Administradores", "Operadores", "Sin área"],
                    [("Usuarios", [sum(1 for u in User.objects.filter(is_active=True) if perm.es_admin(u)),
                                   User.objects.filter(is_active=True, perfil__area__isnull=False, perfil__es_admin_general=False, is_superuser=False).count(),
                                   User.objects.filter(is_active=True, perfil__area__isnull=True, perfil__es_admin_general=False, is_superuser=False).count()])]),
        ],
        "configuracion": conf,
    }


PANELES = {
    "general": panel_general, "abastecimiento": panel_abastecimiento, "produccion": panel_produccion,
    "recepcion": panel_recepcion, "almacenamiento": panel_almacenamiento, "transformacion": panel_transformacion,
    "distribucion": panel_distribucion, "comercial": panel_comercial, "trazabilidad": panel_trazabilidad,
    "seguridad": panel_seguridad, "reportes": panel_reportes, "administracion": panel_administracion,
}


# --------------------------------------------------------------------------
# Alertas y notificaciones (según lo que cada usuario administra)
# --------------------------------------------------------------------------
def alertas(user):
    from lotes.inventario import alertas_inventario
    from comercial.models import Venta
    res = []
    admin = perm.es_admin(user)
    area = perm.area_de(user)
    hoy = timezone.localdate()

    def agregar(nivel, icono, texto, enlace, grupo):
        res.append({"nivel": nivel, "icono": icono, "texto": texto, "url": enlace, "grupo": grupo})

    if admin or area in (Area.LOTES, Area.REPORTES, Area.COMERCIAL):
        lotes = Lote.objects.all() if area != Area.LOTES else Lote.objects.filter(responsable=user)
        for a in alertas_inventario(lotes):
            agregar(a["nivel"], a["icono"], a["texto"], a["url"] if area != Area.COMERCIAL else "", "Inventario")
    if admin or area == Area.COSECHAS:
        cos = Cosecha.objects.filter(recepcion__isnull=True, fecha__lt=hoy)
        if not admin:
            cos = cos.filter(responsable=user)
        for c in cos[:10]:
            agregar("media", "bi-hourglass-split", f"Cosecha {c.codigo} sin recepción en planta desde el {c.fecha:%d/%m/%Y}", c.get_absolute_url(), "Recepción")
        recs = Recepcion.objects.all() if admin else Recepcion.objects.filter(responsable=user)
        for r in recs.select_related("cosecha"):
            if r.kg_clasificados < r.peso_recibido:
                agregar("media", "bi-funnel", f"Recepción de {r.cosecha.codigo}: faltan {r.peso_recibido - r.kg_clasificados} kg por clasificar", r.get_absolute_url(), "Calidad")
    if admin or area in (Area.COSECHAS, Area.PARCELAS):
        parcelas = Parcela.objects.all() if admin or area == Area.COSECHAS else Parcela.objects.filter(responsable=user)
        for p in parcelas:
            rec = num(Recepcion.objects.filter(cosecha__parcela=p).aggregate(t=Sum("peso_recibido"))["t"])
            rch = num(Clasificacion.objects.filter(recepcion__cosecha__parcela=p, categoria="rechazo").aggregate(t=Sum("cantidad"))["t"])
            if rec and rch * 100 / rec >= 10:
                agregar("alta", "bi-x-octagon", f"Rechazo alto en la parcela {p.codigo}: {str(round(rch * 100 / rec, 1)).replace('.', ',')} %",
                        p.get_absolute_url() if admin or area == Area.PARCELAS else "", "Calidad")
    if admin or area == Area.TRANSPORTE:
        d = Despacho.objects.filter(estado="transito", salida__lt=timezone.now() - timedelta(hours=24))
        if not admin:
            d = d.filter(responsable=user)
        for x in d:
            agregar("alta", "bi-truck", f"Despacho {x.codigo} lleva más de 24 h en tránsito hacia {x.destino}", x.get_absolute_url(), "Distribución")
    if admin or area in (Area.TRANSPORTE, Area.COMERCIAL):
        v = Venta.objects.filter(estado__in=["pendiente", "parcial"])
        if area == Area.COMERCIAL:
            v = v.filter(responsable=user)
        for x in v.select_related("cliente"):
            agregar("media", "bi-receipt", f"Venta {x.codigo} de {x.cliente.nombre} pendiente de despacho", x.get_absolute_url(), "Ventas")
    if admin or area == Area.TRAZABILIDAD:
        for l in Lote.objects.exclude(estado__in=["retirado"]).filter(fecha_creacion__lte=hoy - timedelta(days=3)):
            if l.completitud < 60:
                agregar("baja", "bi-diagram-3", f"Lote {l.codigo} con trazabilidad incompleta ({l.completitud} %)", l.get_absolute_url(), "Trazabilidad")
    if admin:
        from dashboard.views import MODELOS_REVISION
        n = sum(m.objects.filter(estado_revision="pendiente").count() for m in MODELOS_REVISION)
        if n:
            agregar("baja", "bi-patch-question", f"{n} registros pendientes de revisión del administrador", "/", "Administración")
        f = RegistroAuditoria.objects.filter(accion="ingreso_fallido", fecha__gte=timezone.now() - timedelta(hours=24)).count()
        if f >= 3:
            agregar("alta", "bi-shield-exclamation", f"{f} intentos de inicio de sesión fallidos en las últimas 24 h", "/cuentas/auditoria/?accion=ingreso_fallido", "Seguridad")
    orden = {"alta": 0, "media": 1, "baja": 2}
    res.sort(key=lambda a: orden[a["nivel"]])
    return res
