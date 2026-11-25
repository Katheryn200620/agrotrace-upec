# Inspección previa del proyecto (24/11/2026)

Antes de modificar AgroTrace-UPEC se revisó el proyecto existente.

| Aspecto | Encontrado |
|---|---|
| Versiones | Python 3.13, Django 6.1, Django REST Framework instalado sin endpoints |
| Base de datos | SQLite (configurable a PostgreSQL o MySQL en `.env`) |
| Aplicaciones | cuentas, dashboard, productores, parcelas, productos, cosechas, lotes, trazabilidad, transporte, reportes |
| Modelos | 17 (Area, Perfil, RegistroAuditoria, Productor, Parcela, Labor, Producto, Cosecha, Recepcion, Clasificacion, Lote, RelacionLote, EventoTrazabilidad, EscaneoQR, SimulacroRetiro, Transportista, Despacho) |
| Migraciones | 10 aplicadas, ninguna pendiente (`makemigrations --check`) |
| Usuarios | Modelo de usuario de Django; perfiles con área; 1 administrador y 9 operadores de prueba; sin grupos |
| Seguridad | Permisos en el servidor por área y por responsable; auditoría no editable; 24 pruebas correctas |
| Faltaba | Ventas y clientes, inventario, API REST, chatbot, agentes guiados, voz, menú por 12 áreas, gráficas por área, documentos |

## Riesgos y decisiones
- No borrar ni renombrar tablas, campos, códigos de lote ni URL existentes: solo se agregan tablas y campos (migraciones no destructivas).
- Las nuevas funciones reutilizan los formularios, vistas y permisos existentes para no abrir accesos.
- Lo que depende de servicios externos (Odoo, IA, voz y cámara reales) se prueba con simuladores y se declara pendiente.

## Migraciones creadas
cuentas 0002 (opciones de área), trazabilidad 0002 (tipo «venta»), productos 0002 (stock mínimo), transporte 0002 (venta del despacho),
comercial 0001, asistente 0001, integracion 0001 y authtoken (tokens de la API).
