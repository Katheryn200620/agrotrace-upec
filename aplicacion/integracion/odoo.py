"""
Integración con Odoo (ERP) por su API externa XML-RPC (Odoo 16, 17 y 18).

Envía hacia Odoo:
  productos            → product.product (GTIN como código de barras, seguimiento por lote, publicado en la tienda)
  productores          → res.partner (proveedores)
  clientes             → res.partner (clientes)
  cosechas recibidas   → purchase.order (referencia del proveedor = código de cosecha)
  lotes                → stock.lot (con el enlace GS1 Digital Link)
  ventas               → sale.order (referencia del cliente = código de venta)
  despachos sin venta  → sale.order (referencia = código de despacho)
  existencias (opcional) → stock.quant por lote en la ubicación de stock del almacén principal
No duplica registros si se ejecuta varias veces (busca por código antes de crear).
"""
import xmlrpc.client

from django.conf import settings


class ErrorOdoo(Exception):
    pass


class Odoo:
    def __init__(self, url=None, db=None, user=None, pwd=None):
        self.url = (url or settings.ODOO_URL).rstrip("/")
        self.db, self.user, self.pwd = db or settings.ODOO_DB, user or settings.ODOO_USER, pwd or settings.ODOO_PASSWORD
        try:
            comun = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common", allow_none=True)
            self.version = str(comun.version().get("server_version", "?"))
            self.uid = comun.authenticate(self.db, self.user, self.pwd, {})
        except (ConnectionError, OSError, xmlrpc.client.Error) as exc:
            raise ErrorOdoo(f"No se pudo conectar con Odoo en {self.url}: {exc}")
        if not self.uid:
            raise ErrorOdoo("Odoo rechazó la base de datos, el usuario o la contraseña.")
        self.obj = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object", allow_none=True)
        try:
            self.mayor = int(self.version.split(".")[0].replace("saas~", "") or 0)
        except ValueError:
            self.mayor = 0

    def ejecutar(self, modelo, metodo, *args, **kw):
        return self.obj.execute_kw(self.db, self.uid, self.pwd, modelo, metodo, list(args), kw)

    def buscar(self, modelo, dominio):
        ids = self.ejecutar(modelo, "search", dominio, limit=1)
        return ids[0] if ids else None

    def crear(self, modelo, valores):
        return self.ejecutar(modelo, "create", valores)


def probar():
    o = Odoo()
    return {"version": o.version, "uid": o.uid}


