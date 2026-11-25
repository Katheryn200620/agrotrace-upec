"""
Motor del asistente virtual de AgroTrace-UPEC.

Funciona en dos niveles, siempre con datos reales y respetando los permisos del usuario:
1. Reglas (siempre disponible, sin internet): reconoce la intención de la pregunta y consulta la base de datos.
2. IA externa (opcional): si se configura un proveedor en .env, las preguntas libres se envían a un modelo de lenguaje
   junto con el contexto que el usuario tiene permitido ver. Si la IA no responde, se usa el nivel 1 y se indica.

Cada respuesta informa su fuente ("reglas" o "ia") para no presentar como IA lo que no lo es.
"""
import json
import logging
import re
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from django.conf import settings
from django.db.models import Q, Sum
from django.urls import NoReverseMatch, reverse

from cuentas import permissions as perm
from cuentas.models import Area

log = logging.getLogger(__name__)


@dataclass
class Respuesta:
    texto: str
    enlaces: list = field(default_factory=list)       # [(texto, url)]
    sugerencias: list = field(default_factory=list)   # preguntas de ejemplo
    intencion: str = "desconocida"
    fuente: str = "reglas"
    contexto: dict = field(default_factory=dict)      # datos permitidos que se pasan a la IA

    def como_dict(self):
        return {"texto": self.texto, "enlaces": [{"texto": t, "url": u} for t, u in self.enlaces],
                "sugerencias": self.sugerencias, "intencion": self.intencion, "fuente": self.fuente}


def normalizar(t):
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip()


def _url(nombre, *args):
    try:
        return reverse(nombre, args=args)
    except NoReverseMatch:
        return None


def _n(v):
    from decimal import Decimal
    v = Decimal(v or 0)
    return f"{v.normalize():f}" if v == v.to_integral() else f"{v:.2f}".replace(".", ",")


SUGERENCIAS = ["¿Qué hay en el inventario?", "¿Cómo registro una cosecha?", "Consultar el lote H26112201",
               "¿Qué alertas tengo?", "¿Dónde registro una venta?"]

# entidad: (palabras clave, url de registro, área que registra, pasos, agente)
INSTRUCCIONES = {
    "productor": (["productor", "proveedor"], "productores:productor_crear", Area.PRODUCTORES,
                  ["Abra Área 2 → Registrar productor.", "Escriba nombre, tipo, cantón y parroquia (el código se genera solo).",
                   "Indique si autoriza mostrar su nombre en el QR.", "Guarde: queda pendiente de revisión del administrador."], "productor"),
    "parcela": (["parcela", "cultivo", "terreno"], "parcelas:parcela_crear", Area.PARCELAS,
                ["Abra Área 3 → Cultivos por parcela → Nuevo.", "Elija el productor y el tipo de cultivo.",
                 "Escriba código, superficie y, si puede, latitud y longitud (sirven para el mapa de QGIS).", "Guarde: se genera el GLN de la parcela."], "parcela"),
    "labor": (["labor", "riego", "fertiliz", "fumig", "insumo", "siembra"], "parcelas:labor_crear", Area.PARCELAS,
              ["Abra Área 3 → Labores e insumos → Nuevo.", "Elija la parcela, el tipo de labor y la fecha.",
               "Anote el insumo y la dosis si aplica.", "Guarde: se registra un evento de cultivo en la trazabilidad."], None),
    "cosecha": (["cosecha", "cosechar"], "cosechas:cosecha_crear", Area.COSECHAS,
                ["Abra Área 3 → Registro de cosechas → Nuevo.", "Elija la parcela de origen; el productor y el producto deben coincidir.",
                 "Escriba la fecha y la cantidad recolectada.", "Guarde: se genera el código C-parcela-fecha y el evento de cosecha."], "cosecha"),
    "recepcion": (["recepcion", "recibir", "pesaje", "pesar"], "cosechas:recepcion_crear", Area.COSECHAS,
                  ["Abra Área 4 → Recepción y pesaje → Nuevo.", "Elija la cosecha que llega a la planta.",
                   "Registre el peso recibido y la temperatura.", "Después clasifique lo recibido por categorías."], "recepcion"),
    "clasificacion": (["clasific", "calidad", "rechazo", "categoria"], "cosechas:clasificacion_crear", Area.COSECHAS,
                      ["Abra Área 4 → Clasificación por categoría → Nuevo.", "Elija la recepción.",
                       "Registre los kg de cada categoría (extra, primera, segunda, rechazo).", "Si hay rechazo, anote la causa."], None),
    "lote": (["lote"], "lotes:lote_crear", Area.LOTES,
             ["Abra Área 5 → Lotes → Nuevo.", "Elija el producto y las cosechas recibidas de origen.",
              "La cantidad no puede superar lo aprovechable (recibido menos rechazo).", "Guarde: se generan el código del lote y su QR GS1."], "lote"),
    "despacho": (["despacho", "despachar", "enviar", "transporte"], "transporte:despacho_crear", Area.TRANSPORTE,
                 ["Abra Área 7 → Despachos y entregas → Nuevo.", "Elija la venta que atiende (o el lote si es un traslado).",
                  "Indique transportista, salida y destino.", "La cantidad se descuenta del inventario al guardar."], None),
    "venta": (["venta", "vender", "pedido"], "comercial:venta_crear", Area.COMERCIAL,
              ["Abra Área 8 → Ventas y pedidos → Nuevo.", "Elija el cliente y el lote.",
               "Escriba la cantidad (no puede superar lo disponible y no comprometido).", "Guarde: el área de transporte la verá para despacharla."], "venta"),
    "cliente": (["cliente", "comprador"], "comercial:cliente_crear", Area.COMERCIAL,
                ["Abra Área 8 → Clientes → Nuevo.", "Escriba nombre, tipo de cliente y ciudad.", "Guarde: se genera el código CL-000."], None),
}


