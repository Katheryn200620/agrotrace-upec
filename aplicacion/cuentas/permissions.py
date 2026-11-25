"""
Reglas de autorización de AgroTrace-UPEC. Se aplican en el servidor, en todas las vistas.

Principios:
1. El administrador general ve y administra todo (sus cambios sobre registros ajenos se justifican y auditan).
2. Cada operador administra SOLO su área y SOLO los registros de los que es responsable.
3. Un operador puede CONSULTAR (sin editar) datos compartidos de otras áreas que necesita para su trabajo.
4. Los datos personales de productores solo los ven el área de productores y el administrador general.
"""
from django.core.exceptions import PermissionDenied

from .models import Area

# Qué áreas puede consultar (solo lectura) cada área, para completar su trabajo.
CONSULTA_COMPARTIDA = {
    Area.PRODUCTORES: set(),
    Area.PARCELAS: {Area.PRODUCTORES, Area.PRODUCTOS},
    Area.PRODUCTOS: set(),
    Area.COSECHAS: {Area.PRODUCTORES, Area.PARCELAS, Area.PRODUCTOS},
    Area.LOTES: {Area.PRODUCTORES, Area.PARCELAS, Area.PRODUCTOS, Area.COSECHAS, Area.TRAZABILIDAD},
    Area.TRAZABILIDAD: {Area.PRODUCTORES, Area.PARCELAS, Area.PRODUCTOS, Area.COSECHAS, Area.LOTES, Area.TRANSPORTE},
    Area.TRANSPORTE: {Area.PRODUCTOS, Area.LOTES, Area.TRAZABILIDAD, Area.COMERCIAL},
    Area.COMERCIAL: {Area.PRODUCTOS, Area.LOTES, Area.TRAZABILIDAD, Area.TRANSPORTE},
    Area.REPORTES: {c for c, _ in Area.CODIGOS},
}


def perfil(user):
    return getattr(user, "perfil", None) if user and user.is_authenticated else None


def es_admin(user):
    if not user or not user.is_authenticated or not user.is_active:
        return False
    p = perfil(user)
    return user.is_superuser or bool(p and p.es_admin_general)


def area_de(user):
    """Código del área asignada (solo si el área está activa)."""
    p = perfil(user)
    if p and p.area and p.area.activa and user.is_active:
        return p.area.codigo
    return None


def administra_area(user, area):
    return es_admin(user) or area_de(user) == area


def consulta_area(user, area):
    if es_admin(user):
        return True
    propia = area_de(user)
    return propia is not None and (propia == area or area in CONSULTA_COMPARTIDA.get(propia, set()))


def puede(user, accion, area):
    """accion: crear | editar | eliminar."""
    if es_admin(user):
        return True
    if area_de(user) != area or area == Area.REPORTES:
        return False
    p = perfil(user)
    return bool(getattr(p, f"puede_{accion}", False))


def es_responsable(user, obj):
    return getattr(obj, "responsable_id", None) == user.id


def puede_editar_obj(user, obj, area):
    return es_admin(user) or (puede(user, "editar", area) and es_responsable(user, obj))


def puede_eliminar_obj(user, obj, area):
    return es_admin(user) or (puede(user, "eliminar", area) and es_responsable(user, obj))


def ve_datos_personales(user):
    return administra_area(user, Area.PRODUCTORES)


def queryset_lista(user, qs, area):
    """Registros que el usuario puede ver en el listado de un área."""
    if es_admin(user) or area_de(user) == Area.REPORTES:
        return qs
    if area_de(user) == area:
        return qs.filter(responsable=user)
    return qs.none()


def queryset_consulta(user, qs, area):
    """Registros que el usuario puede abrir (solo lectura): los suyos o los de áreas compartidas."""
    if es_admin(user):
        return qs
    if area_de(user) == area:
        return qs.filter(responsable=user)
    if consulta_area(user, area):
        return qs
    return qs.none()


def exigir(condicion, request=None, detalle=""):
    """Lanza 403 y deja constancia en la auditoría."""
    if not condicion:
        if request is not None:
            from .auditoria import registrar
            registrar(request, "acceso_denegado", detalle=detalle or request.path)
        raise PermissionDenied("No tiene permiso para realizar esta acción.")   # el detalle queda solo en la auditoría