def sincronizar(existencias=False, informar=print):
    """Ejecuta la sincronización completa y devuelve un resumen con lo creado."""
    from comercial.models import Cliente, Venta
    from cosechas.models import Cosecha
    from lotes.models import Lote
    from productores.models import Productor
    from productos.models import Producto
    from transporte.models import Despacho

    odoo = Odoo()
    r = {"productos": 0, "proveedores": 0, "clientes": 0, "compras": 0, "lotes": 0, "ventas": 0, "existencias": 0, "avisos": []}
    informar(f"Conectado a Odoo {odoo.version} (uid {odoo.uid})")

    for p in Producto.objects.filter(estado="activo"):
        pid = p.odoo_id or odoo.buscar("product.product", [["barcode", "=", p.gtin]])
        if not pid:
            v = {"name": str(p), "barcode": p.gtin, "default_code": p.codigo, "list_price": float(p.precio), "tracking": "lot"}
            if odoo.mayor >= 18:
                v.update(type="consu", is_storable=True)
            else:
                v["detailed_type" if odoo.mayor == 17 else "type"] = "product"
            pid = odoo.crear("product.product", v)
            r["productos"] += 1
            informar(f"  Producto: {p}")
        Producto.objects.filter(pk=p.pk).update(odoo_id=pid)
        ultimo = p.lotes.filter(publicado=True).exclude(estado="retirado").order_by("-fecha_creacion").first()
        texto = "Producto de la Planta Hortofrutícola UPEC. Conozca su origen escaneando el QR del empaque" + \
                (f": {ultimo.link_gs1}" if ultimo else ".")
        for valores in ({"is_published": True}, {"description_ecommerce": texto}, {"website_description": texto},
                        {"description_sale": texto}):
            try:
                odoo.ejecutar("product.product", "write", [pid], valores)
                if "is_published" not in valores:
                    break
            except xmlrpc.client.Fault:
                continue  # campo inexistente en esta versión o tienda no instalada

    socios = {}
    for pr in Productor.objects.all():
        sid = odoo.buscar("res.partner", [["ref", "=", pr.codigo]])
        if not sid:
            sid = odoo.crear("res.partner", {"name": pr.nombre, "ref": pr.codigo, "supplier_rank": 1, "city": pr.canton})
            r["proveedores"] += 1
        socios[pr.pk] = sid

    clientes = {}
    for c in Cliente.objects.all():
        cid = c.odoo_id or odoo.buscar("res.partner", [["ref", "=", c.codigo]])
        if not cid:
            cid = odoo.crear("res.partner", {"name": c.nombre, "ref": c.codigo, "customer_rank": 1, "city": c.ciudad,
                                             "is_company": c.tipo in ("mayorista", "comercio", "institucion")})
            r["clientes"] += 1
        Cliente.objects.filter(pk=c.pk).update(odoo_id=cid)
        clientes[c.pk] = cid

    for c in Cosecha.objects.filter(recepcion__isnull=False).select_related("producto", "recepcion"):
        if odoo.buscar("purchase.order", [["partner_ref", "=", c.codigo]]):
            continue
        odoo.crear("purchase.order", {"partner_id": socios[c.productor_id], "partner_ref": c.codigo, "order_line": [(0, 0, {
            "product_id": Producto.objects.get(pk=c.producto_id).odoo_id, "name": f"{c.producto} – cosecha {c.codigo}",
            "product_qty": float(c.recepcion.peso_recibido), "price_unit": float(c.producto.precio) * 0.4})]})
        r["compras"] += 1
        informar(f"  Orden de compra: {c.codigo}")

    compania = odoo.ejecutar("res.users", "read", [odoo.uid], fields=["company_id"])[0]["company_id"][0]
    for l in Lote.objects.select_related("producto"):
        lid = l.odoo_id or odoo.buscar("stock.lot", [["name", "=", l.codigo]])
        if not lid:
            lid = odoo.crear("stock.lot", {"name": l.codigo, "product_id": Producto.objects.get(pk=l.producto_id).odoo_id,
                                           "company_id": compania, "ref": l.link_gs1})
            r["lotes"] += 1
            informar(f"  Lote: {l.codigo}")
        Lote.objects.filter(pk=l.pk).update(odoo_id=lid)

    for v in Venta.objects.exclude(estado="anulada").select_related("lote__producto", "cliente"):
        if v.odoo_id or odoo.buscar("sale.order", [["client_order_ref", "=", v.codigo]]):
            continue
        sid = odoo.crear("sale.order", {"partner_id": clientes[v.cliente_id], "client_order_ref": v.codigo, "order_line": [(0, 0, {
            "product_id": Producto.objects.get(pk=v.lote.producto_id).odoo_id, "name": f"{v.lote.producto} – lote {v.lote.codigo}",
            "product_uom_qty": float(v.cantidad), "price_unit": float(v.precio_unitario)})]})
        Venta.objects.filter(pk=v.pk).update(odoo_id=sid)
        r["ventas"] += 1
        informar(f"  Pedido de venta: {v.codigo}")

    for d in Despacho.objects.exclude(estado="cancelado").filter(venta__isnull=True).select_related("lote__producto"):
        if odoo.buscar("sale.order", [["client_order_ref", "=", d.codigo]]):
            continue
        cliente = odoo.buscar("res.partner", [["name", "=", d.destino]]) or odoo.crear("res.partner", {"name": d.destino, "customer_rank": 1})
        odoo.crear("sale.order", {"partner_id": cliente, "client_order_ref": d.codigo, "order_line": [(0, 0, {
            "product_id": Producto.objects.get(pk=d.lote.producto_id).odoo_id, "name": f"{d.lote.producto} – lote {d.lote.codigo}",
            "product_uom_qty": float(d.cantidad), "price_unit": float(d.lote.producto.precio)})]})
        r["ventas"] += 1
        informar(f"  Pedido de venta (despacho): {d.codigo}")

    if existencias:
        try:
            ubic = odoo.ejecutar("stock.warehouse", "search_read", [], fields=["lot_stock_id"], limit=1)[0]["lot_stock_id"][0]
            for l in Lote.objects.filter(estado__in=["almacenamiento", "proceso"], cantidad_disponible__gt=0).select_related("producto"):
                qid = odoo.crear("stock.quant", {"product_id": l.producto.odoo_id, "location_id": ubic, "lot_id": l.odoo_id,
                                                 "inventory_quantity": float(l.cantidad_disponible)})
                odoo.ejecutar("stock.quant", "action_apply_inventory", [qid])
                r["existencias"] += 1
        except (xmlrpc.client.Fault, IndexError, KeyError) as exc:
            r["avisos"].append(f"No se actualizaron las existencias (¿está instalada la app Inventario?): {exc}")
    informar("Sincronización terminada.")
    return r
