"""
API REST v1 de AgroTrace-UPEC.

- Autenticación: sesión del navegador o token (POST /api/v1/token/ con usuario y contraseña).
- Autorización: las mismas reglas de cuentas/permissions.py que usa la web.
  · Listar: el administrador y el área de consulta ven todo; el operador ve sus propios registros.
  · Consultar uno: además, lo que su área puede consultar (consulta compartida).
  · Crear, modificar y eliminar: solo con permiso en su área y sobre sus propios registros.
- Validación: las altas y cambios pasan por los mismos formularios y vistas de la web,
  así la API no puede saltarse reglas (stock, procedencia, fechas, eventos y auditoría).
"""
from django.db import transaction
from django.db.models import ProtectedError, Q
from django.forms.models import model_to_dict
from django.shortcuts import get_object_or_404, render
from rest_framework import status, viewsets
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from comercial import views as cv
from comercial.models import Cliente, Venta
from cosechas import views as cosv
from cosechas.models import Clasificacion, Cosecha, Recepcion
from cuentas import permissions as perm
from cuentas.auditoria import instantanea, registrar
from cuentas.models import Area
from lotes import views as lv
from lotes.models import Lote
from parcelas import views as pv
from parcelas.models import Labor, Parcela
from productores import views as prv
from productores.models import Productor
from productos import views as pdv
from productos.models import Producto
from trazabilidad.models import EventoTrazabilidad
from transporte import views as tv
from transporte.models import Despacho, Transportista

from . import serializers as s


class Paginacion(PageNumberPagination):
    page_size = 25
    page_size_query_param = "tamano"
    max_page_size = 200


