"""
Carga datos DE PRUEBA para practicar y presentar el aplicativo.
¡Importante! Para el informe se deben usar datos reales de la planta.

Uso (en la terminal de VS Code):  python manage.py cargar_datos_demo
"""
from datetime import datetime, time, timedelta
from decimal import Decimal as D

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from cosechas.models import Clasificacion, Cosecha, Recepcion
from cuentas.models import Area
from lotes.models import Lote, RelacionLote
from parcelas.models import Labor, Parcela
from productores.models import Productor
from productos.models import Producto
from trazabilidad.models import EscaneoQR, SimulacroRetiro
from trazabilidad.servicios import registrar_evento
from transporte.models import Despacho, Transportista

User = get_user_model()
CLAVE = "upec2026"
OPERADORES = [
    ("productores", "Ana", "Paredes", Area.PRODUCTORES),
    ("parcelas", "Luis", "Benavides", Area.PARCELAS),
    ("productos", "Carla", "Ruano", Area.PRODUCTOS),
    ("cosechas", "Jorge", "Pozo", Area.COSECHAS),
    ("cosechas2", "Diana", "Cuasquer", Area.COSECHAS),
    ("lotes", "Mateo", "Rosero", Area.LOTES),
    ("trazabilidad", "Sofía", "Imbaquingo", Area.TRAZABILIDAD),
    ("transporte", "Kevin", "Chamorro", Area.TRANSPORTE),
    ("reportes", "Paula", "Narváez", Area.REPORTES),
    ("comercial", "Gabriela", "Erazo", Area.COMERCIAL),
]


def momento(fecha, hora):
    return timezone.make_aware(datetime.combine(fecha, time(hora, 0)))


