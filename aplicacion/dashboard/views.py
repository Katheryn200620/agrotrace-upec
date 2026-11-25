"""Paneles: el administrador general ve la supervisión global y cada operador su área de trabajo."""
import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from cosechas.models import Clasificacion, Cosecha, Recepcion
from cuentas import permissions as perm
from cuentas.models import Area, RegistroAuditoria
from lotes.models import Lote
from parcelas.models import Labor, Parcela
from productores.models import Productor
from productos.models import Producto
from trazabilidad.models import EscaneoQR, EventoTrazabilidad, SimulacroRetiro
from transporte.models import Despacho, Transportista

MODELOS_REVISION = [Productor, Parcela, Labor, Producto, Cosecha, Recepcion, Clasificacion, Lote, Despacho, Transportista]


def _semanas(qs_cosechas, n=8):
    hoy = timezone.localdate()
    inicio = hoy - timedelta(days=hoy.weekday()) - timedelta(weeks=n - 1)
    etiquetas, valores = [], []
    for i in range(n):
        a = inicio + timedelta(weeks=i)
        b = a + timedelta(days=6)
        etiquetas.append(f"{a:%d/%m}")
        valores.append(float(qs_cosechas.filter(fecha__range=(a, b)).aggregate(t=Sum("cantidad"))["t"] or 0))
    return etiquetas, valores


def _serie(qs, campo, n=8, fecha_hora=False):
    """Cuántos registros hubo cada semana (para los minigráficos de las tarjetas)."""
    hoy = timezone.localdate()
    inicio = hoy - timedelta(days=hoy.weekday()) - timedelta(weeks=n - 1)
    filtro = f"{campo}__date__range" if fecha_hora else f"{campo}__range"
    return [qs.filter(**{filtro: (inicio + timedelta(weeks=i), inicio + timedelta(weeks=i, days=6))}).count() for i in range(n)]


def saludo():
    h = timezone.localtime().hour
    return "Buenos días" if h < 12 else ("Buenas tardes" if h < 19 else "Buenas noches")


def _rechazo_por_parcela(parcelas):
    filas = []
    for p in parcelas:
        rec = Recepcion.objects.filter(cosecha__parcela=p).aggregate(t=Sum("peso_recibido"))["t"] or 0
        if rec:
            rch = Clasificacion.objects.filter(recepcion__cosecha__parcela=p, categoria="rechazo").aggregate(t=Sum("cantidad"))["t"] or 0
            filas.append({"codigo": p.codigo, "cultivo": p.cultivo.nombre, "pct": round(float(rch) * 100 / float(rec), 1),
                          "rechazo": float(rch), "recibido": float(rec)})
    return filas


