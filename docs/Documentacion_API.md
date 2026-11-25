# Documentación de la API REST de AgroTrace-UPEC (v1)

Universidad Politécnica Estatal del Carchi · TIC's Aplicadas a la Logística · PAO 2026B
Autoras: Dayanara Scarlet Vaca Bravo y Katheryn Maylin Cumbal Narváez

La API permite que otros sistemas (Odoo, n8n, una aplicación móvil u hojas de cálculo) lean y registren información de AgroTrace-UPEC. Usa **las mismas reglas que la web**: los permisos por área, las validaciones de los formularios, los eventos de trazabilidad y la auditoría.

- Dirección base (en su computador): `http://127.0.0.1:8000/api/v1/`
- Formato: JSON (UTF-8). Las cantidades y los precios se envían como texto decimal (`"10.50"`).
- API navegable: abra `http://127.0.0.1:8000/api/v1/` con la sesión iniciada en el navegador.
- Ayuda dentro del aplicativo: Área 12 → API REST (`/api/docs/`).

---

## 1. Autenticación

Hay tres formas de autenticarse:

| Forma | Cuándo usarla |
|---|---|
| Sesión del navegador | Al probar en la API navegable con la sesión iniciada |
| **Token** (recomendada) | Integraciones (n8n, scripts, app móvil) |
| Usuario y contraseña (Basic) | Pruebas rápidas con `curl` |

### Obtener un token

```
POST /api/v1/token/
Content-Type: application/x-www-form-urlencoded

username=comercial&password=upec2026
```

Respuesta `200 OK`:

```json
{"token": "b6cac9c6b8117094b28c57714ae9cb874c79a8a6"}
```

Después envíe la cabecera en cada solicitud:

```
Authorization: Token b6cac9c6b8117094b28c57714ae9cb874c79a8a6
```

Si el usuario o la contraseña no coinciden, la respuesta es `400 Bad Request`. Sin credenciales, cualquier recurso responde `401` o `403`.

---

## 2. Reglas de autorización

| Operación | Quién puede |
|---|---|
| Listar (`GET /recurso/`) | Administrador general y área de consulta: todos los registros. Operador del área: **solo sus registros**. Otras áreas: `403` |
| Ver uno (`GET /recurso/{id}/`) | Lo anterior y, además, las áreas con consulta compartida (por ejemplo, lotes puede ver la cosecha de origen). Sin permiso: `403` y queda en la auditoría |
| Crear (`POST`) | Operador del área con permiso de crear, o administrador. El **responsable lo asigna el servidor** |
| Modificar (`PATCH`, `PUT`) | El responsable del registro (si tiene permiso de editar) o el administrador. Si el administrador modifica un registro ajeno debe enviar `justificacion` |
| Eliminar (`DELETE`) | Solo en catálogos y registros que admiten borrado, por su responsable con permiso o el administrador. Si otros registros dependen de él: `409` |

Los **datos personales** (cédula o RUC, teléfono, correo, dirección) solo aparecen para el área dueña de esos datos y el administrador; para los demás se omiten de la respuesta.

Los **eventos de trazabilidad** son de solo lectura: no se crean, modifican ni borran por la API (`405`).

---

## 3. Recursos

| Recurso | Ruta | Métodos | Área responsable | Filtros (`?campo=valor`) | Búsqueda `?q=` |
|---|---|---|---|---|---|
| Productores | `/productores/` | GET, POST, PATCH, PUT, DELETE | Productores | `estado`, `tipo` | código, nombre, cantón |
| Parcelas | `/parcelas/` | GET, POST, PATCH, PUT, DELETE | Parcelas | `productor`, `cultivo`, `estado_cultivo` | código, nombre |
| Labores | `/labores/` | GET, POST, PATCH, PUT, DELETE | Parcelas | `parcela`, `tipo` | insumo, descripción |
| Productos | `/productos/` | GET, POST, PATCH, PUT, DELETE | Productos | `categoria`, `estado` | código, nombre, GTIN |
| Cosechas | `/cosechas/` | GET, POST, PATCH, PUT, DELETE | Cosechas | `parcela`, `producto`, `productor` | código |
| Recepciones | `/recepciones/` | GET, POST, PATCH, PUT, DELETE | Cosechas | `cosecha` | código de cosecha |
| Clasificaciones | `/clasificaciones/` | GET, POST, PATCH, PUT, DELETE | Cosechas | `recepcion`, `categoria` | causa de rechazo |
| Lotes | `/lotes/` | GET, POST, PATCH, PUT | Lotes | `producto`, `estado`, `categoria` | código |
| Transportistas | `/transportistas/` | GET, POST, PATCH, PUT, DELETE | Transporte | `activo` | nombre, placa |
| Despachos | `/despachos/` | GET, POST, PATCH, PUT | Transporte | `estado`, `lote`, `venta` | código, destino, lote |
| Clientes | `/clientes/` | GET, POST, PATCH, PUT, DELETE | Comercial | `tipo`, `activo` | código, nombre, ciudad |
| Ventas | `/ventas/` | GET, POST, PATCH, PUT | Comercial | `estado`, `cliente`, `lote`, `canal` | código, cliente, lote |
| Eventos | `/eventos/` | GET | Trazabilidad | `lote` (código), `cosecha` (código), `tipo` | — |
| Trazabilidad de un lote | `/trazabilidad/{codigo}/` | GET | Lotes, trazabilidad, transporte, comercial, consulta | — | — |
| Indicadores generales | `/indicadores/` | GET | Administrador y consulta | — | — |

