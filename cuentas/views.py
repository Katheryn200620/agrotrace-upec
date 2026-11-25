from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import permissions as perm
from .auditoria import registrar
from .forms import CambioClaveForm, IngresoForm, UsuarioForm
from .models import Area, RegistroAuditoria

User = get_user_model()


class Ingreso(LoginView):
    template_name = "registration/login.html"
    authentication_form = IngresoForm
    redirect_authenticated_user = True


def _solo_admin(request):
    perm.exigir(perm.es_admin(request.user), request, "Acceso a la administración de usuarios")


@login_required
def perfil(request):
    form = CambioClaveForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        update_session_auth_hash(request, form.user)
        registrar(request, "cuenta", request.user, detalle="Cambio de contraseña propia")
        messages.success(request, "Contraseña actualizada.")
        return redirect("cuentas:perfil")
    return render(request, "cuentas/perfil.html", {"form": form, "titulo": "Mi perfil"})


@login_required
def mi_historial(request):
    qs = RegistroAuditoria.objects.filter(usuario=request.user)
    return render(request, "cuentas/auditoria.html", {
        "pagina": Paginator(qs, 25).get_page(request.GET.get("page")), "titulo": "Mi historial de acciones", "propio": True})


# ---------------------------------------------------------------------------
# Administración de cuentas (solo administrador general)
# ---------------------------------------------------------------------------
@login_required
def usuarios(request):
    _solo_admin(request)
    qs = User.objects.select_related("perfil__area").order_by("-is_active", "perfil__area__id", "username")
    q = request.GET.get("q", "")
    if q:
        qs = qs.filter(username__icontains=q) | qs.filter(first_name__icontains=q) | qs.filter(last_name__icontains=q)
    return render(request, "cuentas/usuarios.html", {"usuarios": qs, "q": q, "titulo": "Usuarios y permisos",
                                                     "areas": Area.objects.all()})


def _guardar_usuario(request, form, u=None):
    d = form.cleaned_data
    creando = u is None
    with transaction.atomic():
        if creando:
            u = User(username=d["username"])
        antes = None if creando else {"area": str(u.perfil.area or ""), "admin": u.perfil.es_admin_general,
                                      "crear": u.perfil.puede_crear, "editar": u.perfil.puede_editar,
                                      "eliminar": u.perfil.puede_eliminar}
        u.username, u.first_name, u.last_name, u.email = d["username"], d["first_name"], d["last_name"], d["email"]
        u.is_staff = d["es_admin_general"]
        if d.get("password1"):
            u.set_password(d["password1"])
        u.save()
        p = u.perfil
        p.es_admin_general = d["es_admin_general"]
        p.area = None if d["es_admin_general"] else d["area"]
        p.puede_crear, p.puede_editar, p.puede_eliminar = d["puede_crear"], d["puede_editar"], d["puede_eliminar"]
        p.cargo = d["cargo"]
        p.actualizado_por = request.user
        p.save()
        despues = {"area": str(p.area or ""), "admin": p.es_admin_general, "crear": p.puede_crear,
                   "editar": p.puede_editar, "eliminar": p.puede_eliminar}
        registrar(request, "cuenta", u, detalle="Cuenta creada" if creando else "Cuenta modificada",
                  cambios={} if creando else {k: {"antes": antes[k], "despues": v} for k, v in despues.items() if antes[k] != v})
    return u


@login_required
def usuario_crear(request):
    _solo_admin(request)
    form = UsuarioForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        u = _guardar_usuario(request, form)
        messages.success(request, f"Cuenta «{u.username}» creada.")
        return redirect("cuentas:usuarios")
    return render(request, "cuentas/usuario_form.html", {"form": form, "titulo": "Nueva cuenta"})


@login_required
def usuario_editar(request, pk):
    _solo_admin(request)
    u = get_object_or_404(User.objects.select_related("perfil"), pk=pk)
    p = u.perfil
    inicial = {"username": u.username, "first_name": u.first_name, "last_name": u.last_name, "email": u.email,
               "cargo": p.cargo, "es_admin_general": p.es_admin_general, "area": p.area,
               "puede_crear": p.puede_crear, "puede_editar": p.puede_editar, "puede_eliminar": p.puede_eliminar}
    form = UsuarioForm(request.POST or None, initial=inicial, usuario=u)
    if request.method == "POST" and form.is_valid():
        if u == request.user and not form.cleaned_data["es_admin_general"]:
            messages.error(request, "No puede quitarse a sí mismo el rol de administrador general.")
        else:
            _guardar_usuario(request, form, u)
            messages.success(request, f"Cuenta «{u.username}» actualizada.")
            return redirect("cuentas:usuarios")
    return render(request, "cuentas/usuario_form.html", {"form": form, "titulo": f"Editar cuenta: {u.username}", "cuenta": u})


@login_required
@require_POST
def usuario_activar(request, pk):
    """Las cuentas no se eliminan: se desactivan y conservan su historial."""
    _solo_admin(request)
    u = get_object_or_404(User, pk=pk)
    if u == request.user:
        messages.error(request, "No puede desactivar su propia cuenta.")
    else:
        u.is_active = not u.is_active
        u.save(update_fields=["is_active"])
        registrar(request, "cuenta", u, detalle="Cuenta activada" if u.is_active else "Cuenta desactivada")
        messages.success(request, f"Cuenta «{u.username}» {'activada' if u.is_active else 'desactivada'}.")
    return redirect("cuentas:usuarios")


@login_required
@require_POST
def area_activar(request, pk):
    _solo_admin(request)
    a = get_object_or_404(Area, pk=pk)
    a.activa = not a.activa
    a.save(update_fields=["activa"])
    registrar(request, "cuenta", a, detalle=f"Área {'habilitada' if a.activa else 'deshabilitada'}")
    messages.success(request, f"Área «{a.nombre}» {'habilitada' if a.activa else 'deshabilitada'}.")
    return redirect("cuentas:usuarios")


@login_required
def auditoria(request):
    _solo_admin(request)
    qs = RegistroAuditoria.objects.select_related("usuario")
    f = {k: request.GET.get(k, "") for k in ("usuario", "accion", "desde", "hasta")}
    if f["usuario"]:
        qs = qs.filter(usuario_nombre__icontains=f["usuario"])
    if f["accion"]:
        qs = qs.filter(accion=f["accion"])
    if f["desde"]:
        qs = qs.filter(fecha__date__gte=f["desde"])
    if f["hasta"]:
        qs = qs.filter(fecha__date__lte=f["hasta"])
    return render(request, "cuentas/auditoria.html", {
        "pagina": Paginator(qs, 25).get_page(request.GET.get("page")), "titulo": "Auditoría del sistema",
        "f": f, "acciones": RegistroAuditoria.ACCIONES})
