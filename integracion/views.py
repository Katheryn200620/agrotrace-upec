from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from cuentas import permissions as perm
from cuentas.auditoria import registrar

from .models import SincronizacionERP
from .odoo import ErrorOdoo, probar, sincronizar


def _admin(request):
    perm.exigir(perm.es_admin(request.user), request, "Acceso a la integración ERP")


@login_required
def estado(request):
    _admin(request)
    from comercial.models import Cliente, Venta
    from lotes.models import Lote
    from productos.models import Producto
    enlazados = [("Productos", Producto.objects.exclude(odoo_id=None).count(), Producto.objects.count()),
                 ("Clientes", Cliente.objects.exclude(odoo_id=None).count(), Cliente.objects.count()),
                 ("Lotes", Lote.objects.exclude(odoo_id=None).count(), Lote.objects.count()),
                 ("Ventas", Venta.objects.exclude(odoo_id=None).count(), Venta.objects.exclude(estado="anulada").count())]
    return render(request, "integracion/estado.html", {
        "titulo": "Integración ERP (Odoo)", "url": settings.ODOO_URL, "db": settings.ODOO_DB, "usuario": settings.ODOO_USER,
        "clave": bool(settings.ODOO_PASSWORD), "historial": SincronizacionERP.objects.select_related("usuario")[:15],
        "enlazados": enlazados, "ultima_ok": SincronizacionERP.objects.filter(exito=True).first()})


@login_required
@require_POST
def ejecutar(request):
    _admin(request)
    modo = request.POST.get("modo", "prueba")
    try:
        if modo == "prueba":
            d = probar()
            SincronizacionERP.objects.create(usuario=request.user, modo="prueba", exito=True, version_odoo=d["version"])
            messages.success(request, f"Conexión correcta con Odoo {d['version']}.")
        else:
            lineas = []
            r = sincronizar(request.POST.get("existencias") == "1", informar=lineas.append)
            SincronizacionERP.objects.create(usuario=request.user, modo="sincronizacion", exito=True, resumen=r,
                                             detalle="\n".join(lineas)[:20000])
            registrar(request, "exportar", detalle=f"Sincronización con Odoo: {r}")
            messages.success(request, "Sincronización terminada: " + ", ".join(f"{v} {k}" for k, v in r.items() if k != "avisos" and v) + "."
                             if any(v for k, v in r.items() if k != "avisos") else "Sincronización terminada: no había registros nuevos.")
            for a in r["avisos"]:
                messages.warning(request, a)
    except ErrorOdoo as exc:
        SincronizacionERP.objects.create(usuario=request.user, modo="prueba" if modo == "prueba" else "sincronizacion",
                                         exito=False, detalle=str(exc))
        messages.error(request, f"{exc} Revise que Odoo esté encendido y los datos ODOO_* del archivo .env.")
    return redirect("integracion:estado")