class Motor:
    def __init__(self, user):
        self.user = user
        self.admin = perm.es_admin(user)
        self.area = perm.area_de(user)

    # ------------------------------------------------------------------
    def responder(self, pregunta):
        q = normalizar(pregunta)
        r = self._reglas(q, pregunta)
        if r is None:
            r = Respuesta("No encontré una respuesta exacta para eso. Puedo ayudarle con lotes, inventario, cosechas, ventas, "
                          "alertas y con los pasos para registrar información.", sugerencias=SUGERENCIAS, intencion="desconocida")
            if ia_configurada():
                ia = consultar_ia(pregunta, self._contexto_general())
                if ia:
                    return Respuesta(ia, intencion="libre", fuente="ia", sugerencias=SUGERENCIAS[:3])
                r.texto = "(El asistente de IA no respondió; esta es la respuesta básica.) " + r.texto
        elif ia_configurada() and r.intencion in ("explicacion",) and r.contexto:
            ia = consultar_ia(pregunta, r.contexto)
            if ia:
                r.texto, r.fuente = ia, "ia"
        return r

    # ------------------------------------------------------------------
    def _reglas(self, q, original):
        m = re.search(r"\bh\s*-?\s*(\d[\d\s-]{6,12}\d)", q)
        if m:
            codigo = "H" + re.sub(r"\D", "", m.group(1))
            return self.lote(codigo)
        m = re.search(r"\bc-p-?\d+-\d{8}-\d+", q)
        if m:
            return self.cosecha(m.group(0).upper())
        m = re.search(r"\bv-\d{8}-\d+", q)
        if m:
            return self.venta(m.group(0).upper())
        if re.search(r"\b(como|pasos|registr|crear|creo|agrego|agregar|ingres|nuevo|nueva|donde registro)", q):
            for clave, (palabras, *_r) in INSTRUCCIONES.items():
                if any(p in q for p in palabras):
                    return self.instrucciones(clave)
        if re.search(r"inventario|stock|existencia|cuanto hay|disponible|bodega", q):
            return self.inventario()
        if re.search(r"alerta|aviso|notificac", q):
            return self.alertas()
        if re.search(r"\bventa|pedido|cliente", q):
            return self.ventas()
        if re.search(r"despacho|entrega|transport|transito", q):
            return self.despachos()
        if re.search(r"pendiente", q):
            return self.alertas()
        if re.search(r"productor|proveedor", q):
            return self.productores(original)
        if re.search(r"producto|catalogo|precio|gtin", q):
            return self.productos()
        if re.search(r"parcela|cultivo", q):
            return self.parcelas()
        if re.search(r"cosecha|cosechado|kilos|kg", q):
            return self.cosechas()
        if re.search(r"trazabilidad|qr|procedencia|origen|gs1|epcis|retiro", q):
            return self.explicacion()
        if re.search(r"donde|abrir|ir a|modulo|menu|pantalla|seccion", q):
            return self.navegacion(q)
        if re.search(r"^(hola|buen|saludos|ayuda|que puedes|que haces|quien eres)", q) or q in ("?", "ayuda"):
            return self.ayuda()
        return None

    # ------------------------------------------------------------------
    def ayuda(self):
        return Respuesta(f"Hola, {self.user.first_name or self.user.username}. Soy el asistente de AgroTrace-UPEC. "
                         "Respondo con los datos que su cuenta puede ver: consulto lotes por su código, el inventario, "
                         "las alertas, ventas y despachos, y le explico paso a paso cómo registrar información.",
                         sugerencias=SUGERENCIAS, intencion="ayuda")

    def lote(self, codigo):
        from lotes.models import Lote
        lote = Lote.objects.select_related("producto").filter(codigo__iexact=codigo).first()
        if not lote:
            return Respuesta(f"No encontré el lote {codigo}. Revise el código: tiene la forma H + año, mes y día + número (ej. H26112201).",
                             intencion="lote", sugerencias=["¿Qué hay en el inventario?"])
        puede = perm.consulta_area(self.user, Area.LOTES) or lote.responsable_id == self.user.id or self.area == Area.COMERCIAL
        parcelas = ", ".join(f"{p.codigo} ({p.nombre})" for p in lote.parcelas()) or "sin parcela registrada"
        productores = ", ".join((p.nombre if perm.ve_datos_personales(self.user) else p.nombre_publico) for p in lote.productores())
        publica = f"{_url('consulta')}?codigo={lote.codigo}"
        if not puede:
            return Respuesta(f"El lote {lote.codigo} es de {lote.producto}. Su área no consulta lotes internos; puede ver su ficha pública.",
                             [("Ver ficha pública", publica)], intencion="lote")
        pasos = ", ".join(n for _c, n, ok in lote.control_eventos() if not ok)
        ultimo = lote.eventos.order_by("-fecha_hora").first()
        texto = (f"Lote {lote.codigo}: {lote.producto}, categoría {lote.get_categoria_display().lower()}, estado «{lote.get_estado_display()}». "
                 f"Disponible: {_n(lote.cantidad_disponible)} de {_n(lote.cantidad_inicial)} {lote.unidad}"
                 f"{f', vence el {lote.fecha_vencimiento:%d/%m/%Y}' if lote.fecha_vencimiento else ''}. "
                 f"Procedencia: parcela(s) {parcelas}; productor(es): {productores or 'sin registro'}. "
                 f"Trazabilidad completa al {lote.completitud} %" + (f" (falta: {pasos})." if pasos else ".") +
                 (f" Último evento: {ultimo.get_tipo_display().lower()} el {ultimo.fecha_hora:%d/%m/%Y}." if ultimo else ""))
        return Respuesta(texto, [("Abrir ficha del lote", lote.get_absolute_url()), ("Ficha pública (QR)", publica)],
                         intencion="lote", contexto={"lote": texto})

    def cosecha(self, codigo):
        from cosechas.models import Cosecha
        c = Cosecha.objects.select_related("producto", "parcela").filter(codigo__iexact=codigo).first()
        if not c:
            return Respuesta(f"No encontré la cosecha {codigo}.", intencion="cosecha")
        if not (perm.consulta_area(self.user, Area.COSECHAS) or c.responsable_id == self.user.id):
            return Respuesta("Su área no consulta cosechas.", intencion="cosecha")
        rec = f"recibida con {_n(c.recepcion.peso_recibido)} kg y {c.recepcion.porcentaje_rechazo} % de rechazo" if c.recibida else "todavía no recibida en planta"
        lotes = ", ".join(l.codigo for l in c.lotes.all()) or "ningún lote aún"
        return Respuesta(f"Cosecha {c.codigo}: {_n(c.cantidad)} {c.unidad} de {c.producto} de la parcela {c.parcela.codigo}, "
                         f"el {c.fecha:%d/%m/%Y}; {rec}. Lotes formados: {lotes}.", [("Abrir cosecha", c.get_absolute_url())], intencion="cosecha")

    def venta(self, codigo):
        from comercial.models import Venta
        v = Venta.objects.select_related("cliente", "lote").filter(codigo__iexact=codigo).first()
        if not v:
            return Respuesta(f"No encontré la venta {codigo}.", intencion="venta")
        if not (perm.consulta_area(self.user, Area.COMERCIAL) and (self.admin or self.area != Area.COMERCIAL or v.responsable_id == self.user.id)):
            return Respuesta("Su área no consulta esa venta.", intencion="venta")
        return Respuesta(f"Venta {v.codigo} a {v.cliente.nombre}: {_n(v.cantidad)} {v.unidad} del lote {v.lote.codigo}, "
                         f"total $ {_n(v.total)}, estado «{v.get_estado_display()}». Por despachar: {_n(v.por_despachar)} {v.unidad}.",
                         [("Abrir venta", v.get_absolute_url())], intencion="venta")

    def instrucciones(self, clave):
        palabras, url_name, area, pasos, agente = INSTRUCCIONES[clave]
        texto = f"Para registrar {'un' if clave not in ('parcela', 'labor', 'cosecha', 'recepcion', 'clasificacion', 'venta') else 'una'} {clave}: " + \
                " ".join(f"{i}) {p}" for i, p in enumerate(pasos, 1))
        enlaces = []
        if perm.puede(self.user, "crear", area):
            if agente and _url(f"asistente:agente_{agente}"):
                enlaces.append(("Hacerlo con el agente guiado", _url(f"asistente:agente_{agente}")))
            if _url(url_name):
                enlaces.append(("Abrir el formulario", _url(url_name)))
        else:
            texto += " Su cuenta no tiene permiso para registrar esto: lo hace el operador del área correspondiente o el administrador."
        return Respuesta(texto, enlaces, intencion="instrucciones")

    def inventario(self):
        from lotes.inventario import existencias
        from lotes.models import Lote
        if not (self.admin or self.area in (Area.LOTES, Area.REPORTES, Area.COMERCIAL, Area.TRANSPORTE)):
            return Respuesta("Su área no consulta el inventario. Pídalo al área de lotes o al administrador.", intencion="inventario")
        lotes = Lote.objects.filter(responsable=self.user) if self.area == Area.LOTES else Lote.objects.all()
        filas = [f for f in existencias(lotes) if f["total"] or f["bajo"]]
        if not filas:
            return Respuesta("No hay existencias disponibles en este momento.", intencion="inventario")
        partes = [f"{f['producto']}: {_n(f['total'])} {f['producto'].unidad} en {f['lotes']} lote(s)" + (" ⚠ bajo el mínimo" if f["bajo"] else "")
                  for f in filas]
        enlaces = [("Ver inventario", _url("lotes:inventario"))] if self.admin or self.area in (Area.LOTES, Area.REPORTES) else []
        return Respuesta("Existencias actuales: " + "; ".join(partes) + ".", enlaces, intencion="inventario",
                         contexto={"inventario": partes})

    def alertas(self):
        from dashboard.indicadores import alertas
        lista = alertas(self.user)
        if not lista:
            return Respuesta("No tiene alertas pendientes en sus áreas.", [("Ver alertas", _url("dashboard:alertas"))], intencion="alertas")
        top = "; ".join(a["texto"] for a in lista[:5])
        return Respuesta(f"Tiene {len(lista)} alerta(s). Las más importantes: {top}.", [("Ver todas las alertas", _url("dashboard:alertas"))],
                         intencion="alertas")

    def ventas(self):
        from comercial.models import Venta
        if not (self.admin or self.area in (Area.COMERCIAL, Area.TRANSPORTE, Area.REPORTES)):
            return Respuesta("Su área no consulta ventas.", intencion="ventas")
        qs = Venta.objects.exclude(estado="anulada")
        if self.area == Area.COMERCIAL:
            qs = qs.filter(responsable=self.user)
        pend = qs.filter(estado__in=["pendiente", "parcial"])
        texto = f"Hay {qs.count()} venta(s) registradas; {pend.count()} pendiente(s) de despacho."
        if pend:
            texto += " Pendientes: " + "; ".join(f"{v.codigo} ({v.cliente.nombre}, {_n(v.por_despachar)} {v.unidad})" for v in pend[:5]) + "."
        enl = [("Ver ventas", _url("comercial:venta_lista"))] if self.admin or self.area in (Area.COMERCIAL, Area.REPORTES) else []
        return Respuesta(texto, enl, intencion="ventas")

    def despachos(self):
        from transporte.models import Despacho
        if not (self.admin or self.area in (Area.TRANSPORTE, Area.REPORTES, Area.COMERCIAL)):
            return Respuesta("Su área no consulta despachos.", intencion="despachos")
        qs = Despacho.objects.exclude(estado="cancelado")
        if self.area == Area.TRANSPORTE:
            qs = qs.filter(responsable=self.user)
        act = qs.filter(estado__in=["programado", "transito"])
        texto = f"Despachos: {qs.count()} en total, {act.filter(estado='programado').count()} programado(s) y {act.filter(estado='transito').count()} en tránsito."
        if act:
            texto += " Activos: " + "; ".join(f"{d.codigo} hacia {d.destino}" for d in act[:5]) + "."
        enl = [("Ver despachos", _url("transporte:despacho_lista"))] if self.admin or self.area in (Area.TRANSPORTE, Area.REPORTES) else []
        return Respuesta(texto, enl, intencion="despachos")

    def productores(self, original):
        from productores.models import Productor
        if not perm.consulta_area(self.user, Area.PRODUCTORES):
            return Respuesta("Su área no consulta productores.", intencion="productores")
        qs = Productor.objects.all()
        if self.area == Area.PRODUCTORES:
            qs = qs.filter(responsable=self.user)
        m = re.search(r"productor(?:a|es)?\s+(?:llamad[oa]\s+|de\s+)?([a-záéíóúñ ]{3,})", original.lower())
        if m and not re.search(r"^(hay|tengo|registrad|activ)", m.group(1).strip()):
            nombre = m.group(1).strip()
            qs = qs.filter(Q(nombre__icontains=nombre) | Q(canton__icontains=nombre) | Q(parroquia__icontains=nombre))
        personales = perm.ve_datos_personales(self.user)
        lista = [f"{p.codigo} {p.nombre if personales else p.nombre_publico} ({p.ubicacion})" for p in qs[:8]]
        texto = f"Encontré {qs.count()} productor(es)" + (": " + "; ".join(lista) + "." if lista else ".")
        enl = [("Ver productores", _url("productores:productor_lista"))] if perm.administra_area(self.user, Area.PRODUCTORES) or self.area == Area.REPORTES else []
        return Respuesta(texto, enl, intencion="productores")

    def productos(self):
        from productos.models import Producto
        qs = Producto.objects.filter(estado="activo")
        lista = [f"{p} (GTIN {p.gtin}, $ {_n(p.precio)}/{p.unidad})" for p in qs[:10]]
        return Respuesta(f"Catálogo activo ({qs.count()}): " + "; ".join(lista) + ".", intencion="productos")

    def parcelas(self):
        from parcelas.models import Parcela
        if not perm.consulta_area(self.user, Area.PARCELAS):
            return Respuesta("Su área no consulta parcelas.", intencion="parcelas")
        qs = Parcela.objects.select_related("cultivo")
        if self.area == Area.PARCELAS:
            qs = qs.filter(responsable=self.user)
        lista = [f"{p.codigo} {p.nombre}: {p.cultivo.nombre}, {p.get_estado_cultivo_display().lower()}" for p in qs[:8]]
        return Respuesta(f"Parcelas ({qs.count()}): " + "; ".join(lista) + ".", intencion="parcelas")

    def cosechas(self):
        from cosechas.models import Cosecha
        if not perm.consulta_area(self.user, Area.COSECHAS):
            return Respuesta("Su área no consulta cosechas.", intencion="cosechas")
        qs = Cosecha.objects.all()
        if self.area == Area.COSECHAS:
            qs = qs.filter(responsable=self.user)
        total = qs.aggregate(t=Sum("cantidad"))["t"] or 0
        sin = qs.filter(recepcion__isnull=True).count()
        return Respuesta(f"Hay {qs.count()} cosecha(s) con {_n(total)} kg en total; {sin} sin recepción en planta.", intencion="cosechas")

    def explicacion(self):
        texto = ("La trazabilidad en AgroTrace-UPEC une cada etapa: productor → parcela → labores → cosecha → recepción → "
                 "clasificación → lote → empaque → despacho → cliente. Cada lote tiene un código único y un QR con GS1 Digital Link "
                 "(GTIN del producto + código del lote). Al escanearlo, el cliente ve la procedencia sin datos personales. "
                 "Los eventos siguen el estándar EPCIS y no se borran: las correcciones se agregan como eventos nuevos. "
                 "El simulacro de retiro mide cuánto se tarda en rastrear un lote hasta sus clientes.")
        return Respuesta(texto, [("Consulta pública por código", _url("consulta"))], intencion="explicacion",
                         contexto={"explicacion": texto})

    def navegacion(self, q):
        from dashboard.areas import menu_para
        mejores = []
        for g in menu_para(self.user):
            for it in g["items"]:
                palabras = normalizar(it["texto"] + " " + g["nombre"]).split()
                puntos = sum(1 for p in palabras if len(p) > 3 and p in q)
                if puntos:
                    mejores.append((puntos, f"{g['nombre']} → {it['texto']}", it["url"]))
        mejores.sort(key=lambda x: -x[0])
        if not mejores:
            return Respuesta("No encontré ese módulo entre los que su cuenta puede abrir. Revise el menú de la izquierda: "
                             "está organizado en áreas numeradas.", intencion="navegacion")
        return Respuesta("Puede encontrarlo aquí:", [(t, u) for _p, t, u in mejores[:4]], intencion="navegacion")

    def _contexto_general(self):
        from dashboard.areas import menu_para
        return {"usuario": self.user.get_full_name() or self.user.username,
                "rol": getattr(getattr(self.user, "perfil", None), "rol_legible", ""),
                "modulos_permitidos": [f"{g['nombre']}: " + ", ".join(i["texto"] for i in g["items"]) for g in menu_para(self.user)]}


