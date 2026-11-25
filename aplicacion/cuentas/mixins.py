"""
Vistas genéricas seguras (listar, ver, crear, editar, eliminar, revisar) que usan todos los módulos.

Cada vista declara:
    modelo, area, form_class, columnas, campos_busqueda, filtros
y hereda los controles de acceso del servidor definidos en cuentas.permissions.
"""
from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import ProtectedError, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from . import permissions as perm
from .auditoria import diferencias, instantanea, registrar


# --------------------------------------------------------------------------
# Formularios
# --------------------------------------------------------------------------
class FormularioBase(forms.ModelForm):
    """Aplica estilos de Bootstrap y marca los campos obligatorios."""

    def __init__(self, *args, **kwargs):
        self.usuario = kwargs.pop("usuario", None)
        super().__init__(*args, **kwargs)
        for nombre, campo in self.fields.items():
            w = campo.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs["class"] = "form-check-input"
            elif isinstance(w, (forms.Select, forms.SelectMultiple)):
                w.attrs["class"] = "form-select"
            else:
                w.attrs["class"] = "form-control"
            if isinstance(w, forms.Textarea):
                w.attrs["rows"] = 2
            if isinstance(campo, forms.ModelChoiceField) and not isinstance(campo, forms.ModelMultipleChoiceField):
                campo.empty_label = "— Seleccione —"
            elif isinstance(campo, forms.ChoiceField) and campo.choices and campo.choices[0][0] in ("", None):
                campo.choices = [("", "— Seleccione —") if c[0] == "" else c for c in campo.choices]


FECHA = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
FECHA_HORA = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")


def operadores_del_area(area):
    return get_user_model().objects.filter(is_active=True, perfil__area__codigo=area).order_by("first_name")


# --------------------------------------------------------------------------
# Base de las vistas
# --------------------------------------------------------------------------
class VistaArea(LoginRequiredMixin, View):
    modelo = None
    area = None
    titulo = ""
    titulo_singular = ""
    url_base = ""          # prefijo de nombres de URL, p. ej. "productores:productor"
    plantilla_detalle = "comun/detalle.html"
    plantilla_form = "comun/formulario.html"
    form_class = None
    campos_detalle = []     # [(atributo, etiqueta)]
    campos_privados = []    # atributos que solo ve quien administra el área de productores
    permite_eliminar = True
    area_datos_privados = "productores"   # área que puede ver los campos privados

    def url(self, accion, *args):
        return reverse(f"{self.url_base}_{accion}", args=args)

    def contexto_base(self, **extra):
        ctx = {"titulo": self.titulo, "titulo_singular": self.titulo_singular, "area": self.area,
               "url_base": self.url_base, "permite_eliminar": self.permite_eliminar,
               "puede_crear": perm.puede(self.request.user, "crear", self.area)}
        ctx.update(extra)
        return ctx

    def obtener_para_consulta(self, pk):
        qs = perm.queryset_consulta(self.request.user, self.modelo.objects.all(), self.area)
        obj = qs.filter(pk=pk).first()
        if obj is None:
            existe = self.modelo.objects.filter(pk=pk).exists()
            perm.exigir(not existe, self.request, f"Intento de abrir {self.modelo._meta.verbose_name} #{pk} sin autorización")
            raise Http404
        return obj


class ListaView(VistaArea):
    columnas = []          # [(atributo, etiqueta)]
    campos_busqueda = []
    filtros = []           # [(campo, etiqueta, choices)]
    orden = None
    plantilla = "comun/lista.html"
    ayuda = ""

    def get(self, request):
        perm.exigir(perm.administra_area(request.user, self.area) or perm.area_de(request.user) == "reportes",
                    request, f"Acceso al listado de {self.titulo}")
        qs = perm.queryset_lista(request.user, self.modelo.objects.all(), self.area)
        q = request.GET.get("q", "").strip()
        if q and self.campos_busqueda:
            cond = Q()
            for c in self.campos_busqueda:
                cond |= Q(**{f"{c}__icontains": q})
            qs = qs.filter(cond)
        valores_filtro = {}
        for campo, _et, _ch in self.filtros:
            v = request.GET.get(campo, "")
            if v:
                qs = qs.filter(**{campo: v})
            valores_filtro[campo] = v
        if self.orden:
            qs = qs.order_by(*self.orden)
        if request.GET.get("exportar") == "csv":
            return self.exportar(qs)
        pagina = Paginator(qs, 15).get_page(request.GET.get("page"))
        filas = []
        for o in pagina:
            celdas = []
            for attr, _ in self.columnas:
                v = o
                for parte in attr.split("."):
                    v = getattr(v, parte, "")
                    v = v() if callable(v) else v
                celdas.append(v)
            filas.append({"obj": o, "celdas": celdas,
                          "editar": perm.puede_editar_obj(request.user, o, self.area)})
        params = request.GET.copy(); params.pop("page", None)
        return render(request, self.plantilla, self.contexto_base(
            filas=filas, pagina=pagina, encabezados=[c[1] for c in self.columnas], q=q,
            filtros=[(c, et, ch, valores_filtro.get(c, "")) for c, et, ch in self.filtros],
            params=params.urlencode(), ayuda=self.ayuda, total=qs.count(),
        ))


    def exportar(self, qs):
        """Exporta solo lo que el usuario ya puede ver en la lista, con las mismas columnas."""
        import csv
        from django.http import HttpResponse
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{self.url_base.split(":")[-1]}s.csv"'
        resp.write("\ufeff")
        w = csv.writer(resp, delimiter=";")
        w.writerow([c[1] for c in self.columnas])
        n = 0
        for o in qs:
            fila = []
            for attr, _ in self.columnas:
                v = o
                for parte in attr.split("."):
                    v = getattr(v, parte, "")
                    v = v() if callable(v) else v
                fila.append("" if v is None else v)
            w.writerow(fila); n += 1
        registrar(self.request, "exportar", detalle=f"Exportó {n} registros de {self.titulo}")
        return resp


