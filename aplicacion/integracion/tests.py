"""Pruebas de la integración con Odoo contra el simulador XML-RPC (no contra un Odoo real)."""
import threading

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from herramientas import simulador_odoo
from integracion.models import SincronizacionERP
from integracion.odoo import ErrorOdoo, sincronizar

User = get_user_model()


@override_settings(ODOO_URL="http://127.0.0.1:18069", ODOO_DB="upec", ODOO_USER="admin", ODOO_PASSWORD="admin", ALLOWED_HOSTS=["*"])
class IntegracionOdoo(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        simulador_odoo.DB.clear()
        cls.srv = simulador_odoo.servidor(18069)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()
        super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        call_command("cargar_datos_demo", verbosity=0)

    def test_sincroniza_sin_duplicar(self):
        r1 = sincronizar(existencias=True, informar=lambda t: None)
        self.assertGreater(r1["productos"], 0)
        self.assertGreater(r1["lotes"], 0)
        self.assertGreater(r1["ventas"], 0)
        r2 = sincronizar(informar=lambda t: None)
        self.assertEqual(sum(v for k, v in r2.items() if k != "avisos"), 0)

    @override_settings(ODOO_PASSWORD="mala")
    def test_credenciales_incorrectas(self):
        with self.assertRaises(ErrorOdoo):
            sincronizar(informar=lambda t: None)

    def test_pagina_solo_administrador_y_bitacora(self):
        self.client.force_login(User.objects.get(username="comercial"))
        self.assertEqual(self.client.get("/integracion/").status_code, 403)
        self.client.force_login(User.objects.get(username="admin"))
        self.assertEqual(self.client.get("/integracion/").status_code, 200)
        self.client.post("/integracion/ejecutar/", {"modo": "prueba"})
        self.assertTrue(SincronizacionERP.objects.filter(exito=True, modo="prueba").exists())
