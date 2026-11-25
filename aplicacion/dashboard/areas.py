"""
Organización del aplicativo en 12 áreas del proceso productivo.

Cada área agrupa módulos que ya existen. Cada enlace declara qué áreas de operador pueden verlo;
el administrador general ve todo. Las vistas vuelven a comprobar los permisos en el servidor:
el menú solo evita mostrar opciones que el usuario no podría abrir.
"""
from django.urls import NoReverseMatch, reverse

from cuentas import permissions as perm
from cuentas.models import Area as A

TODOS = {c for c, _ in A.CODIGOS}
SOLO_ADMIN = set()

# (clave, número, nombre, icono, descripción, áreas que ven el panel del área, enlaces)
# enlace: (nombre_url, texto, icono, áreas que lo ven o None = las mismas del panel)
AREAS = [
    ("general", 1, "Panel general", "bi-speedometer2",
     "Indicadores de toda la cadena, alertas y asistentes.", {A.REPORTES}, [
         ("dashboard:area_general", "Indicadores generales", "bi-graph-up-arrow", {A.REPORTES}),
         ("dashboard:alertas", "Alertas y notificaciones", "bi-bell", TODOS),
         ("asistente:chat", "Asistente virtual", "bi-chat-dots", TODOS),
         ("asistente:agentes", "Agentes guiados", "bi-signpost-2", TODOS),
         ("asistente:voz", "Control por voz", "bi-mic", TODOS),
     ]),
    ("abastecimiento", 2, "Abastecimiento y proveedores", "bi-people",
     "Productores agrícolas que abastecen a la planta, sus datos y la procedencia de la materia prima.",
     {A.PRODUCTORES, A.PARCELAS, A.REPORTES}, [
         ("dashboard:area_abastecimiento", "Panel del área", "bi-grid", None),
         ("productores:productor_lista", "Productores y proveedores", "bi-person-vcard", {A.PRODUCTORES, A.REPORTES}),
         ("productores:productor_crear", "Registrar productor", "bi-person-plus", {A.PRODUCTORES}),
         ("parcelas:parcela_lista", "Parcelas y cultivos", "bi-geo-alt", {A.PARCELAS, A.REPORTES}),
     ]),
    ("produccion", 3, "Producción agrícola", "bi-flower1",
     "Cultivos, labores, insumos aplicados y registro de cosechas.", {A.PARCELAS, A.COSECHAS, A.REPORTES}, [
         ("dashboard:area_produccion", "Panel del área", "bi-grid", None),
         ("parcelas:parcela_lista", "Cultivos por parcela", "bi-geo-alt", {A.PARCELAS, A.REPORTES}),
         ("parcelas:labor_lista", "Labores e insumos", "bi-tools", {A.PARCELAS, A.REPORTES}),
         ("cosechas:cosecha_lista", "Registro de cosechas", "bi-basket", {A.COSECHAS, A.REPORTES}),
     ]),
    ("recepcion", 4, "Recepción y clasificación", "bi-clipboard-check",
     "Recepción en planta, pesaje, inspección de calidad, categorías y motivos de rechazo.", {A.COSECHAS, A.REPORTES}, [
         ("dashboard:area_recepcion", "Panel del área", "bi-grid", None),
         ("cosechas:recepcion_lista", "Recepción y pesaje", "bi-box-arrow-in-down", None),
         ("cosechas:clasificacion_lista", "Clasificación por categoría", "bi-funnel", None),
     ]),
    ("almacenamiento", 5, "Almacenamiento e inventarios", "bi-boxes",
     "Lotes, existencias, ubicaciones, entradas y salidas y alertas de stock.", {A.LOTES, A.REPORTES}, [
         ("dashboard:area_almacenamiento", "Panel del área", "bi-grid", None),
         ("lotes:lote_lista", "Lotes", "bi-box-seam", None),
         ("lotes:inventario", "Inventario actual", "bi-clipboard-data", None),
         ("lotes:movimientos", "Entradas y salidas", "bi-arrow-left-right", None),
     ]),
    ("transformacion", 6, "Transformación y empaque", "bi-recycle",
     "Procesamiento, empaque y etiquetado, conservando el vínculo entre el lote de origen y el resultante.",
     {A.LOTES, A.TRAZABILIDAD, A.REPORTES}, [
         ("dashboard:area_transformacion", "Panel del área", "bi-grid", None),
         ("lotes:etiquetas", "Etiquetado (QR)", "bi-tags", {A.LOTES, A.REPORTES}),
         ("trazabilidad:evento_crear", "Registrar empaque o proceso", "bi-plus-circle", {A.TRAZABILIDAD}),
     ]),
    ("distribucion", 7, "Distribución y transporte", "bi-truck",
     "Despachos, transportistas y vehículos, seguimiento y estado de las entregas.", {A.TRANSPORTE, A.REPORTES}, [
         ("dashboard:area_distribucion", "Panel del área", "bi-grid", None),
         ("transporte:despacho_lista", "Despachos y entregas", "bi-signpost-split", None),
         ("transporte:transportista_lista", "Transportistas y vehículos", "bi-person-vcard", None),
     ]),
    ("comercial", 8, "Clientes y comercialización", "bi-shop",
     "Clientes mayoristas, minoristas y comercios, ventas y lotes entregados a cada cliente.", {A.COMERCIAL, A.REPORTES}, [
         ("dashboard:area_comercial", "Panel del área", "bi-grid", None),
         ("comercial:cliente_lista", "Clientes", "bi-person-lines-fill", None),
         ("comercial:venta_lista", "Ventas y pedidos", "bi-receipt", None),
     ]),
    ("trazabilidad", 9, "Trazabilidad digital", "bi-diagram-3",
     "Historial de eventos, consulta por código de lote, procedencia y simulacros de retiro.",
     {A.TRAZABILIDAD, A.REPORTES}, [
         ("dashboard:area_trazabilidad", "Panel del área", "bi-grid", None),
         ("trazabilidad:evento_lista", "Historial de eventos", "bi-clock-history", None),
         ("trazabilidad:simulacros", "Simulacro de retiro", "bi-stopwatch", {A.TRAZABILIDAD}),
         ("consulta", "Consulta por código de lote", "bi-qr-code-scan", TODOS),
     ]),
    ("seguridad", 10, "Personal y seguridad", "bi-shield-lock",
     "Usuarios, roles y permisos, registro de actividad y auditoría de modificaciones.", SOLO_ADMIN, [
         ("dashboard:area_seguridad", "Panel del área", "bi-grid", None),
         ("cuentas:usuarios", "Usuarios, roles y permisos", "bi-person-gear", None),
         ("cuentas:auditoria", "Auditoría", "bi-shield-check", None),
         ("asistente:uso", "Uso del asistente y la voz", "bi-chat-square-text", None),
     ]),
    ("reportes", 11, "Reportes y análisis", "bi-bar-chart-line",
     "Reportes de producción, calidad, inventario, distribución y procedencia, con exportación.", {A.REPORTES}, [
         ("dashboard:area_reportes", "Analítica de datos", "bi-graph-up", None),
         ("reportes:inicio", "Reportes y exportación", "bi-file-earmark-spreadsheet", None),
     ]),
    ("administracion", 12, "Administración del sistema", "bi-gear",
     "Catálogos, parámetros, integraciones (Odoo y API) y acceso técnico.", SOLO_ADMIN, [
         ("dashboard:area_administracion", "Panel del área", "bi-grid", None),
         ("productos:producto_lista", "Catálogo de productos", "bi-basket2", {A.PRODUCTOS, A.REPORTES}),
         ("integracion:estado", "Integración ERP (Odoo)", "bi-plug", None),
         ("api_docs", "API REST", "bi-braces", None),
         ("dashboard:hoja_ruta", "Funciones en preparación", "bi-map", None),
     ]),
]

