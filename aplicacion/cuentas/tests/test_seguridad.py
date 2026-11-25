"""
Pruebas de seguridad y separación de información entre operadores.
Ejecutar:  python manage.py test
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

AHORA = lambda: timezone.localtime().strftime("%Y-%m-%dT%H:%M")

from cosechas.models import Cosecha
from cuentas.models import Area, RegistroAuditoria
from lotes.models import Lote
from parcelas.models import Parcela
from productores.models import Productor
from trazabilidad.models import EventoTrazabilidad
from transporte.models import Despacho

User = get_user_model()


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_datos_demo", verbosity=0)

    def entrar(self, usuario):
        self.client.force_login(User.objects.get(username=usuario))

    def cosecha_de(self, usuario):
        return Cosecha.objects.filter(responsable__username=usuario, recepcion__isnull=False).first()


class SinSesion(Base):
    def test_paginas_privadas_piden_inicio_de_sesion(self):
        for url in ["/", "/productores/", "/cosechas/1/", "/lotes/nuevo/", "/reportes/", "/cuentas/usuarios/"]:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertIn("/ingresar/", r["Location"])

    def test_la_consulta_publica_no_requiere_sesion_ni_expone_datos_personales(self):
        lote = Lote.objects.filter(cosechas__productor__tipo="persona").first()
        r = self.client.get(f"/01/{lote.producto.gtin}/10/{lote.codigo}")
        self.assertEqual(r.status_code, 200)
        productor = lote.productores().first()
        self.assertNotContains(r, productor.identificacion)
        self.assertNotContains(r, productor.telefono)
        self.assertNotContains(r, productor.nombre)          # no autorizó mostrar su nombre
        self.assertContains(r, "No constituye una certificación")


class AislamientoEntreOperadores(Base):
    def test_cada_operador_edita_sus_propios_registros(self):
        self.entrar("cosechas")
        c = self.cosecha_de("cosechas")
        r = self.client.post(f"/cosechas/{c.pk}/editar/", {"fecha": c.fecha.isoformat(), "observaciones": "Revisado en campo"})
        self.assertEqual(r.status_code, 302)
        c.refresh_from_db()
        self.assertEqual(c.observaciones, "Revisado en campo")

    def test_no_puede_ver_editar_ni_eliminar_registros_ajenos_manipulando_la_url(self):
        ajena = self.cosecha_de("cosechas")
        self.entrar("cosechas2")
        self.assertEqual(self.client.get(f"/cosechas/{ajena.pk}/").status_code, 403)
        self.assertEqual(self.client.get(f"/cosechas/{ajena.pk}/editar/").status_code, 403)
        r = self.client.post(f"/cosechas/{ajena.pk}/editar/", {"observaciones": "hackeado"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.client.post(f"/cosechas/{ajena.pk}/eliminar/").status_code, 403)
        ajena.refresh_from_db()
        self.assertNotEqual(ajena.observaciones, "hackeado")
        self.assertTrue(RegistroAuditoria.objects.filter(accion="acceso_denegado", usuario__username="cosechas2").exists())

    def test_las_listas_solo_muestran_lo_autorizado(self):
        self.entrar("cosechas2")
        r = self.client.get("/cosechas/")
        for c in Cosecha.objects.filter(responsable__username="cosechas"):
            self.assertNotContains(r, c.codigo)
        for c in Cosecha.objects.filter(responsable__username="cosechas2"):
            self.assertContains(r, c.codigo)

    def test_la_exportacion_no_entrega_datos_que_no_puede_ver(self):
        self.entrar("cosechas2")
        contenido = self.client.get("/cosechas/?exportar=csv").content.decode("utf-8-sig")
        for c in Cosecha.objects.filter(responsable__username="cosechas"):
            self.assertNotIn(c.codigo, contenido)
        self.assertEqual(self.client.get("/reportes/datos/productores.csv").status_code, 403)

    def test_no_accede_a_modulos_de_otras_areas(self):
        self.entrar("transporte")
        for url in ["/productores/", "/parcelas/nuevo/", "/cosechas/", "/lotes/nuevo/", "/reportes/"]:
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_consulta_compartida_sin_permiso_de_edicion(self):
        """El operador de lotes puede abrir una cosecha (origen) pero no modificarla."""
        c = self.cosecha_de("cosechas")
        self.entrar("lotes")
        self.assertEqual(self.client.get(f"/cosechas/{c.pk}/").status_code, 200)
        self.assertEqual(self.client.get(f"/cosechas/{c.pk}/editar/").status_code, 403)

    def test_datos_personales_reservados_a_productores(self):
        p = Productor.objects.get(identificacion="0401234567")
        self.entrar("cosechas")
        r = self.client.get(f"/productores/{p.pk}/")
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "0401234567")
        self.assertNotContains(r, p.telefono)

    def test_no_puede_apropiarse_de_registros_ni_elegir_responsable(self):
        self.entrar("parcelas")
        otro = User.objects.get(username="productores")
        r = self.client.post("/parcelas/nuevo/", {
            "codigo": "P-99", "nombre": "Prueba", "productor": Productor.objects.first().pk,
            "cultivo": Parcela.objects.first().cultivo_id, "superficie": "1", "unidad_superficie": "ha",
            "estado_cultivo": "sembrado", "responsable": otro.pk, "responsable_asignado": otro.pk})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Parcela.objects.get(codigo="P-99").responsable.username, "parcelas")

    def test_no_registra_labores_en_parcelas_ajenas(self):
        ajena = Parcela.objects.exclude(responsable__username="parcelas").first()
        self.entrar("parcelas")
        r = self.client.post("/parcelas/labores/nueva/", {"parcela": ajena.pk, "tipo": "riego", "fecha": "2026-01-10"})
        self.assertEqual(r.status_code, 200)               # vuelve el formulario con error
        self.assertFalse(ajena.labores.filter(tipo="riego", fecha="2026-01-10").exists())


class CuentasYPermisos(Base):
    def test_operador_no_cambia_su_area_ni_sus_permisos(self):
        u = User.objects.get(username="cosechas")
        self.entrar("cosechas")
        r = self.client.post(f"/cuentas/usuarios/{u.pk}/", {"username": "cosechas", "first_name": "x", "es_admin_general": "on",
                                                           "puede_eliminar": "on"})
        self.assertEqual(r.status_code, 403)
        u.refresh_from_db()
        self.assertFalse(u.perfil.es_admin_general)
        self.assertFalse(u.perfil.puede_eliminar)
        self.assertEqual(self.client.get("/cuentas/usuarios/").status_code, 403)
        self.assertEqual(self.client.get("/admin/").status_code, 302)   # no entra al panel técnico

    def test_cuenta_desactivada_no_puede_trabajar(self):
        u = User.objects.get(username="lotes")
        self.client.force_login(u)
        u.is_active = False
        u.save()
        r = self.client.get("/lotes/")
        self.assertEqual(r.status_code, 302)

    def test_area_deshabilitada_bloquea_a_sus_operadores(self):
        Area.objects.filter(codigo="transporte").update(activa=False)
        self.entrar("transporte")
        self.assertEqual(self.client.get("/transporte/").status_code, 302)

    def test_administrador_supervisa_todas_las_areas(self):
        self.entrar("admin")
        for url in ["/productores/", "/parcelas/", "/cosechas/", "/lotes/", "/trazabilidad/", "/transporte/", "/reportes/",
                    "/cuentas/usuarios/", "/cuentas/auditoria/"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        r = self.client.get("/cosechas/")
        for c in Cosecha.objects.all()[:5]:
            self.assertContains(r, c.codigo)

    def test_administrador_corrige_con_justificacion_y_queda_auditado(self):
        c = self.cosecha_de("cosechas")
        self.entrar("admin")
        r = self.client.post(f"/cosechas/{c.pk}/editar/", {"fecha": c.fecha.isoformat(), "observaciones": "Corrección"})
        self.assertEqual(r.status_code, 200)                         # falta la justificación
        r = self.client.post(f"/cosechas/{c.pk}/editar/", {"fecha": c.fecha.isoformat(), "observaciones": "Corrección",
                                                          "justificacion": "Error de digitación reportado"})
        self.assertEqual(r.status_code, 302)
        a = RegistroAuditoria.objects.filter(accion="editar", objeto_id=str(c.pk)).latest("fecha")
        self.assertEqual(a.justificacion, "Error de digitación reportado")
        self.assertIn("observaciones", a.cambios)


class IntegridadDeLaProcedencia(Base):
    def test_no_se_modifica_el_origen_de_un_lote_sin_autorizacion(self):
        lote = Lote.objects.filter(responsable__username="lotes", cosechas__isnull=False).first()
        origen = set(lote.cosechas.values_list("pk", flat=True))
        otra = Cosecha.objects.exclude(pk__in=origen).first()
        self.entrar("lotes")
        self.client.post(f"/lotes/{lote.pk}/editar/", {"categoria": "extra", "ubicacion": "X", "estado": "almacenamiento",
                                                      "cosechas": [otra.pk], "cantidad_inicial": "1"})
        self.assertEqual(set(lote.cosechas.values_list("pk", flat=True)), origen)
        r = self.client.post(f"/lotes/{lote.pk}/corregir-origen/", {"cosechas": [otra.pk], "justificacion": "x"})
        self.assertEqual(r.status_code, 403)

    def test_los_eventos_historicos_no_se_alteran(self):
        ev = EventoTrazabilidad.objects.first()
        ev.descripcion = "alterado"
        with self.assertRaises(PermissionDenied):
            ev.save()
        with self.assertRaises(PermissionDenied):
            ev.delete()
        self.entrar("trazabilidad")
        r = self.client.post(f"/trazabilidad/{ev.pk}/corregir/", {"descripcion": "x", "observaciones": "y"})
        self.assertEqual(r.status_code, 403)          # no es su evento

    def test_la_correccion_conserva_el_evento_original(self):
        ev = EventoTrazabilidad.objects.filter(responsable__username="trazabilidad").first()
        self.entrar("trazabilidad")
        self.client.post(f"/trazabilidad/{ev.pk}/corregir/", {"descripcion": "Empaque en gavetas", "observaciones": "Dato mal escrito"})
        ev.refresh_from_db()
        self.assertNotEqual(ev.descripcion, "Empaque en gavetas")
        self.assertTrue(ev.correcciones.filter(descripcion="Empaque en gavetas").exists())

    def test_auditoria_no_editable(self):
        a = RegistroAuditoria.objects.first() or RegistroAuditoria.objects.create(accion="crear")
        with self.assertRaises(PermissionDenied):
            a.save()
        with self.assertRaises(PermissionDenied):
            a.delete()

    def test_no_despacha_mas_de_lo_disponible(self):
        lote = Lote.objects.filter(cantidad_disponible__gt=0).exclude(estado="retirado").first()
        self.entrar("transporte")
        r = self.client.post("/transporte/nuevo/", {"lote": lote.pk, "cantidad": str(lote.cantidad_disponible + 1),
                                                    "salida": AHORA(), "origen": "Planta", "tipo_destino": "cliente",
                                                    "destino": "Cliente"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Despacho.objects.filter(destino="Cliente", lote=lote).exists())

    def test_despacho_descuenta_y_cancelacion_devuelve(self):
        lote = Lote.objects.filter(cantidad_disponible__gte=10).exclude(estado="retirado").first()
        antes = lote.cantidad_disponible
        self.entrar("transporte")
        self.client.post("/transporte/nuevo/", {"lote": lote.pk, "cantidad": "5", "salida": AHORA(),
                                                "origen": "Planta", "tipo_destino": "cliente", "destino": "Cliente prueba"})
        lote.refresh_from_db()
        self.assertEqual(lote.cantidad_disponible, antes - 5)
        d = Despacho.objects.get(destino="Cliente prueba")
        self.client.post(f"/transporte/{d.pk}/cancelar/", {"motivo": "Prueba"})
        lote.refresh_from_db()
        self.assertEqual(lote.cantidad_disponible, antes)

    def test_dividir_conserva_la_procedencia(self):
        lote = Lote.objects.filter(responsable__username="lotes", cantidad_disponible__gt=20, cosechas__isnull=False).first()
        self.entrar("lotes")
        self.client.post(f"/lotes/{lote.pk}/dividir/", {"cantidad": "10", "ubicacion": "Cámara 2"})
        nuevo = Lote.objects.get(origenes__origen=lote)
        self.assertEqual(set(nuevo.parcelas()), set(lote.parcelas()))
        self.assertEqual(nuevo.cantidad_inicial, Decimal("10"))

    def test_otro_operador_no_opera_lotes_ajenos(self):
        lote = Lote.objects.filter(responsable__username="lotes").first()
        self.entrar("transporte")
        self.assertEqual(self.client.post(f"/lotes/{lote.pk}/dividir/", {"cantidad": "1", "ubicacion": "x"}).status_code, 403)
        self.assertEqual(self.client.post(f"/lotes/{lote.pk}/retirar/", {"motivo": "x"}).status_code, 403)