class Command(BaseCommand):
    help = "Crea cuentas de prueba (administrador y operadores) y datos de ejemplo de procedencia."

    @transaction.atomic
    def handle(self, *args, **opts):
        admin, creado = User.objects.get_or_create(username="admin", defaults={
            "first_name": "Administrador", "last_name": "General", "is_staff": True, "is_superuser": True})
        if creado:
            admin.set_password(CLAVE); admin.save()
        admin.perfil.es_admin_general = True; admin.perfil.save()
        u = {}
        for usuario, nombre, apellido, area in OPERADORES:
            x, creado = User.objects.get_or_create(username=usuario, defaults={"first_name": nombre, "last_name": apellido})
            if creado:
                x.set_password(CLAVE); x.save()
            p = x.perfil
            p.area = Area.objects.get(codigo=area)
            p.puede_crear = p.puede_editar = area != Area.REPORTES
            p.puede_eliminar = area in (Area.PRODUCTORES, Area.PARCELAS)
            p.save()
            u[usuario] = x
        self.stdout.write(f"Cuentas listas (clave para todas: {CLAVE}): admin, " + ", ".join(u))

        if Productor.objects.exists():
            self.stdout.write(self.style.WARNING("Ya existen datos de procedencia; no se cargaron de nuevo."))
            self.cargar_comercial(u)
            return

        hoy = timezone.localdate()
        # ---- Productores ----
        pr1 = Productor.objects.create(nombre="Centro Experimental UPEC", tipo="centro", identificacion="0460000000001",
                                       canton="Tulcán", parroquia="González Suárez", telefono="062224079",
                                       correo="planta.hortofruticola@upec.edu.ec", responsable=u["productores"])
        pr2 = Productor.objects.create(nombre="Asociación Frutales del Norte", tipo="organizacion", identificacion="0491234567001",
                                       canton="Montúfar", parroquia="San Gabriel", telefono="0991234567",
                                       mostrar_nombre_publico=True, responsable=u["productores"])
        pr3 = Productor.objects.create(nombre="José Cuaical Pozo", tipo="persona", identificacion="0401234567",
                                       canton="Tulcán", parroquia="Julio Andrade", telefono="0987654321",
                                       responsable=u["productores"])
        Productor.objects.create(nombre="María Tarapués", tipo="persona", canton="Tulcán", parroquia="Urbina",
                                 responsable=u["productores"])

        # ---- Productos ----
        P = lambda **k: Producto.objects.create(responsable=u["productos"], **k)
        papa = P(nombre="Papa", variedad="Superchola", categoria="tuberculo", vida_util_dias=30, precio=D("0.60"), stock_minimo=D("200"))
        mora = P(nombre="Mora de Castilla", categoria="fruta", vida_util_dias=5, precio=D("2.50"), stock_minimo=D("40"))
        tomate = P(nombre="Tomate de árbol", variedad="Anaranjado", categoria="fruta", vida_util_dias=12, precio=D("1.20"), stock_minimo=D("50"))
        pulpa = P(nombre="Pulpa de mora 500 g", categoria="procesado", unidad="und", vida_util_dias=90, precio=D("1.80"))
        P(nombre="Haba tierna", categoria="grano", vida_util_dias=7, precio=D("1.00"))

        # ---- Parcelas y labores ----
        Pa = lambda **k: Parcela.objects.create(responsable=u["parcelas"], **k)
        p1 = Pa(codigo="P-01", nombre="Lote Norte", productor=pr1, cultivo=papa, variedad="Superchola", superficie=D("0.80"),
                latitud=D("0.812500"), longitud=D("-77.720800"), altitud_msnm=2950, fecha_siembra=hoy - timedelta(days=160),
                estado_cultivo="cosecha")
        p2 = Pa(codigo="P-02", nombre="Huerto de mora", productor=pr1, cultivo=mora, variedad="Castilla", superficie=D("0.35"),
                latitud=D("0.811900"), longitud=D("-77.719600"), altitud_msnm=2940, fecha_siembra=hoy - timedelta(days=400),
                estado_cultivo="cosecha")
        p3 = Pa(codigo="P-03", nombre="Finca La Esperanza", productor=pr2, cultivo=tomate, superficie=D("1.20"),
                latitud=D("0.602100"), longitud=D("-77.831500"), altitud_msnm=2860, fecha_siembra=hoy - timedelta(days=300),
                estado_cultivo="cosecha")
        p4 = Parcela.objects.create(codigo="P-04", nombre="Chacra Cuaical", productor=pr3, cultivo=mora, superficie=D("0.25"),
                                    latitud=D("0.732000"), longitud=D("-77.734000"), altitud_msnm=2900,
                                    fecha_siembra=hoy - timedelta(days=380), estado_cultivo="desarrollo", responsable=admin)
        L = lambda **k: Labor.objects.create(responsable=u["parcelas"], **k)
        L(parcela=p1, tipo="siembra", fecha=hoy - timedelta(days=160), insumo="Semilla certificada", dosis="1 200 kg/ha")
        L(parcela=p1, tipo="fertilizacion", fecha=hoy - timedelta(days=120), insumo="Fertilizante 10-30-10", dosis="400 kg/ha")
        L(parcela=p1, tipo="fitosanitario", fecha=hoy - timedelta(days=55), insumo="Fungicida preventivo", dosis="2,5 kg/ha")
        L(parcela=p2, tipo="poda", fecha=hoy - timedelta(days=45), descripcion="Poda de formación")
        L(parcela=p2, tipo="riego", fecha=hoy - timedelta(days=20), dosis="2 h por goteo")
        L(parcela=p3, tipo="fertilizacion", fecha=hoy - timedelta(days=35), insumo="Abono orgánico", dosis="5 t/ha")

        # ---- Cosechas, recepción y clasificación ----
        datos = [  # parcela, productor, producto, días, kg, kg recibido, clases, operador
            (p1, pr1, papa, 24, 620, 615, [("primera", 420), ("segunda", 140), ("rechazo", 55, "Daño mecánico")], "cosechas"),
            (p2, pr1, mora, 15, 85, 84, [("extra", 30), ("primera", 38), ("rechazo", 16, "Pudrición")], "cosechas"),
            (p3, pr2, tomate, 10, 160, 158, [("primera", 110), ("segunda", 36), ("rechazo", 12, "Calibre")], "cosechas"),
            (p2, pr1, mora, 6, 92, 91, [("extra", 41), ("primera", 40), ("rechazo", 10, "Golpe")], "cosechas"),
            (p4, pr3, mora, 5, 60, 59, [("primera", 50), ("rechazo", 9, "Pudrición")], "cosechas2"),
            (p1, pr1, papa, 3, 540, 536, [("primera", 380), ("segunda", 120), ("rechazo", 36, "Verdeamiento")], "cosechas"),
        ]
        cos = []
        for parcela, productor, producto, dias, kg, rec, clases, op in datos:
            f = hoy - timedelta(days=dias)
            c = Cosecha.objects.create(parcela=parcela, productor=productor, producto=producto, fecha=f, cantidad=kg,
                                       responsable=u[op])
            r = Recepcion.objects.create(cosecha=c, fecha_hora=momento(f, 11), peso_recibido=rec, temperatura=D("12.5"),
                                         minutos_recepcion=18, responsable=u[op])
            for cl in clases:
                Clasificacion.objects.create(recepcion=r, categoria=cl[0], cantidad=cl[1], causa_rechazo=cl[2] if len(cl) > 2 else "",
                                             responsable=u[op])
            cos.append(c)
        # Una cosecha de hoy aún sin recibir
        Cosecha.objects.create(parcela=p3, productor=pr2, producto=tomate, fecha=hoy, cantidad=140, responsable=u["cosechas"])

        # ---- Lotes ----
        def lote(c, cantidad, dias, categoria="primera"):
            l = Lote.objects.create(producto=c.producto, cantidad_inicial=cantidad, categoria=categoria,
                                    fecha_creacion=c.fecha + timedelta(days=1), proceso="Lavado, selección y empaque",
                                    responsable=u["lotes"])
            l.cosechas.add(c)
            return l
        l1 = lote(cos[0], 420, 23)
        l2 = lote(cos[1], 68, 14, "extra")
        l3 = lote(cos[2], 110, 9)
        l4 = lote(cos[3], 81, 5, "extra")
        l5 = lote(cos[4], 50, 4)
        lote(cos[5], 380, 2)

        # Transformación: parte de la mora del lote 4 se convierte en pulpa
        pl = Lote(producto=pulpa, cantidad_inicial=60, proceso="Despulpado, pasteurización y envasado de 500 g",
                  ubicacion="Bodega de producto terminado", fecha_creacion=hoy - timedelta(days=4), responsable=u["lotes"])
        pl._sin_evento = True
        pl.save()
        RelacionLote.objects.create(origen=l4, resultado=pl, tipo="transformacion", cantidad=30, responsable=u["lotes"])
        l4.cantidad_disponible -= 30; l4.save()
        registrar_evento("transformacion", u["lotes"], f"30 kg transformados en el lote {pl.codigo}", lote=l4, cantidad=30,
                         unidad="kg", fecha_hora=momento(hoy - timedelta(days=4), 10))
        registrar_evento("transformacion", u["lotes"], f"60 und de pulpa obtenidas de {l4.codigo}", lote=pl, cantidad=60,
                         unidad="und", fecha_hora=momento(hoy - timedelta(days=4), 15))

        # Eventos registrados por el operador de trazabilidad
        for l, dias in ((l1, 22), (l2, 13), (l3, 8)):
            registrar_evento("empaque", u["trazabilidad"], "Empaque en sacos de 50 kg" if l == l1 else "Empaque en gavetas plásticas",
                             lote=l, fecha_hora=momento(hoy - timedelta(days=dias), 9), origen="manual")
            registrar_evento("almacenamiento", u["trazabilidad"], "Ingreso a cámara de poscosecha a 6 °C", lote=l,
                             fecha_hora=momento(hoy - timedelta(days=dias), 10), origen="manual")

        # ---- Transporte ----
        t1 = Transportista.objects.create(nombre="Transportes Carchi Frío", vehiculo_placa="CAA-1234", tipo_vehiculo="Furgón",
                                          refrigerado=True, telefono="062987654", responsable=u["transporte"])
        t2 = Transportista.objects.create(nombre="Camioneta UPEC", vehiculo_placa="CEB-0456", tipo_vehiculo="Camioneta",
                                          responsable=u["transporte"])

        def despacho(l, cantidad, dias, tipo, destino, transp, estado):
            salida = momento(hoy - timedelta(days=dias), 8)
            d = Despacho.objects.create(lote=l, cantidad=cantidad, transportista=transp, vehiculo=transp.vehiculo_placa,
                                        salida=salida, tipo_destino=tipo, destino=destino, estado=estado,
                                        responsable=u["transporte"])
            l.cantidad_disponible -= cantidad
            registrar_evento("despacho", u["transporte"], f"Despacho {d.codigo}: {cantidad} {l.unidad} hacia {d.get_tipo_destino_display().lower()}",
                             lugar=d.origen, lote=l, cantidad=cantidad, unidad=l.unidad, fecha_hora=salida, disposicion="in_transit")
            if estado in ("transito", "entregado"):
                registrar_evento("transporte", u["transporte"], f"Salida del despacho {d.codigo} hacia {destino}", lugar=d.origen,
                                 lote=l, cantidad=cantidad, unidad=l.unidad, fecha_hora=salida + timedelta(minutes=20))
            if estado == "entregado":
                d.llegada = salida + timedelta(hours=2); d.entregado_a_tiempo = True; d.km_recorridos = D("4.5"); d.save()
                registrar_evento("recepcion_destino", u["transporte"], f"Recepción en destino ({destino}) del despacho {d.codigo}",
                                 lugar=destino, lote=l, cantidad=cantidad, unidad=l.unidad, fecha_hora=d.llegada)
            if l.cantidad_disponible == 0:
                l.estado = "entregado" if estado == "entregado" else "transporte"
            l.save()
            return d
        despacho(l1, 300, 20, "cedi", "CEDI UPEC", t1, "entregado")
        despacho(l2, 68, 12, "tienda", "Pedido web #1001 – Tulcán", t2, "entregado")
        despacho(l3, 80, 6, "cliente", "Mercado San Miguel, Tulcán", t2, "transito")
        despacho(pl, 24, 1, "cedi", "CEDI UPEC", t1, "programado")

        # Revisión del administrador en algunos registros
        for m in (pr1, pr2, p1, p2, papa, mora, l1, l2):
            m.estado_revision = "aprobado"; m.revisado_por = admin; m.revisado_en = timezone.now(); m.save()

        for _ in range(7):
            EscaneoQR.objects.create(lote=l2, agente_usuario="demo")
        for _ in range(3):
            EscaneoQR.objects.create(lote=pl, agente_usuario="demo")
        SimulacroRetiro.objects.create(lote=l1, metodo="actual", minutos=D("38"), completitud_pct=40,
                                       responsable=u["trazabilidad"], observaciones="Dato de prueba")
        self.cargar_comercial(u)
        self.stdout.write(self.style.SUCCESS("Datos de prueba cargados."))

    def cargar_comercial(self, u):
        """Clientes y ventas de prueba, enlazados con los despachos de prueba (solo si aún no hay clientes)."""
        from comercial.models import Cliente, Venta
        if Cliente.objects.exists() or not Lote.objects.exists():
            return
        C = lambda **k: Cliente.objects.create(responsable=u["comercial"], **k)
        web = C(nombre="Pedido web #1001", tipo="tienda", ciudad="Tulcán")
        mercado = C(nombre="Mercado San Miguel", tipo="minorista", ciudad="Tulcán", telefono="062980111")
        C(nombre="Supermercado Norte", tipo="mayorista", ciudad="Ibarra", identificacion="1091234567001")
        C(nombre="Restaurante El Frailejón", tipo="comercio", ciudad="Tulcán")
        for d, cliente, canal in ((Despacho.objects.filter(destino__startswith="Pedido web").first(), web, "tienda"),
                                  (Despacho.objects.filter(destino__startswith="Mercado").first(), mercado, "pedido")):
            if d is None:
                continue
            v = Venta.objects.create(cliente=cliente, lote=d.lote, cantidad=d.cantidad, precio_unitario=d.lote.producto.precio,
                                     canal=canal, fecha=timezone.localtime(d.salida).date(), responsable=u["comercial"],
                                     estado="entregada" if d.estado == "entregado" else "despachada")
            Despacho.objects.filter(pk=d.pk).update(venta=v)
            registrar_evento("venta", u["comercial"], f"Venta {v.codigo}: {v.cantidad} {d.lote.unidad} a {cliente.get_tipo_display().lower()}",
                             lote=d.lote, cantidad=v.cantidad, unidad=d.lote.unidad,
                             fecha_hora=d.salida - timedelta(hours=2), disposicion="sellable_accessible")
        self.stdout.write("Clientes y ventas de prueba cargados.")
