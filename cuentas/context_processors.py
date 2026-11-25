"""Menú lateral por áreas y contador de alertas: cada usuario ve solo lo que tiene autorizado."""
from django.core.cache import cache

from . import permissions as perm


def menu(request):
    u = request.user
    if not u.is_authenticated:
        return {}
    from dashboard.areas import menu_para
    p = getattr(u, "perfil", None)
    admin = perm.es_admin(u)
    clave = f"alertas-{u.pk}"
    n = cache.get(clave)
    if n is None:
        try:
            from dashboard.indicadores import alertas
            n = len(alertas(u))
        except Exception:  # el menú nunca debe romper la página
            n = 0
        cache.set(clave, n, 60)
    return {
        "menu_grupos": menu_para(u),
        "es_admin_general": admin,
        "area_usuario": "Administración general" if admin else (p.area.nombre if p and p.area else ""),
        "rol_usuario": p.rol_legible if p else "",
        "n_alertas": n,
    }
