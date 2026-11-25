"""
SIMULADOR de la API XML-RPC de Odoo 18 — SOLO PARA PRUEBAS.

No es Odoo. Sirve para comprobar que el código de integración (integracion/odoo.py) envía bien los datos
cuando todavía no se tiene un Odoo instalado. Para la integración real use Odoo Community o un plan con API.

Uso:  python herramientas/simulador_odoo.py      (escucha en http://127.0.0.1:8069, usuario admin / clave admin)
"""
from xmlrpc.server import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler
DB = {}
class H(SimpleXMLRPCRequestHandler):
    rpc_paths = ("/xmlrpc/2/common", "/xmlrpc/2/object")
def version(): return {"server_version": "18.0"}
def authenticate(db, u, p, x): return 2 if (u, p) == ("admin", "admin") else False
def execute_kw(db, uid, pwd, modelo, metodo, args, kw):
    tabla = DB.setdefault(modelo, {})
    if metodo == "search":
        dom = args[0]
        res = [i for i, r in tabla.items() if all(r.get(c) == v for c, _op, v in dom)]
        return res[: kw.get("limit", len(res))]
    if metodo == "create":
        i = len(tabla) + 1; tabla[i] = args[0]; return i
    if metodo == "write": return True
    if metodo == "read": return [{"id": 2, "company_id": [1, "UPEC"]}]
    if metodo == "search_read": return [{"id": 1, "lot_stock_id": [8, "WH/Stock"]}]
    if metodo == "action_apply_inventory": return True
    raise Exception("método no simulado " + metodo)
def resumen(): return {k: len(v) for k, v in DB.items()}
def servidor(puerto=8069):
    s = SimpleXMLRPCServer(("127.0.0.1", puerto), requestHandler=H, allow_none=True, logRequests=False)
    for f in (version, authenticate, execute_kw, resumen):
        s.register_function(f)
    return s


if __name__ == "__main__":
    print("Simulador de Odoo (solo pruebas) en http://127.0.0.1:8069 — Ctrl + C para detener")
    servidor().serve_forever()