@login_required
def portada(request):
    """Página de Inicio: catálogo visual con los productos registrados (sin datos inventados)."""
    from django.db.models import Count, Max
    activos = ["almacenamiento", "proceso", "transporte"]
    productos = Producto.objects.annotate(
        existencias=Sum("lotes__cantidad_disponible", filter=Q(lotes__estado__in=activos, lotes__cantidad_disponible__gt=0)),
        n_lotes=Count("lotes", distinct=True),
        ultimo_lote=Max("lotes__fecha_creacion", filter=Q(lotes__publicado=True) & ~Q(lotes__estado="retirado")),
    ).order_by("estado", "nombre")
    lista = list(productos)
    for p in lista:   # último lote publicado, para enlazar a su consulta pública
        p.lote_publico = p.lotes.filter(publicado=True).exclude(estado="retirado").order_by("-fecha_creacion", "-id").first() if p.ultimo_lote else None
    # Etapas de la cadena (tarjetas grandes). Cada una abre el primer panel que el usuario puede ver.
    from django.urls import reverse
    from . import areas as areas_def
    ETAPAS = [("campo", "Agricultor y proveedor", "Productores, parcelas y cosechas",
               "Conozca el origen: productores, parcelas, labores agrícolas y el registro de cada cosecha.",
               "Productores · Parcelas · Cosechas", ["abastecimiento", "produccion"]),
              ("planta", "Recepción y transformación", "Pesaje, calidad y empaque",
               "Reciba y pese lo cosechado, clasifique por calidad y registre procesos y empaque.",
               "Recepción · Calidad · Empaque", ["recepcion", "transformacion"]),
              ("almacen", "Almacén", "Existencias sin perder la trazabilidad",
               "Controle lotes, entradas, salidas, ubicaciones y existencias de cada lote registrado.",
               "Lotes · Inventario · Etiquetas QR", ["almacenamiento"]),
              ("distribucion", "Distribución", "Del almacén al destino",
               "Prepare despachos, asigne transportistas y siga cada entrega hasta su destino.",
               "Despachos · Transporte · Entregas", ["distribucion"]),
              ("clientes", "Clientes y tienda", "El producto llega a sus clientes",
               "Registre clientes mayoristas y minoristas, ventas y la consulta del QR por el consumidor.",
               "Clientes · Ventas · QR", ["comercial", "trazabilidad"])]
    etapas = []
    for n, (clave, nombre, sub, desc, chips, claves) in enumerate(ETAPAS, 1):
        destino = next((reverse(f"dashboard:area_{c}") for c in claves if areas_def.puede_ver_panel(request.user, c)), None)
        etapas.append({"n": n, "clave": clave, "nombre": nombre, "sub": sub, "desc": desc, "chips": chips, "url": destino,
                       "escena": f"comun/escenas/{clave}.html",
                       "foto": f"img/areas/{clave}.jpg" if finders.find(f"img/areas/{clave}.jpg") else None})
    from comercial.models import Venta
    from transporte.models import Despacho
    u = request.user
    ver_lotes = perm.consulta_area(u, Area.LOTES)
    ver_pedidos = perm.es_admin(u) or perm.area_de(u) in (Area.COMERCIAL, Area.TRANSPORTE, Area.REPORTES)
    kg = Lote.objects.filter(estado__in=activos, cantidad_disponible__gt=0, producto__unidad="kg").aggregate(t=Sum("cantidad_disponible"))["t"] or 0
    usadas = {p.categoria for p in lista}
    categorias = [(c, n, sum(1 for p in lista if p.categoria == c)) for c, n in Producto.CATEGORIAS if c in usadas]
    return render(request, "dashboard/portada.html", {
        "titulo": "Inicio", "saludo": saludo(), "hoy": timezone.localdate(), "productos": lista, "categorias": categorias,
        "q": request.GET.get("q", "").strip(), "categoria": request.GET.get("categoria", ""),
        "total_activos": sum(1 for p in lista if p.estado == "activo"),
        "con_foto": sum(1 for p in lista if p.foto),
        "con_existencias": sum(1 for p in lista if p.existencias),
        "ver_ficha": perm.consulta_area(request.user, Area.PRODUCTOS),
        "puede_agregar": perm.puede(request.user, "crear", Area.PRODUCTOS),
        "foto_portada": "img/portada.jpg" if finders.find("img/portada.jpg") else None,
        "etapas": etapas, "rol": getattr(u.perfil, "rol_legible", ""), "admin": perm.es_admin(u),
        "kpi": {"lotes": Lote.objects.count(), "productores": Productor.objects.count(), "existencias_kg": kg,
                "pedidos": Despacho.objects.filter(estado__in=["programado", "transito"]).count(),
                "ventas": Venta.objects.exclude(estado="anulada").count()},
        "ultimos_lotes": Lote.objects.select_related("producto").order_by("-fecha_creacion", "-id")[:5] if ver_lotes else None,
        "pedidos": Venta.objects.select_related("cliente", "lote").order_by("-fecha", "-id")[:4] if ver_pedidos else None,
        "datos_demo": get_user_model().objects.filter(username="cosechas2").exists(),
        "url_lotes": reverse("lotes:lote_lista") if perm.administra_area(u, Area.LOTES) or perm.area_de(u) == Area.REPORTES else None,
        "url_ventas": reverse("comercial:venta_lista") if perm.administra_area(u, Area.COMERCIAL) or perm.area_de(u) == Area.REPORTES else
                      (reverse("transporte:despacho_lista") if perm.administra_area(u, Area.TRANSPORTE) else None),
    })


