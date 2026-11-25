"""Pruebas de la página de Inicio (catálogo de productos) y del Panel de procedencia."""
import io
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from PIL import Image

from productos.models import Producto

User = get_user_model()
MEDIA_PRUEBA = tempfile.mkdtemp()


def imagen_png():
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (61, 128, 96)).save(buf, format="PNG")
    return SimpleUploadedFile("mora.png", buf.getvalue(), content_type="image/png")


@override_settings(ALLOWED_HOSTS=["*"], MEDIA_ROOT=MEDIA_PRUEBA)
class PaginaInicio(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_datos_demo", verbosity=0)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_PRUEBA, ignore_errors=True)
        super().tearDownClass()

    def test_inicio_es_la_primera_pagina_despues_de_ingresar(self):
        r = self.client.post("/ingresar/", {"username": "comercial", "password": "upec2026"})
        self.assertRedirects(r, "/")
        r = self.client.get("/")
        self.assertContains(r, "Catálogo de productos")
        self.assertContains(r, "Panel de procedencia")              # el menú permite volver al panel

    def test_muestra_todos_los_productos_reales_y_reemplazo_sin_foto(self):
        self.client.force_login(User.objects.get(username="lotes"))
        r = self.client.get("/")
        for p in Producto.objects.all():
            self.assertContains(r, p.nombre)
        self.assertContains(r, "Sin fotografía registrada")
        self.assertEqual(len(r.context["productos"]), Producto.objects.count())

    def test_producto_nuevo_con_foto_aparece_solo(self):
        self.client.force_login(User.objects.get(username="productos"))
        r = self.client.post("/productos/nuevo/", {"nombre": "Uvilla", "categoria": "fruta", "unidad": "kg", "vida_util_dias": 15,
                                                   "precio": "3.00", "stock_minimo": "0", "estado": "activo", "foto": imagen_png()})
        self.assertEqual(r.status_code, 302, r.content[:500])
        p = Producto.objects.get(nombre="Uvilla")
        self.assertTrue(p.foto.name.startswith("productos/"))
        r = self.client.get("/")
        self.assertContains(r, "Uvilla")
        self.assertContains(r, p.foto.url)

    def test_archivo_que_no_es_imagen_se_rechaza(self):
        self.client.force_login(User.objects.get(username="productos"))
        falso = SimpleUploadedFile("foto.png", b"no es una imagen", content_type="image/png")
        r = self.client.post("/productos/nuevo/", {"nombre": "X", "categoria": "fruta", "unidad": "kg", "vida_util_dias": 5,
                                                   "precio": "1", "stock_minimo": "0", "estado": "activo", "foto": falso})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Producto.objects.filter(nombre="X").exists())

    def test_panel_de_procedencia_se_conserva(self):
        self.client.force_login(User.objects.get(username="admin"))
        r = self.client.get("/panel-procedencia/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Rechazo por parcela")
        self.assertContains(r, "Trazabilidad completa")
        self.assertIn("graficos", r.context)