**Paginación:** 25 registros por página. Use `?page=2` y `?tamano=50` (máximo 200).

---

## 4. Ejemplos

Las respuestas de esta sección se obtuvieron con los datos de prueba (`python manage.py cargar_datos_demo`).

### 4.1 Listar ventas (operador comercial)

```
GET /api/v1/ventas/?tamano=1
Authorization: Token …
```

`200 OK`

```json
{
  "count": 2,
  "next": "http://127.0.0.1:8000/api/v1/ventas/?page=2&tamano=1",
  "previous": null,
  "results": [{
    "id": 2, "codigo": "V-20261118-01", "cliente": 2, "lote": 3, "fecha": "2026-11-18",
    "cantidad": "80.00", "precio_unitario": "1.20", "total": "96.00", "canal": "pedido",
    "referencia": "", "estado": "despachada", "por_despachar": "0.00", "observaciones": "",
    "responsable_nombre": "Gabriela Erazo", "estado_revision": "pendiente"
  }]
}
```

### 4.2 Registrar una venta

```
POST /api/v1/ventas/
Authorization: Token …
Content-Type: application/json

{"cliente": 3, "lote": 1, "cantidad": "10", "canal": "directa"}
```

`201 Created` con la venta creada (el código `V-AAAAMMDD-NN`, el precio referencial del producto si no se envía `precio_unitario` y el estado `pendiente`). Además se registra un evento «Venta registrada» en el historial del lote.

Si la cantidad supera lo disponible y no comprometido, `400 Bad Request`:

```json
{"cantidad": ["Del lote H26110101 quedan 120.00 kg sin comprometer en otras ventas."]}
```

### 4.3 Despachar una venta (operador de transporte)

```
POST /api/v1/despachos/
{"venta": 3, "cantidad": "10", "salida": "2026-11-25T08:00", "origen": "Planta Hortofrutícola UPEC, Tulcán", "tipo_destino": "cliente"}
```

El lote y el destino se toman de la venta. La cantidad se descuenta del lote y la venta pasa a `despachada` (o `parcial` si falta despachar).

### 4.4 Acceso a otra área

```
GET /api/v1/productores/          (con el token del operador comercial)
```

`403 Forbidden`

```json
{"detail": "No tiene permiso para realizar esta acción."}
```

El intento queda en la auditoría (Área 10 → Auditoría).

### 4.5 Trazabilidad completa de un lote

```
GET /api/v1/trazabilidad/H26111001/
```

`200 OK` (extracto)

```json
{
  "lote": {"codigo": "H26111001", "producto_nombre": "Mora de Castilla", "estado": "entregado", "completitud": 100, "…": "…"},
  "gs1_digital_link": "http://127.0.0.1:8000/01/07861234000029/10/H26111001",
  "lotes_de_origen": [],
  "productores": ["Centro Experimental UPEC"],
  "parcelas": [{"codigo": "P-02", "nombre": "Huerto de mora", "gln": "7861234900022", "latitud": 0.8119, "longitud": -77.7196}],
  "cosechas": [{"codigo": "C-P-02-20261109-1", "fecha": "2026-11-09", "cantidad": 85.0, "unidad": "kg"}],
  "control_eventos": [{"paso": "Cosecha", "registrado": true}, {"paso": "Recepción", "registrado": true}, "…"],
  "eventos": [{"tipo": "cosecha", "biz_step": "harvesting", "fecha_hora": "2026-11-09T07:00:00-05:00", "lugar": "Parcela P-02 (GLN 7861234900022)", "…": "…"}],
  "despachos": [{"codigo": "D-20261112-01", "destino": "Pedido web #1001 – Tulcán", "estado": "entregado"}]
}
```

### 4.6 Modificar un registro propio

```
PATCH /api/v1/productores/5/
{"telefono": "0991234567"}
```

Solo se envían los campos que cambian. Si el registro es de otro operador: `403`.

### 4.7 Con curl (Windows PowerShell)

```powershell
$t = (Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/token/ -Body @{username="lotes"; password="upec2026"}).token
Invoke-RestMethod http://127.0.0.1:8000/api/v1/lotes/ -Headers @{Authorization="Token $t"}
```

---

## 5. Códigos de respuesta

| Código | Significado |
|---|---|
| 200 | Correcto |
| 201 | Registro creado |
| 204 | Registro eliminado |
| 400 | Datos inválidos: el cuerpo indica el campo y el motivo |
| 401 / 403 | Sin credenciales o sin permiso |
| 404 | No existe |
| 405 | Operación no permitida para ese recurso (por ejemplo, borrar eventos) |
| 409 | No se puede eliminar porque otros registros dependen de él |
| 429 | Demasiadas solicitudes (límite: 600 por minuto por usuario) |

---

## 6. Integraciones que usan la API

- **n8n:** recibe el aviso de cada cosecha (webhook) y puede consultar `/api/v1/trazabilidad/{codigo}/` con un token.
- **Odoo:** la sincronización usa la API XML-RPC de Odoo desde el aplicativo (Área 12 → Integración ERP); no necesita la API REST.
- **QGIS:** capa vectorial `http://127.0.0.1:8000/parcelas/mapa.geojson`.

## 7. Pruebas automáticas de la API

Las pruebas están en `api/tests.py` y se ejecutan con `python manage.py test api`. Comprueban: token, permisos por área, ocultamiento de datos personales, validación de stock en ventas, despacho de una venta, eventos de solo lectura y trazabilidad completa de un lote.