@login_required
def inicio(request):
    """Panel de procedencia (indicadores, gráficas y registros): se conserva igual que antes."""
    u = request.user
    if perm.es_admin(u):
        return panel_admin(request)
    return panel_operador(request, perm.area_de(u))


def panel_admin(request):
    g = request.GET
    lotes = Lote.objects.select_related("producto")
    filtros = {k: g.get(k, "").strip() for k in ("producto", "productor", "ubicacion", "estado", "desde", "hasta", "lote")}
    if filtros["producto"]:
        lotes = lotes.filter(producto_id=filtros["producto"])
    if filtros["productor"]:
        lotes = lotes.filter(cosechas__productor_id=filtros["productor"])
    if filtros["ubicacion"]:
        lotes = lotes.filter(Q(cosechas__productor__canton__icontains=filtros["ubicacion"]) |
                             Q(cosechas__productor__parroquia__icontains=filtros["ubicacion"]))
    if filtros["estado"]:
        lotes = lotes.filter(estado=filtros["estado"])
    if filtros["desde"]:
        lotes = lotes.filter(fecha_creacion__gte=filtros["desde"])
    if filtros["hasta"]:
        lotes = lotes.filter(fecha_creacion__lte=filtros["hasta"])
    if filtros["lote"]:
        lotes = lotes.filter(codigo__icontains=filtros["lote"])
    lotes = lotes.distinct()
    lista_lotes = list(lotes)

    kg_rec = Recepcion.objects.aggregate(t=Sum("peso_recibido"))["t"] or Decimal("0")
    kg_rch = Clasificacion.objects.filter(categoria="rechazo").aggregate(t=Sum("cantidad"))["t"] or Decimal("0")
    completos = sum(1 for l in lista_lotes if l.completitud == 100)
    pendientes = {m._meta.verbose_name_plural: m.objects.filter(estado_revision="pendiente").count() for m in MODELOS_REVISION}
    etiquetas, valores = _semanas(Cosecha.objects.all())
    estados = dict(lotes.values_list("estado").annotate(n=Count("id")).values_list("estado", "n"))

    ctx = {
        "titulo": "Panel de procedencia", "saludo": saludo(), "hoy": timezone.localdate(),
        "kpi": {
            "productores": Productor.objects.count(), "parcelas": Parcela.objects.count(),
            "productos": Producto.objects.count(), "cosechas": Cosecha.objects.count(),
            "kg_cosechados": Cosecha.objects.aggregate(t=Sum("cantidad"))["t"] or 0,
            "lotes": len(lista_lotes),
            "almacenamiento": sum(1 for l in lista_lotes if l.estado in ("almacenamiento", "proceso")),
            "transporte": sum(1 for l in lista_lotes if l.estado == "transporte") +
                          Despacho.objects.filter(estado="transito").exclude(lote__estado="transporte").values("lote").distinct().count(),
            "entregados": sum(1 for l in lista_lotes if l.estado == "entregado"),
            "pendientes": sum(pendientes.values()),
            "rechazo_pct": round(kg_rch * 100 / kg_rec, 1) if kg_rec else 0,
            "trazabilidad_pct": round(100 * completos / len(lista_lotes)) if lista_lotes else 0,
            "escaneos": EscaneoQR.objects.count(), "eventos": EventoTrazabilidad.objects.count(),
            "parcelas_activas": Parcela.objects.exclude(estado_cultivo__in=["descanso", "cosechado"]).count(),
            "cosechas_mes": Cosecha.objects.filter(fecha__gte=timezone.localdate().replace(day=1)).count(),
            "kg_recibidos": kg_rec,
            "aceptacion_pct": round(100 - kg_rch * 100 / kg_rec, 1) if kg_rec else 0,
            "inventario": Lote.objects.filter(estado__in=["almacenamiento", "proceso"], cantidad_disponible__gt=0).count(),
            "despachos": Despacho.objects.exclude(estado="cancelado").count(),
            "entregas_pendientes": Despacho.objects.filter(estado__in=["programado", "transito"]).count(),
            "alertas": len(indicadores.alertas(request.user)),
        },
        "vacio": not Productor.objects.exists() and not Cosecha.objects.exists(),
        "rol": request.user.perfil.rol_legible,
        "pendientes": [(k, v) for k, v in pendientes.items() if v],
        "actividad": RegistroAuditoria.objects.exclude(accion__in=["ingreso", "salida"]).select_related("usuario")[:9],
        "lotes_tabla": lista_lotes[:8],
        "filtros": filtros, "hay_filtros": any(filtros.values()),
        "productos": Producto.objects.filter(estado="activo"), "productores": Productor.objects.all(),
        "estados_lote": Lote.ESTADOS,
        "graficos": {
            "semanas": {"etiquetas": etiquetas, "valores": valores},
            "series": {"kg": valores, "lotes": _serie(Lote.objects.all(), "fecha_creacion"),
                       "eventos": _serie(EventoTrazabilidad.objects.all(), "fecha_hora", fecha_hora=True),
                       "escaneos": _serie(EscaneoQR.objects.all(), "fecha_hora", fecha_hora=True)},
            "rechazo": _rechazo_por_parcela(Parcela.objects.select_related("cultivo")),
            "estados": {"etiquetas": [dict(Lote.ESTADOS)[k] for k in estados], "valores": list(estados.values())},
            "aceptacion": [round(float(kg_rec - kg_rch), 1), round(float(kg_rch), 1)],
            "despachos": {"etiquetas": [dict(Despacho.ESTADOS)[k] for k, _ in Despacho.ESTADOS],
                          "valores": [Despacho.objects.filter(estado=k).count() for k, _ in Despacho.ESTADOS]},
            "trazabilidad": round(100 * completos / len(lista_lotes)) if lista_lotes else 0,
        },
        "accesos": [(reverse("productores:productor_crear"), "Productor", "bi-person-plus"),
                    (reverse("parcelas:parcela_crear"), "Parcela", "bi-geo-alt"),
                    (reverse("cosechas:cosecha_crear"), "Cosecha", "bi-flower1"),
                    (reverse("lotes:lote_crear"), "Lote", "bi-box-seam"),
                    (reverse("transporte:despacho_crear"), "Despacho", "bi-truck"),
                    (reverse("cuentas:usuario_crear"), "Cuenta", "bi-person-gear")],
    }
    return render(request, "dashboard/admin.html", ctx)


