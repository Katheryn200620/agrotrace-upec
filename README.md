# AgroTrace-UPEC

Aplicativo web de **procedencia digital de productos hortofrutícolas**.

Universidad Politécnica Estatal del Carchi · Carrera de Logística y Transporte
TIC's Aplicadas a la Logística · PAO 2026B

**Autoras:** Dayanara Scarlet Vaca Bravo · Katheryn Maylin Cumbal Narváez
**Docente:** Ing. Omar Alpala

---

## Qué hace

Registra y rastrea cada etapa de la cadena hortofrutícola —productor → parcela → labor →
cosecha → recepción → clasificación → lote → venta → transporte → cliente— y genera un
código QR GS1 Digital Link por lote para consultar la procedencia desde el teléfono.

Incluye menú en 12 áreas con paneles de indicadores, inventario con entradas y salidas,
asistente virtual, agentes guiados, control por voz, API REST documentada, integración
con Odoo y etiquetas QR imprimibles.

## Cómo ejecutarlo

Instrucciones completas en **[`aplicacion/README.md`](aplicacion/README.md)**. En resumen,
dentro de la carpeta `aplicacion`:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py cargar_datos_demo
python manage.py runserver
```

Luego abra <http://127.0.0.1:8000>.

## Contenido del repositorio

| Carpeta | Qué contiene |
|---|---|
| `aplicacion/` | Código fuente del sistema (Django) |
| `documentacion/` | Informe de resultados, manual de usuario, manual de instalación y documentación de la API |
| `evidencias/` | Capturas de pantalla, fotografías y videos |
| `pruebas/` | Encuesta de usuarios, matriz de validación y pruebas técnicas |
| `prototipo/` | Documentación del prototipo físico y etiquetas QR |
| `LEEME.txt` | Guía rápida y mapa de requerimiento → evidencia |