class ModuloViewSet(viewsets.ViewSet):
    """Operaciones estándar de un módulo con las reglas del área."""
    modelo = None
    area = None
    serializer = None
    vista_crear = None
    vista_editar = None
    vista_eliminar = None
    busqueda = []
    filtros = []           # parámetros de consulta permitidos: ?campo=valor

    # ---- utilidades ----
    def _vista(self, clase):
        v = clase()
        v.request = self.request._request
        v.args, v.kwargs = (), {}
        return v

    def _ser(self, obj, many=False):
        return self.serializer(obj, many=many, context={"request": self.request}).data

    def _con_valores_por_defecto(self, form_class, recibido):
        """Completa los campos omitidos con el valor por defecto del modelo (como hace el formulario web)."""
        from django.db.models import NOT_PROVIDED
        datos = dict(recibido.items()) if hasattr(recibido, "items") else {}
        if hasattr(recibido, "getlist"):
            datos = {k: (recibido.getlist(k) if len(recibido.getlist(k)) > 1 else recibido.get(k)) for k in recibido}
        for nombre in form_class._meta.fields:
            if nombre in datos:
                continue
            try:
                campo = self.modelo._meta.get_field(nombre)
            except Exception:
                continue
            if getattr(campo, "default", NOT_PROVIDED) is not NOT_PROVIDED:
                v = campo.default() if callable(campo.default) else campo.default
                if hasattr(v, "isoformat") and not isinstance(v, bool):
                    v = v.isoformat()
                datos[nombre] = v
        return datos

    def _errores(self, form):
        raise ValidationError({k: [str(e) for e in v] for k, v in form.errors.items()})

    # ---- lectura ----
    def list(self, request):
        u = request.user
        perm.exigir(perm.administra_area(u, self.area) or perm.area_de(u) == Area.REPORTES, request._request,
                    f"API: listado de {self.modelo._meta.verbose_name_plural}")
        qs = perm.queryset_lista(u, self.modelo.objects.all(), self.area)
        q = request.query_params.get("q", "").strip()
        if q and self.busqueda:
            cond = Q()
            for c in self.busqueda:
                cond |= Q(**{f"{c}__icontains": q})
            qs = qs.filter(cond)
        for f in self.filtros:
            v = request.query_params.get(f)
            if v not in (None, ""):
                qs = qs.filter(**{f: v})
        pag = Paginacion()
        pagina = pag.paginate_queryset(qs.order_by(*(self.modelo._meta.ordering or ["-id"])), request, view=self)
        return pag.get_paginated_response(self._ser(pagina, many=True))

    def retrieve(self, request, pk=None):
        qs = perm.queryset_consulta(request.user, self.modelo.objects.all(), self.area)
        obj = qs.filter(pk=pk).first()
        if obj is None:
            perm.exigir(not self.modelo.objects.filter(pk=pk).exists(), request._request,
                        f"API: intento de abrir {self.modelo._meta.verbose_name} #{pk} sin autorización")
            return Response({"detail": "No encontrado."}, status=404)
        return Response(self._ser(obj))

    # ---- escritura ----
    def create(self, request):
        if self.vista_crear is None:
            return Response({"detail": "Este recurso es de solo lectura en la API."}, status=405)
        perm.exigir(perm.puede(request.user, "crear", self.area), request._request, f"API: crear en {self.area} sin permiso")
        vista = self._vista(self.vista_crear)
        datos = self._con_valores_por_defecto(vista.form_class, request.data)
        form = vista.preparar_form(vista.form_class(data=datos, files=request.FILES, usuario=request.user))
        if not form.is_valid():
            self._errores(form)
        try:
            with transaction.atomic():
                obj = vista.guardar(form, creando=True)
        except ValueError as exc:
            raise ValidationError({"detail": f"No se pudo guardar: {exc}. Revise la disponibilidad."})
        return Response(self._ser(obj), status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        if self.vista_editar is None:
            return Response({"detail": "Este recurso no se modifica por la API."}, status=405)
        obj = get_object_or_404(self.modelo, pk=pk)
        perm.exigir(perm.puede_editar_obj(request.user, obj, self.area), request._request,
                    f"API: intento de modificar {self.modelo._meta.verbose_name} #{pk} sin permiso")
        vista = self._vista(self.vista_editar)
        campos = list(vista.form_class._meta.fields)
        datos = {k: v for k, v in model_to_dict(obj, fields=campos).items()}
        for k, v in list(datos.items()):          # relaciones muchos a muchos como lista de ids
            if isinstance(v, list):
                datos[k] = [getattr(x, "pk", x) for x in v]
        datos.update(request.data)
        antes = instantanea(obj)
        form = vista.preparar_form(vista.form_class(data=datos, files=request.FILES, instance=obj, usuario=request.user), obj)
        if not form.is_valid():
            self._errores(form)
        obj = vista.guardar(form, creando=False, antes=antes)
        return Response(self._ser(obj))

    update = partial_update

    def destroy(self, request, pk=None):
        obj = get_object_or_404(self.modelo, pk=pk)
        if self.vista_eliminar is None:
            return Response({"detail": "Este recurso no se elimina: se anula o se corrige."}, status=405)
        perm.exigir(perm.puede_eliminar_obj(request.user, obj, self.area), request._request,
                    f"API: intento de eliminar {self.modelo._meta.verbose_name} #{pk} sin permiso")
        datos = instantanea(obj)
        try:
            with transaction.atomic():
                registrar(request._request, "eliminar", obj, cambios={"registro_eliminado": datos}, detalle="Eliminado por la API")
                obj.delete()
        except ProtectedError:
            return Response({"detail": "Otros registros dependen de este. Márquelo como inactivo."}, status=409)
        return Response(status=204)


def modulo(nombre, modelo_, area_, ser, crear=None, editar=None, eliminar=None, busqueda=(), filtros=()):
    return type(nombre, (ModuloViewSet,), {"modelo": modelo_, "area": area_, "serializer": ser, "vista_crear": crear,
                                           "vista_editar": editar, "vista_eliminar": eliminar, "busqueda": list(busqueda),
                                           "filtros": list(filtros)})


Productores = modulo("Productores", Productor, Area.PRODUCTORES, s.ProductorSerializer, prv.Crear, prv.Editar, prv.Eliminar,
                     ["codigo", "nombre", "canton"], ["estado", "tipo"])
Parcelas = modulo("Parcelas", Parcela, Area.PARCELAS, s.ParcelaSerializer, pv.ParcelaCrear, pv.ParcelaEditar, pv.ParcelaEliminar,
                  ["codigo", "nombre"], ["productor", "cultivo", "estado_cultivo"])
Labores = modulo("Labores", Labor, Area.PARCELAS, s.LaborSerializer, pv.LaborCrear, pv.LaborEditar, pv.LaborEliminar,
                 ["insumo", "descripcion"], ["parcela", "tipo"])
Productos = modulo("Productos", Producto, Area.PRODUCTOS, s.ProductoSerializer, pdv.Crear, pdv.Editar, pdv.Eliminar,
                   ["codigo", "nombre", "gtin"], ["categoria", "estado"])
Cosechas = modulo("Cosechas", Cosecha, Area.COSECHAS, s.CosechaSerializer, cosv.CosechaCrear, cosv.CosechaEditar,
                  cosv.CosechaEliminar, ["codigo"], ["parcela", "producto", "productor"])
Recepciones = modulo("Recepciones", Recepcion, Area.COSECHAS, s.RecepcionSerializer, cosv.RecepcionCrear, cosv.RecepcionEditar,
                     cosv.RecepcionEliminar, ["cosecha__codigo"], ["cosecha"])
Clasificaciones = modulo("Clasificaciones", Clasificacion, Area.COSECHAS, s.ClasificacionSerializer, cosv.ClasificacionCrear,
                         cosv.ClasificacionEditar, cosv.ClasificacionEliminar, ["causa_rechazo"], ["recepcion", "categoria"])
Lotes = modulo("Lotes", Lote, Area.LOTES, s.LoteSerializer, lv.Crear, lv.Editar, None, ["codigo"], ["producto", "estado", "categoria"])
Transportistas = modulo("Transportistas", Transportista, Area.TRANSPORTE, s.TransportistaSerializer, tv.TCrear, tv.TEditar,
                        tv.TEliminar, ["nombre", "vehiculo_placa"], ["activo"])
Despachos = modulo("Despachos", Despacho, Area.TRANSPORTE, s.DespachoSerializer, tv.DCrear, tv.DEditar, None,
                   ["codigo", "destino", "lote__codigo"], ["estado", "lote", "venta"])
Clientes = modulo("Clientes", Cliente, Area.COMERCIAL, s.ClienteSerializer, cv.CCrear, cv.CEditar, cv.CEliminar,
                  ["codigo", "nombre", "ciudad"], ["tipo", "activo"])
Ventas = modulo("Ventas", Venta, Area.COMERCIAL, s.VentaSerializer, cv.VCrear, cv.VEditar, None,
                ["codigo", "cliente__nombre", "lote__codigo"], ["estado", "cliente", "lote", "canal"])


class Eventos(viewsets.ViewSet):
    """Historial de trazabilidad: solo lectura (los eventos no se modifican)."""

    def _qs(self, u):
        qs = EventoTrazabilidad.objects.select_related("lote", "cosecha").order_by("-fecha_hora", "-id")
        if perm.es_admin(u) or perm.area_de(u) in (Area.TRAZABILIDAD, Area.REPORTES):
            return qs
        return qs.filter(responsable=u)

    def list(self, request):
        qs = self._qs(request.user)
        for p, campo in (("lote", "lote__codigo"), ("cosecha", "cosecha__codigo"), ("tipo", "tipo")):
            v = request.query_params.get(p)
            if v:
                qs = qs.filter(**{campo: v})
        pag = Paginacion()
        return pag.get_paginated_response(s.EventoSerializer(pag.paginate_queryset(qs, request, view=self), many=True).data)

    def retrieve(self, request, pk=None):
        return Response(s.EventoSerializer(get_object_or_404(self._qs(request.user), pk=pk)).data)


@api_view(["GET"])
def trazabilidad_lote(request, codigo):
    """Toda la procedencia de un lote: origen, cosechas, eventos y despachos."""
    lote = get_object_or_404(Lote.objects.select_related("producto"), codigo__iexact=codigo)
    u = request.user
    perm.exigir(perm.consulta_area(u, Area.LOTES) or lote.responsable_id == u.id or perm.area_de(u) == Area.COMERCIAL,
                request._request, f"API: trazabilidad del lote {codigo}")
    personales = perm.ve_datos_personales(u)
    lotes = [lote] + lote.lotes_origen()
    eventos = EventoTrazabilidad.objects.filter(Q(lote__in=lotes) | Q(cosecha__in=lote.todas_las_cosechas())).order_by("fecha_hora")
    return Response({
        "lote": s.LoteSerializer(lote, context={"request": request}).data,
        "gs1_digital_link": lote.link_gs1,
        "lotes_de_origen": [l.codigo for l in lote.lotes_origen()],
        "productores": [p.nombre if personales else p.nombre_publico for p in lote.productores()],
        "parcelas": [{"codigo": p.codigo, "nombre": p.nombre, "gln": p.gln, "latitud": p.latitud, "longitud": p.longitud}
                     for p in lote.parcelas()],
        "cosechas": [{"codigo": c.codigo, "fecha": c.fecha, "cantidad": c.cantidad, "unidad": c.unidad}
                     for c in lote.todas_las_cosechas()],
        "control_eventos": [{"paso": n, "registrado": ok} for _c, n, ok in lote.control_eventos()],
        "completitud": lote.completitud,
        "eventos": s.EventoSerializer(eventos, many=True).data,
        "despachos": [{"codigo": d.codigo, "salida": d.salida, "destino": d.destino, "cantidad": d.cantidad, "estado": d.estado}
                      for d in lote.despachos.exclude(estado="cancelado")],
    })


@api_view(["GET"])
def indicadores(request):
    """Indicadores generales (administrador y área de consulta)."""
    perm.exigir(perm.es_admin(request.user) or perm.area_de(request.user) == Area.REPORTES, request._request, "API: indicadores")
    from dashboard.indicadores import panel_general
    datos = panel_general(request.user)
    return Response({"indicadores": [{"nombre": k["etiqueta"], "valor": k["valor"]} for k in datos["kpis"]],
                     "graficos": datos["graficos"]})


def documentacion(request):
    """Página de ayuda de la API dentro del aplicativo."""
    from django.contrib.auth.decorators import login_required

    @login_required
    def _vista(req):
        return render(req, "api/documentacion.html", {"titulo": "API REST"})
    return _vista(request)