def panel_operador(request, area):
    u = request.user
    hoy = timezone.localdate()
    kpis, acciones, tabla, aviso = [], [], None, ""

    def url(n, *a):
        return reverse(n, args=a)

    if area == Area.PRODUCTORES:
        mios = Productor.objects.filter(responsable=u)
        kpis = [(mios.count(), "Mis productores", "bi-people"), (mios.filter(estado="activo").count(), "Activos", "bi-check-circle"),
                (sum(1 for p in mios if p.datos_incompletos), "Datos por completar", "bi-exclamation-circle"),
                (mios.filter(estado_revision="pendiente").count(), "Pendientes de revisión", "bi-hourglass-split")]
        acciones = [(url("productores:productor_crear"), "Registrar productor", "bi-person-plus"),
                    (url("productores:productor_lista"), "Ver mis productores", "bi-list-ul")]
        tabla = ("Productores con datos por completar", ["Código", "Nombre", "Ubicación"],
                 [(p.get_absolute_url(), [p.codigo, p.nombre, p.ubicacion]) for p in mios if p.datos_incompletos][:8])
    elif area == Area.PARCELAS:
        mias = Parcela.objects.filter(responsable=u).select_related("cultivo")
        kpis = [(mias.count(), "Mis parcelas", "bi-geo-alt"),
                (mias.aggregate(t=Sum("superficie"))["t"] or 0, "Superficie total", "bi-bounding-box"),
                (mias.filter(estado_cultivo__in=["desarrollo", "cosecha"]).count(), "Cultivos en desarrollo o cosecha", "bi-flower2"),
                (Labor.objects.filter(responsable=u, fecha__gte=hoy - timedelta(days=30)).count(), "Labores del último mes", "bi-tools")]
        acciones = [(url("parcelas:parcela_crear"), "Registrar parcela", "bi-plus-lg"),
                    (url("parcelas:labor_crear"), "Registrar labor", "bi-tools"),
                    (url("parcelas:geojson"), "Mapa para QGIS (GeoJSON)", "bi-map")]
        tabla = ("Mis parcelas", ["Código", "Nombre", "Cultivo", "Estado"],
                 [(p.get_absolute_url(), [p.codigo, p.nombre, p.cultivo.nombre, p.get_estado_cultivo_display()]) for p in mias[:8]])
    elif area == Area.PRODUCTOS:
        mios = Producto.objects.filter(responsable=u)
        kpis = [(Producto.objects.count(), "Productos en el catálogo", "bi-basket2"), (mios.count(), "Registrados por mí", "bi-person-check"),
                (Producto.objects.filter(estado="activo").count(), "Activos", "bi-check-circle"),
                (mios.filter(estado_revision="pendiente").count(), "Pendientes de revisión", "bi-hourglass-split")]
        acciones = [(url("productos:producto_crear"), "Registrar producto", "bi-plus-lg"),
                    (url("productos:producto_lista"), "Ver catálogo", "bi-list-ul")]
        tabla = ("Mis productos", ["Código", "Nombre", "Categoría", "GTIN"],
                 [(p.get_absolute_url(), [p.codigo, p.nombre, p.get_categoria_display(), p.gtin]) for p in mios[:8]])
    elif area == Area.COSECHAS:
        mias = Cosecha.objects.filter(responsable=u).select_related("producto", "parcela")
        sin_recibir = mias.filter(recepcion__isnull=True)
        sin_clasificar = [r for r in Recepcion.objects.filter(responsable=u) if r.kg_clasificados < r.peso_recibido]
        kpis = [(mias.count(), "Mis cosechas", "bi-flower1"),
                (mias.filter(fecha__gte=hoy.replace(day=1)).aggregate(t=Sum("cantidad"))["t"] or 0, "Kg cosechados este mes", "bi-graph-up"),
                (sin_recibir.count(), "Pendientes de recibir", "bi-hourglass-split"),
                (len(sin_clasificar), "Pendientes de clasificar", "bi-camera")]
        acciones = [(url("cosechas:cosecha_crear"), "Registrar cosecha", "bi-plus-lg"),
                    (url("cosechas:recepcion_crear"), "Registrar recepción", "bi-box-arrow-in-down"),
                    (url("cosechas:clasificacion_crear"), "Registrar clasificación", "bi-camera")]
        tabla = ("Cosechas pendientes de recibir", ["Código", "Producto", "Parcela", "Cantidad"],
                 [(c.get_absolute_url(), [c.codigo, c.producto.nombre, c.parcela.codigo, f"{c.cantidad} {c.unidad}"]) for c in sin_recibir[:8]])
    elif area == Area.LOTES:
        mios = Lote.objects.filter(responsable=u).select_related("producto")
        activos = mios.exclude(estado__in=["retirado", "agotado", "entregado"])
        kpis = [(mios.count(), "Mis lotes", "bi-box-seam"), (activos.count(), "Lotes activos", "bi-check-circle"),
                (activos.filter(producto__unidad="kg").aggregate(t=Sum("cantidad_disponible"))["t"] or 0, "Kg disponibles", "bi-boxes"),
                (sum(1 for l in activos if l.por_vencer), "Por vencer (2 días)", "bi-alarm")]
        acciones = [(url("lotes:lote_crear"), "Crear lote", "bi-plus-lg"), (url("lotes:lote_lista"), "Ver mis lotes", "bi-list-ul")]
        tabla = ("Lotes activos", ["Lote", "Producto", "Disponible", "Vence"],
                 [(l.get_absolute_url(), [l.codigo, l.producto.nombre, f"{l.cantidad_disponible} {l.unidad}",
                                          f"{l.fecha_vencimiento:%d/%m/%Y}" if l.fecha_vencimiento else "–"]) for l in activos[:8]])
    elif area == Area.TRAZABILIDAD:
        lotes = list(Lote.objects.exclude(estado="retirado").select_related("producto"))
        incompletos = [l for l in lotes if l.completitud < 100]
        kpis = [(EventoTrazabilidad.objects.filter(fecha_hora__date=hoy).count(), "Eventos registrados hoy", "bi-clock-history"),
                (EventoTrazabilidad.objects.filter(responsable=u).count(), "Registrados por mí", "bi-person-check"),
                (len(incompletos), "Lotes con eventos pendientes", "bi-exclamation-circle"),
                (SimulacroRetiro.objects.count(), "Simulacros de retiro (E1)", "bi-stopwatch")]
        acciones = [(url("trazabilidad:evento_crear"), "Registrar evento", "bi-plus-lg"),
                    (url("trazabilidad:simulacros"), "Simulacro de retiro", "bi-stopwatch"),
                    (url("trazabilidad:evento_lista"), "Historial completo", "bi-diagram-3")]
        tabla = ("Lotes con trazabilidad incompleta", ["Lote", "Producto", "Completitud", "Estado"],
                 [(l.get_absolute_url(), [l.codigo, l.producto.nombre, f"{l.completitud} %", l.get_estado_display()]) for l in incompletos[:8]])
    elif area == Area.TRANSPORTE:
        mios = Despacho.objects.filter(responsable=u).select_related("lote")
        entregados = mios.filter(estado="entregado")
        a_tiempo = entregados.filter(entregado_a_tiempo=True).count()
        kpis = [(mios.filter(estado="programado").count(), "Despachos programados", "bi-calendar-event"),
                (mios.filter(estado="transito").count(), "En tránsito", "bi-truck"),
                (entregados.count(), "Entregados", "bi-check2-circle"),
                (f"{round(100 * a_tiempo / entregados.count())} %" if entregados else "–", "Entregas a tiempo", "bi-stopwatch")]
        acciones = [(url("transporte:despacho_crear"), "Registrar despacho", "bi-plus-lg"),
                    (url("transporte:transportista_crear"), "Registrar transportista", "bi-person-vcard")]
        tabla = ("Despachos activos", ["Código", "Lote", "Destino", "Estado"],
                 [(d.get_absolute_url(), [d.codigo, d.lote.codigo, d.destino, d.get_estado_display()])
                  for d in mios.filter(estado__in=["programado", "transito"])[:8]])
    elif area == Area.COMERCIAL:
        from comercial.models import Cliente, Venta
        mias = Venta.objects.filter(responsable=u).select_related("cliente", "lote")
        pend = mias.filter(estado__in=["pendiente", "parcial"])
        kpis = [(Cliente.objects.filter(activo=True).count(), "Clientes activos", "bi-person-lines-fill"),
                (mias.exclude(estado="anulada").count(), "Mis ventas", "bi-receipt"),
                (pend.count(), "Pendientes de despacho", "bi-hourglass-split"),
                (mias.filter(estado="entregada").count(), "Entregadas", "bi-check2-circle")]
        acciones = [(url("comercial:venta_crear"), "Registrar venta", "bi-cart-plus"),
                    (url("comercial:cliente_crear"), "Registrar cliente", "bi-person-plus"),
                    (url("asistente:agente_venta"), "Venta con agente guiado", "bi-signpost-2")]
        tabla = ("Ventas pendientes de despacho", ["Venta", "Cliente", "Lote", "Por despachar"],
                 [(v.get_absolute_url(), [v.codigo, v.cliente.nombre, v.lote.codigo, f"{v.por_despachar} {v.unidad}"]) for v in pend[:8]])
    elif area == Area.REPORTES:
        return redirect("dashboard:area_reportes")

    from .areas import menu_para
    grupos = [g for g in menu_para(u) if g["clave"] != "general"]
    return render(request, "dashboard/operador.html", {
        "paneles": grupos, "rol": getattr(u.perfil, "rol_legible", ""),
        "titulo": "Mi área de trabajo", "saludo": saludo(), "hoy": timezone.localdate(), "kpis": kpis, "acciones": acciones, "tabla": tabla, "aviso": aviso,
        "puede_crear": perm.puede(u, "crear", area),
        "actividad": RegistroAuditoria.objects.filter(usuario=u).exclude(accion__in=["ingreso", "salida"])[:8],
    })


