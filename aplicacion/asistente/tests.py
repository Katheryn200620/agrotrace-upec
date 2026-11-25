"""Pruebas del asistente virtual, los agentes guiados y el registro de voz."""
import json

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from asistente.models import MensajeAsistente
from lotes.models import Lote
from productores.models import Productor

User = get_user_model()


@override_settings(ALLOWED_HOSTS=["*"], IA_PROVEEDOR="ninguno")
class Asistente(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_datos_demo", verbosity=0)

    def preguntar(self, usuario, texto):
        self.client.force_login(User.objects.get(username=usuario))
        r = self.client.post("/asistente/mensaje/", json.dumps({"pregunta": texto}), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        return r.json()

    def test_consulta_un_lote_con_datos_reales(self):
        lote = Lote.objects.first()
        d = self.preguntar("admin", f"consultar el lote {lote.codigo}")
        self.assertEqual(d["intencion"], "lote")
        self.assertIn(lote.codigo, d["texto"])
        self.assertEqual(d["fuente"], "reglas")
        self.assertTrue(MensajeAsistente.objects.filter(pregunta__contains=lote.codigo).exists())

    def test_respeta_permisos(self):
        d = self.preguntar("comercial", "¿qué productores hay?")
        self.assertIn("no consulta productores", d["texto"])
        p = Productor.objects.exclude(identificacion="").first()
        d = self.preguntar("cosechas", "productores")
        self.assertNotIn(p.identificacion, d["texto"])

    def test_instrucciones_con_agente(self):
        d = self.preguntar("cosechas", "¿cómo registro una cosecha?")
        self.assertEqual(d["intencion"], "instrucciones")
        self.assertTrue(any("/asistente/agentes/cosecha/" == e["url"] for e in d["enlaces"]))

    def test_sin_ia_lo_dice_y_no_inventa(self):
        d = self.preguntar("admin", "¿quién ganó el partido?")
        self.assertEqual(d["fuente"], "reglas")
        self.assertEqual(d["intencion"], "desconocida")

    def test_pregunta_vacia(self):
        self.client.force_login(User.objects.get(username="admin"))
        r = self.client.post("/asistente/mensaje/", json.dumps({"pregunta": " "}), content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_registro_de_comando_de_voz(self):
        self.client.force_login(User.objects.get(username="lotes"))
        r = self.client.post("/asistente/voz/registrar/", json.dumps({"texto": "abrir inventario", "comando": "abrir",
                                                                      "accion": "Abriendo inventario"}), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(MensajeAsistente.objects.filter(canal="voz", pregunta="abrir inventario").exists())
        self.assertEqual(self.client.get("/asistente/voz/").status_code, 200)

    def test_agente_crea_productor_con_las_mismas_reglas(self):
        self.client.force_login(User.objects.get(username="productores"))
        self.assertEqual(self.client.get("/asistente/agentes/productor/").status_code, 200)
        r = self.client.post("/asistente/agentes/productor/", {"nombre": "Rosa Chalá", "tipo": "persona", "provincia": "Carchi",
                                                               "canton": "Tulcán", "parroquia": "Tufiño", "estado": "activo",
                                                               "identificacion": "123"})
        self.assertEqual(r.status_code, 200)               # cédula inválida: vuelve al agente con el error
        self.assertContains(r, "10 dígitos")
        r = self.client.post("/asistente/agentes/productor/", {"nombre": "Rosa Chalá", "tipo": "persona", "provincia": "Carchi",
                                                               "canton": "Tulcán", "parroquia": "Tufiño", "estado": "activo"})
        p = Productor.objects.get(nombre="Rosa Chalá")
        self.assertRedirects(r, p.get_absolute_url())
        self.assertEqual(p.responsable.username, "productores")

    def test_agente_de_otra_area_bloqueado(self):
        self.client.force_login(User.objects.get(username="comercial"))
        self.assertEqual(self.client.get("/asistente/agentes/lote/").status_code, 403)
        self.assertEqual(self.client.get("/asistente/agentes/venta/").status_code, 200)

    def test_uso_solo_administrador(self):
        self.client.force_login(User.objects.get(username="comercial"))
        self.assertEqual(self.client.get("/asistente/uso/").status_code, 403)
        self.client.force_login(User.objects.get(username="admin"))
        self.assertEqual(self.client.get("/asistente/uso/").status_code, 200)
