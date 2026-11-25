"""Bloquea a usuarios desactivados y a operadores sin área, aunque tengan una sesión abierta."""
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect

from .permissions import area_de, es_admin

RUTAS_LIBRES = ("/ingresar/", "/salir/", "/static/", "/media/", "/01/", "/consulta/")


class UsuarioActualMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        u = request.user
        if u.is_authenticated and not request.path.startswith(RUTAS_LIBRES):
            if not u.is_active:
                logout(request)
                return redirect("login")
            if not es_admin(u) and area_de(u) is None:
                logout(request)
                messages.error(request, "Su cuenta no tiene un área de trabajo activa. Comuníquese con el administrador general.")
                return redirect("login")
        return self.get_response(request)
