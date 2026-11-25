"""
F5 – Sincroniza AgroTrace-UPEC con Odoo. La lógica está en integracion/odoo.py.

Uso:  python manage.py sincronizar_odoo --probar
      python manage.py sincronizar_odoo
      python manage.py sincronizar_odoo --existencias     (además actualiza las cantidades por lote)
"""
from django.core.management.base import BaseCommand, CommandError

from integracion.models import SincronizacionERP
from integracion.odoo import ErrorOdoo, probar, sincronizar


class Command(BaseCommand):
    help = "Sincroniza productos, proveedores, clientes, cosechas, lotes, ventas y despachos con Odoo."

    def add_arguments(self, parser):
        parser.add_argument("--probar", action="store_true", help="Solo prueba la conexión")
        parser.add_argument("--existencias", action="store_true", help="También envía las cantidades disponibles por lote")

    def handle(self, *args, **opts):
        modo = "prueba" if opts["probar"] else "sincronizacion"
        try:
            if opts["probar"]:
                d = probar()
                self.stdout.write(self.style.SUCCESS(f"Conectado a Odoo {d['version']} (uid {d['uid']})"))
                SincronizacionERP.objects.create(modo=modo, exito=True, version_odoo=d["version"])
                return
            lineas = []
            r = sincronizar(opts["existencias"], informar=lambda t: (lineas.append(t), self.stdout.write(t)))
            SincronizacionERP.objects.create(modo=modo, exito=True, resumen=r, detalle="\n".join(lineas)[:20000],
                                             version_odoo=lineas[0].split()[3] if lineas else "")
            for a in r["avisos"]:
                self.stdout.write(self.style.WARNING(a))
        except ErrorOdoo as exc:
            SincronizacionERP.objects.create(modo=modo, exito=False, detalle=str(exc))
            raise CommandError(str(exc))