class DetalleView(VistaArea):
    def extra_detalle(self, obj):
        return {}

    def get(self, request, pk):
        obj = self.obtener_para_consulta(pk)
        ver_privado = perm.administra_area(request.user, self.area_datos_privados) and (
            perm.es_admin(request.user) or perm.es_responsable(request.user, obj) or self.area_datos_privados != self.area)
        campos = []
        for attr, etiqueta in self.campos_detalle:
            if attr in self.campos_privados and not ver_privado:
                continue
            v = obj
            for parte in attr.split("."):
                v = getattr(v, parte, "")
                v = v() if callable(v) else v
            campos.append((etiqueta, v))
        ctx = self.contexto_base(
            obj=obj, campos=campos,
            puede_editar=perm.puede_editar_obj(request.user, obj, self.area),
            puede_eliminar=perm.puede_eliminar_obj(request.user, obj, self.area),
            es_admin=perm.es_admin(request.user),
            solo_consulta=not perm.administra_area(request.user, self.area) or not perm.es_responsable(request.user, obj),
        )
        ctx.update(self.extra_detalle(obj))
        return render(request, self.plantilla_detalle, ctx)


class FormularioView(VistaArea):
    """Lógica común de crear y editar."""
    ayuda = ""

    def preparar_form(self, form, obj=None):
        u = self.request.user
        # El responsable lo asigna el servidor. Solo el administrador puede elegirlo.
        if perm.es_admin(u):
            form.fields["responsable_asignado"] = forms.ModelChoiceField(
                label="Operador responsable", required=False,
                queryset=operadores_del_area(self.area), empty_label="— Yo mismo —",
                initial=obj.responsable_id if obj else None,
                help_text="Déjelo vacío para quedar usted como responsable.",
                widget=forms.Select(attrs={"class": "form-select"}))
            if obj is not None and obj.responsable_id != u.id:
                form.fields["justificacion"] = forms.CharField(
                    label="Justificación de la modificación administrativa", max_length=250,
                    widget=forms.TextInput(attrs={"class": "form-control"}),
                    help_text="Obligatoria: el registro pertenece a otro operador. Quedará en la auditoría.")
        return form

    def render_form(self, form, obj=None):
        return render(self.request, self.plantilla_form, self.contexto_base(
            form=form, obj=obj, ayuda=self.ayuda,
            volver=self.url("detalle", obj.pk) if obj else self.url("lista")))

    def antes_de_guardar(self, form, obj, creando):
        """Para validaciones o ajustes propios de cada módulo."""

    def despues_de_guardar(self, obj, creando):
        """Para crear eventos de trazabilidad u otras acciones."""

    def guardar(self, form, creando, antes=None):
        u = self.request.user
        obj = form.save(commit=False)
        if creando:
            obj.responsable = u
        if perm.es_admin(u) and form.cleaned_data.get("responsable_asignado"):
            obj.responsable = form.cleaned_data["responsable_asignado"]
        if not creando and not perm.es_admin(u):
            obj.estado_revision = "pendiente"  # un cambio vuelve a requerir revisión
        self.antes_de_guardar(form, obj, creando)
        with transaction.atomic():
            obj.save()
            form.save_m2m()
            self.despues_de_guardar(obj, creando)
        if creando:
            registrar(self.request, "crear", obj, detalle=f"Nuevo registro en {self.titulo}")
        else:
            registrar(self.request, "editar", obj, cambios=diferencias(antes, instantanea(obj)),
                      justificacion=form.cleaned_data.get("justificacion", ""))
        return obj