@login_required
def buscar(request):
    """Buscador superior: abre la ficha interna del lote si el usuario puede verla; si no, la consulta pública."""
    codigo = request.GET.get("q", "").strip()
    lote = Lote.objects.filter(codigo__iexact=codigo).first()
    if lote is None:
        from cosechas.models import Cosecha
        c = Cosecha.objects.filter(codigo__iexact=codigo).first()
        lote = c.lotes.first() if c else None
    if lote and (perm.consulta_area(request.user, Area.LOTES) or lote.responsable_id == request.user.id):
        return redirect(lote)
    return redirect(f"{reverse('consulta')}?codigo={codigo}")


# ---------------------------------------------------------------------------
# Paneles por área, alertas y hoja de ruta
# ---------------------------------------------------------------------------
from . import areas as areas_def          # noqa: E402
from . import indicadores                 # noqa: E402


@login_required
def panel_area(request, clave):
    a = areas_def.CLAVES.get(clave)
    perm.exigir(a is not None and areas_def.puede_ver_panel(request.user, clave), request, f"Acceso al panel del área {clave}")
    _clave, n, nombre, icono, descripcion, _areas, enlaces = a
    desde = hasta = None
    if clave == "reportes":
        from datetime import date
        try:
            desde = date.fromisoformat(request.GET.get("desde", "")) if request.GET.get("desde") else None
            hasta = date.fromisoformat(request.GET.get("hasta", "")) if request.GET.get("hasta") else None
        except ValueError:
            desde = hasta = None
        datos = indicadores.panel_reportes(request.user, desde, hasta)
    else:
        datos = indicadores.PANELES[clave](request.user)
    accesos = [g for g in areas_def.menu_para(request.user) if g["clave"] == clave]
    return render(request, "dashboard/area.html", {
        "titulo": nombre, "area_n": n, "area_icono": icono, "descripcion": descripcion, "clave": clave,
        "datos": datos, "graficos": datos.get("graficos", []), "accesos": accesos[0]["items"] if accesos else [],
        "desde": request.GET.get("desde", ""), "hasta": request.GET.get("hasta", ""),
    })


@login_required
def alertas(request):
    lista = indicadores.alertas(request.user)
    grupos = {}
    for x in lista:
        grupos.setdefault(x["grupo"], []).append(x)
    return render(request, "dashboard/alertas.html", {"titulo": "Alertas y notificaciones", "grupos": grupos, "total": len(lista)})


@login_required
def hoja_ruta(request):
    perm.exigir(perm.es_admin(request.user), request, "Acceso a la hoja de ruta")
    return render(request, "dashboard/hoja_ruta.html", {"titulo": "Funciones en preparación"})
