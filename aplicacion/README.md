# AgroTrace-UPEC

Aplicativo web de **procedencia digital de productos hortofrutícolas**.
Universidad Politécnica Estatal del Carchi (UPEC) · Carrera de Logística y Transporte · TIC's Aplicadas a la Logística.

Registra cada etapa de la cadena (productor → parcela → labor → cosecha → recepción → clasificación → lote → venta → transporte → cliente),
genera un **QR GS1 Digital Link** por lote y separa el trabajo entre un **administrador general** y **operadores por área**.

Incluye: menú en **12 áreas** con paneles de indicadores y gráficas, **clientes y ventas**, **inventario** con entradas y salidas,
**asistente virtual (chatbot)**, **agentes guiados**, **control por voz**, **API REST** documentada, **integración con Odoo**
y **etiquetas QR** imprimibles.

---

## 1. Requisitos

- Python 3.12 o 3.13 (marcar «Add python.exe to PATH» al instalar)
- Visual Studio Code
- Git (opcional, para GitHub)

## 2. Instalación paso a paso (Windows, terminal de VS Code)

> ¿Ya tenía una versión anterior con datos? Copie su `db.sqlite3` y su `.env` a esta carpeta y ejecute `python manage.py migrate`: las migraciones nuevas solo agregan tablas y campos.

Abra en VS Code la carpeta que contiene `manage.py` y luego **Terminal → Nueva terminal**:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py cargar_datos_demo
python manage.py runserver
```

Si PowerShell no deja activar el entorno: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

Abra **http://127.0.0.1:8000**. La primera página es **Inicio** (catálogo de productos con sus fotografías); el **Panel de procedencia** está justo debajo en el menú (`/panel-procedencia/`).

Para usarlo otro día: `.venv\Scripts\activate` y `python manage.py runserver`.

## 3. Cuentas de prueba (clave para todas: `upec2026`)

| Usuario | Rol | Qué puede hacer |
|---|---|---|
| `admin` | Administrador general | Todo: supervisa, revisa, corrige con justificación, gestiona cuentas, áreas y auditoría |
| `productores` | Operador de productores | Sus productores (único que ve cédula, teléfono y correo) |
| `parcelas` | Operador de parcelas y cultivos | Sus parcelas y labores |
| `productos` | Operador de productos | Catálogo de productos (GTIN) |
| `cosechas` y `cosechas2` | Operadores de cosechas | Sus cosechas, recepciones y clasificaciones (no ven las del otro) |
| `lotes` | Operador de lotes | Sus lotes: crear, dividir, combinar, transformar, retirar |
| `trazabilidad` | Operador de trazabilidad | Eventos, correcciones y simulacro de retiro (E1) |
| `transporte` | Operador de transporte | Despachos, transportistas, salidas y entregas |
| `comercial` | Operador de clientes y ventas | Clientes, ventas y lotes entregados a cada cliente |
| `reportes` | Consulta, reportes y auditoría | Solo consulta y exportación, sin editar |

Las cuentas nuevas las crea el administrador en **Administración → Usuarios y áreas**.

## 4. Seguridad aplicada

- Todos los controles se hacen **en el servidor** (`cuentas/permissions.py` y `cuentas/mixins.py`), no solo ocultando botones.
- Cada operador **solo ve y edita los registros de los que es responsable** y solo dentro de su área.
  Cambiar el número en la URL o enviar formularios manipulados devuelve **403** y queda en la auditoría.
- **Consulta compartida**: un operador puede abrir datos de otras áreas que necesita (p. ej. el de lotes abre la cosecha de origen), pero sin poder editarlos.
- El **responsable** lo asigna el servidor; el operador no puede elegirlo ni cambiar su área o permisos.
- **Historial inmutable**: los eventos de trazabilidad y la auditoría no se editan ni se borran; las correcciones se agregan como eventos nuevos.
- El **origen de un lote** no se cambia al editar; solo el administrador puede corregirlo, con justificación.
- No se puede **despachar más** de lo disponible (verificación con bloqueo de fila en la base de datos).
- Las cuentas **se desactivan, no se eliminan** (se conserva su historial). Un área deshabilitada bloquea a sus operadores.
- La **página pública del QR** no muestra cédulas, teléfonos, correos ni nombres de personas que no lo autorizaron.
- Protección CSRF, contraseñas con validación, configuración por variables de entorno (`.env`).

## 5. Pruebas automáticas

```powershell
python manage.py test
```

59 pruebas:
- `cuentas/tests/test_seguridad.py` (24): aislamiento entre operadores, URLs manipuladas, datos personales, auditoría, origen de lotes, stock.
- `api/tests.py` (18): token, permisos de la API, ventas y despachos, 12 paneles, menú por áreas y base de datos vacía.
- `asistente/tests.py` (9): chatbot con datos reales y permisos, agentes guiados, registro de comandos de voz.
- `dashboard/tests.py` (5): página de Inicio (productos reales, foto subida, archivo inválido) y Panel de procedencia.
- `integracion/tests.py` (3): sincronización con el **simulador** de Odoo (sin duplicar) y credenciales incorrectas.

## 5.1 Asistente, agentes y voz

- **Asistente virtual**: botón redondo abajo a la derecha o Área 1 → Asistente virtual. Responde con consultas a la base de datos
  y respeta los permisos. IA opcional en `.env` (`IA_PROVEEDOR=anthropic` u `openai` compatible, por ejemplo Ollama local).
- **Agentes guiados**: Área 1 → Agentes guiados (productor, parcela, cosecha, recepción, lote, venta y consulta de trazabilidad).
- **Control por voz**: micrófono de la barra superior (Chrome o Edge). Lista de comandos en Área 1 → Control por voz.

## 5.2 API REST

`http://127.0.0.1:8000/api/v1/` · token en `POST /api/v1/token/` · documentación completa en `docs/Documentacion_API.md`.

