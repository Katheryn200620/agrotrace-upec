import datetime
from decimal import Decimal

from django import template
from django.contrib.auth import get_user_model
from django.db.models.fields.files import FieldFile
from django.utils import formats, timezone
from django.utils.html import format_html

register = template.Library()

VERDES = {"Activo", "Aprobado", "Entregado", "Sí", "Extra", "Primera", "En almacenamiento", "Sembrado", "En desarrollo", "En cosecha"}
AZULES = {"En transporte", "En tránsito", "Programado", "En proceso", "Despacho", "Pendiente de revisión"}
AMBAR = {"Observado", "Segunda", "Agotado", "En preparación", "En descanso", "Inactivo", "Cosechado"}
ROJOS = {"Retirado del mercado", "Rechazo", "Cancelado", "No"}


@register.filter
def valor(v):
    """Presenta cualquier valor de forma legible en español."""
    if v is None or v == "":
        return "–"
    if v is True:
        return "Sí"
    if v is False:
        return "No"
    if isinstance(v, datetime.datetime):
        return formats.date_format(timezone.localtime(v), "d/m/Y H:i")
    if isinstance(v, datetime.date):
        return formats.date_format(v, "d/m/Y")
    if isinstance(v, Decimal):
        return formats.number_format(v.normalize() if v == v.to_integral() else v, use_l10n=True)
    if isinstance(v, FieldFile):
        return format_html('<a href="{}" target="_blank">Ver archivo</a>', v.url) if v else "–"
    if isinstance(v, get_user_model()):
        return v.get_full_name() or v.get_username()
    return v


@register.filter
def etiqueta(v):
    """Etiqueta de estado discreta según el texto."""
    texto = valor(v)
    clase = "etq-verde" if texto in VERDES else "etq-azul" if texto in AZULES else "etq-ambar" if texto in AMBAR \
        else "etq-rojo" if texto in ROJOS else ""
    if not clase:
        return texto
    return format_html('<span class="etq {}">{}</span>', clase, texto)


@register.filter
def iniciales(u):
    n = (u.get_full_name() or u.get_username()).split()
    return "".join(x[0] for x in n[:2]).upper()


ICONOS = {"cultivo": "bi-flower2", "cosecha": "bi-basket", "recepcion": "bi-box-arrow-in-down", "clasificacion": "bi-camera",
          "creacion_lote": "bi-box-seam", "empaque": "bi-box2", "almacenamiento": "bi-thermometer-snow",
          "transformacion": "bi-gear", "division": "bi-scissors", "combinacion": "bi-intersect", "despacho": "bi-truck",
          "transporte": "bi-signpost-split", "recepcion_destino": "bi-shop", "retiro": "bi-exclamation-octagon",
          "correccion": "bi-pencil-square"}


@register.filter
def icono_evento(tipo):
    return ICONOS.get(tipo, "bi-dot")


@register.simple_tag(takes_context=True)
def url_con(context, **kwargs):
    """Conserva los filtros actuales de la URL y cambia los indicados."""
    q = context["request"].GET.copy()
    for k, v in kwargs.items():
        q[k] = v
    return "?" + q.urlencode()


@register.filter
def es_activo(ruta, url):
    """Marca el enlace del menú de la página actual (lista, detalle o formulario de ese módulo)."""
    if ruta == url:
        return True
    if not ruta.startswith(url):
        return False
    primero = ruta[len(url):].split("/")[0]
    return primero.isdigit() or primero in ("nuevo", "nueva")


@register.filter
def grupo_activo(items, ruta):
    """¿Alguno de los enlaces del grupo corresponde a la página actual?"""
    return any(es_activo(ruta, it["url"]) for it in items)