# ----------------------------------------------------------------------
# IA externa opcional
# ----------------------------------------------------------------------
SISTEMA = ("Eres el asistente de AgroTrace-UPEC, un sistema web de trazabilidad de productos hortofrutícolas de la "
           "Planta Hortofrutícola de la UPEC (Tulcán, Ecuador). Responde en español claro, en máximo 6 oraciones. "
           "Usa solo la información del CONTEXTO; si no está, dilo y sugiere el módulo del menú donde buscarla. "
           "Nunca inventes cantidades, códigos, nombres ni datos personales.")


def ia_configurada():
    return getattr(settings, "IA_PROVEEDOR", "ninguno") in ("anthropic", "openai") and bool(getattr(settings, "IA_MODELO", ""))


def consultar_ia(pregunta, contexto):
    """Devuelve el texto de la IA o None si no está disponible (sin romper el asistente)."""
    proveedor = settings.IA_PROVEEDOR
    mensaje = f"CONTEXTO (datos que el usuario puede ver):\n{json.dumps(contexto, ensure_ascii=False, default=str)[:6000]}\n\nPREGUNTA: {pregunta}"
    try:
        if proveedor == "anthropic":
            req = urllib.request.Request(
                (settings.IA_URL or "https://api.anthropic.com/v1").rstrip("/") + "/messages",
                data=json.dumps({"model": settings.IA_MODELO, "max_tokens": 500, "system": SISTEMA,
                                 "messages": [{"role": "user", "content": mensaje}]}).encode(),
                headers={"Content-Type": "application/json", "x-api-key": settings.IA_API_KEY, "anthropic-version": "2023-06-01"})
            with urllib.request.urlopen(req, timeout=settings.IA_TIEMPO) as r:
                datos = json.loads(r.read())
            return "".join(b.get("text", "") for b in datos.get("content", []) if b.get("type") == "text").strip() or None
        if proveedor == "openai":       # API compatible con OpenAI: Ollama, LM Studio, Groq, OpenAI, etc.
            cab = {"Content-Type": "application/json"}
            if settings.IA_API_KEY:
                cab["Authorization"] = f"Bearer {settings.IA_API_KEY}"
            req = urllib.request.Request(
                settings.IA_URL.rstrip("/") + "/chat/completions",
                data=json.dumps({"model": settings.IA_MODELO, "temperature": 0.2, "max_tokens": 500,
                                 "messages": [{"role": "system", "content": SISTEMA}, {"role": "user", "content": mensaje}]}).encode(),
                headers=cab)
            with urllib.request.urlopen(req, timeout=settings.IA_TIEMPO) as r:
                datos = json.loads(r.read())
            return (datos["choices"][0]["message"]["content"] or "").strip() or None
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError, OSError) as exc:
        log.warning("El proveedor de IA no respondió: %s", exc)
    return None