## 6. Estructura

```
AgroTrace-UPEC/
├── agrotrace/        configuración (settings, urls, gs1)
├── cuentas/          áreas, perfiles, permisos, auditoría, usuarios, pruebas de seguridad
├── dashboard/        panel del administrador y paneles de operadores
├── productores/      productores
├── parcelas/         parcelas, cultivos y labores (+ GeoJSON para QGIS)
├── productos/        catálogo de productos (GTIN-14)
├── cosechas/         cosechas, recepción en planta y clasificación de calidad
├── lotes/            lotes, división, combinación, transformación, retiro, QR
├── trazabilidad/     historial EPCIS, consulta pública, simulacro E1, contratos JSON, Odoo
├── transporte/       transportistas y despachos
├── reportes/         reportes con filtros y exportación CSV
├── comercial/        clientes y ventas
├── api/              API REST v1 (Django REST Framework)
├── asistente/        chatbot, agentes guiados y control por voz
├── integracion/      integración con Odoo (página, bitácora y sincronización)
├── herramientas/     simulador de Odoo SOLO para pruebas
├── docs/             Documentacion_API.md
├── templates/        base, ingreso y errores
├── static/           css/estilos.css (colores en variables), js/app.js, librerías locales
└── integraciones/    flujo de n8n
```

## 7. Integraciones (fase F5)

- **Odoo**: configure `ODOO_URL`, `ODOO_DB`, `ODOO_USER`, `ODOO_PASSWORD` en `.env` y use Área 12 → Integración ERP,
  o ejecute `python manage.py sincronizar_odoo --probar` y `python manage.py sincronizar_odoo --existencias`.
  Envía productos, proveedores, clientes, compras, lotes, ventas y existencias. Para practicar sin Odoo:
  `python herramientas/simulador_odoo.py` (simulador, no es Odoo).
- **n8n**: importe `integraciones/n8n_aviso_cosecha.json` y ponga la URL del webhook en `N8N_WEBHOOK_COSECHA`.
- **QGIS**: capa vectorial HTTP `http://127.0.0.1:8000/parcelas/mapa.geojson` (incluye % de rechazo por parcela).
- **EPCIS / contratos**: botones «EPCIS» en la ficha del lote y «Contrato JSON» en cosechas y despachos al CEDI.

## 8. QR en el celular

El celular y el computador deben estar en la misma red Wi-Fi. En `.env` ponga `SITE_URL=http://IP-DEL-COMPUTADOR:8000`
y ejecute `python manage.py runserver 0.0.0.0:8000`.

## 9. Base de datos

SQLite por defecto. Para PostgreSQL: `pip install "psycopg[binary]"` y en `.env` `DB_ENGINE=postgres` con sus datos.
Para MySQL: `pip install mysqlclient` y `DB_ENGINE=mysql`. Luego `python manage.py migrate`.

> Los datos de `cargar_datos_demo` son **de prueba**. Para el informe use datos reales de la planta.
