"""Funciones para registrar acciones en la bitácora de auditoría."""
from decimal import Decimal

from django.db.models import Model
from django.forms.models import model_to_dict

from .models import RegistroAuditoria


def _ip(request):
    if request is None:
        return None
    ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR")
    return ip or None


def _area(user):
    p = getattr(user, "perfil", None)
    if p is None:
        return ""
    return "Administración general" if p.es_admin_general or user.is_superuser else (p.area.nombre if p.area else "")


def _serializable(v):
    if isinstance(v, Model):
        return str(v)
    if isinstance(v, (list, tuple, set)):
        return [_serializable(x) for x in v]
    if isinstance(v, Decimal):
        return str(v)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if hasattr(v, "name") and hasattr(v, "url"):  # archivos
        return v.name or ""
    return v


def instantanea(obj):
    """Copia de los valores de un registro, para conservar el estado anterior en la auditoría."""
    datos = model_to_dict(obj)
    return {k: _serializable(v) for k, v in datos.items()}


def diferencias(antes, despues):
    return {k: {"antes": antes.get(k), "despues": v} for k, v in despues.items() if antes.get(k) != v}


def registrar(request, accion, obj=None, detalle="", cambios=None, justificacion="", usuario=None):
    user = usuario or (request.user if request is not None and request.user.is_authenticated else None)
    RegistroAuditoria.objects.create(
        usuario=user,
        usuario_nombre=(user.get_full_name() or user.get_username()) if user else "Anónimo",
        area=_area(user) if user else "",
        accion=accion,
        modulo=obj._meta.verbose_name.capitalize() if obj is not None else "",
        objeto_id=str(obj.pk) if obj is not None and obj.pk else "",
        objeto=str(obj)[:200] if obj is not None else "",
        detalle=detalle[:2000],
        cambios=cambios or {},
        justificacion=justificacion[:250],
        ip=_ip(request),
    )