class CrearView(FormularioView):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            perm.exigir(perm.puede(request.user, "crear", self.area), request,
                        f"Intento de crear en {self.titulo} sin permiso")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        initial = {k: v for k, v in request.GET.items()}
        form = self.preparar_form(self.form_class(initial=initial, usuario=request.user))
        return self.render_form(form)

    def post(self, request):
        form = self.preparar_form(self.form_class(request.POST, request.FILES, usuario=request.user))
        if form.is_valid():
            obj = self.guardar(form, creando=True)
            messages.success(request, f"{self.titulo_singular} «{obj}» registrado correctamente.")
            return redirect(self.url("detalle", obj.pk))
        messages.error(request, "Revise los campos marcados en rojo.")
        return self.render_form(form)


class EditarView(FormularioView):
    def objeto(self, pk):
        obj = get_object_or_404(self.modelo, pk=pk)
        perm.exigir(perm.puede_editar_obj(self.request.user, obj, self.area), self.request,
                    f"Intento de editar {self.modelo._meta.verbose_name} #{pk} de otro operador")
        return obj

    def get(self, request, pk):
        obj = self.objeto(pk)
        return self.render_form(self.preparar_form(self.form_class(instance=obj, usuario=request.user), obj), obj)

    def post(self, request, pk):
        obj = self.objeto(pk)
        antes = instantanea(obj)
        form = self.preparar_form(self.form_class(request.POST, request.FILES, instance=obj, usuario=request.user), obj)
        if form.is_valid():
            obj = self.guardar(form, creando=False, antes=antes)
            messages.success(request, f"{self.titulo_singular} «{obj}» actualizado.")
            return redirect(self.url("detalle", obj.pk))
        messages.error(request, "Revise los campos marcados en rojo.")
        return self.render_form(form, obj)


class EliminarView(VistaArea):
    def objeto(self, pk):
        obj = get_object_or_404(self.modelo, pk=pk)
        perm.exigir(perm.puede_eliminar_obj(self.request.user, obj, self.area), self.request,
                    f"Intento de eliminar {self.modelo._meta.verbose_name} #{pk} sin permiso")
        return obj

    def get(self, request, pk):
        obj = self.objeto(pk)
        return render(request, "comun/confirmar_eliminar.html", self.contexto_base(obj=obj, volver=self.url("detalle", pk)))

    def post(self, request, pk):
        obj = self.objeto(pk)
        datos = instantanea(obj)
        texto = str(obj)
        try:
            with transaction.atomic():
                registrar(request, "eliminar", obj, cambios={"registro_eliminado": datos},
                          justificacion=request.POST.get("justificacion", ""))
                obj.delete()
        except ProtectedError:
            messages.error(request, f"No se puede eliminar «{texto}» porque otros registros dependen de él "
                                    "(por ejemplo, cosechas o lotes). Puede marcarlo como inactivo.")
            return redirect(self.url("detalle", pk))
        messages.success(request, f"«{texto}» fue eliminado.")
        return redirect(self.url("lista"))


class RevisarView(VistaArea):
    """El administrador general aprueba u observa un registro."""

    def post(self, request, pk):
        perm.exigir(perm.es_admin(request.user), request, "Intento de revisar un registro sin ser administrador")
        obj = get_object_or_404(self.modelo, pk=pk)
        estado = request.POST.get("estado")
        if estado in ("aprobado", "observado"):
            obj.estado_revision = estado
            obj.revisado_por = request.user
            obj.revisado_en = timezone.now()
            obj.nota_revision = request.POST.get("nota", "")[:200]
            obj.save(update_fields=["estado_revision", "revisado_por", "revisado_en", "nota_revision"])
            registrar(request, "revisar", obj, detalle=f"Registro {obj.get_estado_revision_display().lower()}",
                      justificacion=obj.nota_revision)
            messages.success(request, f"Registro {obj.get_estado_revision_display().lower()}.")
        return redirect(self.url("detalle", pk))


def crud_urls(prefijo, lista, detalle, crear, editar, eliminar=None, revisar=None):
    """Genera las rutas estándar de un módulo."""
    from django.urls import path
    rutas = [
        path("", lista.as_view(), name=f"{prefijo}_lista"),
        path("nuevo/", crear.as_view(), name=f"{prefijo}_crear"),
        path("<int:pk>/", detalle.as_view(), name=f"{prefijo}_detalle"),
        path("<int:pk>/editar/", editar.as_view(), name=f"{prefijo}_editar"),
    ]
    if eliminar:
        rutas.append(path("<int:pk>/eliminar/", eliminar.as_view(), name=f"{prefijo}_eliminar"))
    if revisar:
        rutas.append(path("<int:pk>/revisar/", revisar.as_view(), name=f"{prefijo}_revisar"))
    return rutas
