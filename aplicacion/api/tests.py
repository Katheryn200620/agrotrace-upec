"""
Pruebas de la API REST, de las ventas y de los paneles por área.
Ejecutar:  python manage.py test
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from comercial.models import Cliente, Venta
from lotes.models import Lote
from productores.models import Productor
from trazabilidad.models import EventoTrazabilidad

User = get_user_model()


@override_settings(ALLOWED_HOSTS=["*"])
class BaseApi(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_datos_demo", verbosity=0)

    def cliente_api(self, usuario):
        c = APIClient()
        r = c.post("/api/v1/token/", {"username": usuario, "password": "upec2026"})
        self.assertEqual(r.status_code, 200, r.content)
        c.credentials(HTTP_AUTHORIZATION="Token " + r.data["token"])
        return c

    def lote_con_stock(self):
        return Lote.objects.filter(cantidad_disponible__gt=50, estado="almacenamiento", producto__unidad="kg").first()


class ApiAutenticacion(BaseApi):
    def test_sin_credenciales_responde_401_o_403(self):
        r = APIClient().get("/api/v1/lotes/")
        self.assertIn(r.status_code, (401, 403))

    def test_token_con_clave_incorrecta(self):
        r = APIClient().post("/api/v1/token/", {"username": "admin", "password": "mal"})
        self.assertEqual(r.status_code, 400)

    def test_raiz_lista_los_recursos(self):
        r = self.cliente_api("admin").get("/api/v1/")
        self.assertEqual(r.status_code, 200)
        for recurso in ["productores", "parcelas", "labores", "cosechas", "recepciones", "clasificaciones", "lotes",
                        "productos", "ventas", "clientes", "eventos"]:
            self.assertIn(recurso, r.data)


class ApiPermisos(BaseApi):
    def test_operador_no_lista_otra_area(self):
        r = self.cliente_api("comercial").get("/api/v1/productores/")
        self.assertEqual(r.status_code, 403)

    def test_operador_solo_lista_sus_registros(self):
        r = self.cliente_api("cosechas2").get("/api/v1/cosechas/")
        self.assertEqual(r.status_code, 200)
        propias = {c.pk for c in User.objects.get(username="cosechas2").__class__.objects.none()}
        self.assertTrue(all(x["responsable_nombre"] == "Diana Cuasquer" for x in r.data["results"]))

    def test_datos_personales_ocultos_para_otras_areas(self):
        p = Productor.objects.exclude(telefono="").first()
        r = self.cliente_api("cosechas").get(f"/api/v1/productores/{p.pk}/")
        self.assertEqual(r.status_code, 200)            # consulta compartida
        self.assertNotIn("telefono", r.data)
        self.assertNotIn("identificacion", r.data)

    def test_consulta_no_puede_crear(self):
        lote = self.lote_con_stock()
        r = self.cliente_api("reportes").post("/api/v1/ventas/", {"cliente": Cliente.objects.first().pk, "lote": lote.pk,
                                                                  "cantidad": "1"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_no_modifica_registro_ajeno(self):
        p = Productor.objects.first()
        p.responsable = User.objects.get(username="admin"); p.save()
        r = self.cliente_api("productores").patch(f"/api/v1/productores/{p.pk}/", {"telefono": "0999999999"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_eventos_no_se_borran_por_api(self):
        e = EventoTrazabilidad.objects.first()
        r = self.cliente_api("admin").delete(f"/api/v1/eventos/{e.pk}/")
        self.assertEqual(r.status_code, 405)


class ApiVentas(BaseApi):
    def test_venta_valida_y_reserva(self):
        c = self.cliente_api("comercial")
        lote = self.lote_con_stock()
        cli = Cliente.objects.first()
        r = c.post("/api/v1/ventas/", {"cliente": cli.pk, "lote": lote.pk, "cantidad": "10", "canal": "directa"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        v = Venta.objects.get(codigo=r.data["codigo"])
        self.assertEqual(v.precio_unitario, lote.producto.precio)       # precio referencial por defecto
        self.assertTrue(lote.eventos.filter(tipo="venta").exists())    # evento de trazabilidad
        lote.refresh_from_db()
        r = c.post("/api/v1/ventas/", {"cliente": cli.pk, "lote": lote.pk, "cantidad": str(lote.cantidad_disponible), "canal": "directa"},
                   format="json")
        self.assertEqual(r.status_code, 400)                            # ya hay 10 reservados

    def test_venta_mayor_que_lo_disponible(self):
        lote = self.lote_con_stock()
        r = self.cliente_api("comercial").post("/api/v1/ventas/", {"cliente": Cliente.objects.first().pk, "lote": lote.pk,
                                                                   "cantidad": "999999"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("cantidad", r.data)

    def test_despacho_de_venta_actualiza_estado(self):
        lote = self.lote_con_stock()
        v = Venta.objects.create(cliente=Cliente.objects.first(), lote=lote, cantidad=Decimal("5"), precio_unitario=1,
                                 responsable=User.objects.get(username="comercial"))
        from django.utils import timezone
        r = self.cliente_api("transporte").post("/api/v1/despachos/", {
            "venta": v.pk, "cantidad": "5", "salida": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
            "origen": "Planta", "tipo_destino": "cliente"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        v.refresh_from_db()
        self.assertEqual(v.estado, "despachada")

    def test_trazabilidad_completa_de_un_lote(self):
        lote = Lote.objects.filter(despachos__isnull=False).first()
        r = self.cliente_api("trazabilidad").get(f"/api/v1/trazabilidad/{lote.codigo}/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["eventos"])
        self.assertTrue(r.data["parcelas"])


@override_settings(ALLOWED_HOSTS=["*"])
class PanelesYMenu(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_datos_demo", verbosity=0)

    def test_admin_abre_los_12_paneles(self):
        from dashboard.areas import AREAS
        self.client.force_login(User.objects.get(username="admin"))
        for a in AREAS:
            r = self.client.get(f"/panel/areas/{a[0]}/")
            self.assertEqual(r.status_code, 200, a[0])

    def test_operador_no_abre_panel_ajeno_por_url(self):
        self.client.force_login(User.objects.get(username="comercial"))
        self.assertEqual(self.client.get("/panel/areas/comercial/").status_code, 200)
        for clave in ["seguridad", "administracion", "abastecimiento", "recepcion"]:
            self.assertEqual(self.client.get(f"/panel/areas/{clave}/").status_code, 403, clave)

    def test_menu_oculta_areas_no_autorizadas(self):
        self.client.force_login(User.objects.get(username="comercial"))
        r = self.client.get("/")
        self.assertContains(r, "Clientes y comercialización")
        self.assertNotContains(r, "Personal y seguridad")
        self.assertNotContains(r, "Abastecimiento y proveedores")

    def test_inventario_y_alertas(self):
        self.client.force_login(User.objects.get(username="lotes"))
        self.assertEqual(self.client.get("/lotes/inventario/").status_code, 200)
        self.assertEqual(self.client.get("/lotes/inventario/movimientos/?exportar=csv").status_code, 200)
        self.assertEqual(self.client.get("/panel/alertas/").status_code, 200)
        self.client.force_login(User.objects.get(username="comercial"))
        self.assertEqual(self.client.get("/lotes/inventario/").status_code, 403)


@override_settings(ALLOWED_HOSTS=["*"])
class BaseVacia(TestCase):
    """Con la base de datos vacía los paneles muestran cero y no fallan."""

    def test_paneles_sin_datos(self):
        admin = User.objects.create_superuser("admin", "a@a.com", "x")
        admin.perfil.es_admin_general = True; admin.perfil.save()
        self.client.force_login(admin)
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Todavía no hay productos registrados")      # Inicio sin productos
        r = self.client.get("/panel-procedencia/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Todavía no hay registros")
        from dashboard.areas import AREAS
        for a in AREAS:
            r = self.client.get(f"/panel/areas/{a[0]}/")
            self.assertEqual(r.status_code, 200, a[0])