CLAVES = {a[0]: a for a in AREAS}


def ve(user, areas):
    """¿El usuario puede ver algo marcado para estas áreas? (el administrador siempre)."""
    if perm.es_admin(user):
        return True
    return perm.area_de(user) in (areas or set())


def puede_ver_panel(user, clave):
    a = CLAVES.get(clave)
    return bool(a) and ve(user, a[5])


def _url(nombre):
    try:
        return reverse(nombre)
    except NoReverseMatch:
        return None


def menu_para(user):
    grupos = []
    for clave, n, nombre, icono, desc, areas_panel, enlaces in AREAS:
        items = []
        for url_name, texto, ic, areas in enlaces:
            permitidas = areas_panel if areas is None else areas
            if not ve(user, permitidas):
                continue
            u = _url(url_name)
            if u:
                items.append({"url": u, "texto": texto, "icono": ic, "externo": url_name == "consulta",
                              "admin_django": False})
        if clave == "administracion" and user.is_staff and perm.es_admin(user):
            items.append({"url": "/admin/", "texto": "Panel de Django Admin", "icono": "bi-database-gear", "externo": True})
        if items:
            panel = _url(f"dashboard:area_{clave}") if ve(user, areas_panel) else None
            grupos.append({"clave": clave, "n": n, "nombre": nombre, "icono": icono, "items": items,
                           "panel": panel or items[0]["url"]})
    return grupos
