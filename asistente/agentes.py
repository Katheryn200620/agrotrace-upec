"""
Agentes guiados: llevan al usuario paso a paso por los registros más frecuentes.

Cada agente reutiliza la vista de creación del módulo (mismo formulario, mismas validaciones,
mismos permisos, eventos y auditoría); solo cambia la presentación: un paso a la vez con instrucciones.
"""
from comercial import views as comercial
from cosechas import views as cosechas
from cuentas.models import Area
from lotes import views as lotes
from parcelas import views as parcelas
from productores import views as productores

# clave: (título, descripción, icono, vista de creación, área, pasos [(título, instrucción, campos)])
AGENTES = {
    "productor": ("Registrar un productor", "Datos del agricultor u organización que abastece a la planta.", "bi-person-plus",
                  productores.Crear, Area.PRODUCTORES, [
                      ("¿Quién es?", "Escriba el nombre completo o la razón social y el tipo de productor. El código PR-000 se genera solo.",
                       ["nombre", "tipo", "identificacion", "codigo"]),
                      ("¿Dónde produce?", "La ubicación aparece en la ficha pública del QR (sin datos personales).",
                       ["provincia", "canton", "parroquia"]),
                      ("Contacto y autorización", "El teléfono y el correo solo los ve su área. Marque la autorización si el productor acepta mostrar su nombre.",
                       ["telefono", "correo", "estado", "mostrar_nombre_publico"]),
                  ]),
    "parcela": ("Registrar una parcela", "Terreno donde se cultiva el producto; recibe un código GLN.", "bi-geo-alt",
                parcelas.ParcelaCrear, Area.PARCELAS, [
                    ("Productor y cultivo", "Elija a quién pertenece la parcela y qué se siembra en ella.", ["productor", "cultivo", "variedad"]),
                    ("Identificación y tamaño", "Use un código corto (ej. P-05) y la superficie.", ["codigo", "nombre", "superficie", "unidad_superficie"]),
                    ("Ubicación", "Las coordenadas permiten ver la parcela en el mapa de QGIS. Puede tomarlas del celular.",
                     ["latitud", "longitud", "altitud_msnm"]),
                    ("Estado del cultivo", "Indique la fecha de siembra y en qué etapa está.", ["fecha_siembra", "estado_cultivo"]),
                ]),
    "cosecha": ("Registrar una cosecha", "Lo recolectado en una parcela en una fecha.", "bi-basket",
                cosechas.CosechaCrear, Area.COSECHAS, [
                    ("Origen", "Elija la parcela, su productor y el producto cosechado. Deben coincidir con lo registrado en la parcela.",
                     ["parcela", "productor", "producto"]),
                    ("Cantidad y fecha", "Escriba cuánto se recolectó y cuándo.", ["fecha", "cantidad", "unidad"]),
                    ("Observaciones", "Anote algo importante (clima, estado del producto). Revise y guarde.", ["observaciones"]),
                ]),
    "recepcion": ("Recibir una cosecha en planta", "Pesaje y control de temperatura al llegar.", "bi-box-arrow-in-down",
                  cosechas.RecepcionCrear, Area.COSECHAS, [
                      ("¿Qué llega?", "Elija la cosecha que llega a la planta.", ["cosecha", "fecha_hora"]),
                      ("Pesaje y control", "Registre el peso en la balanza, la temperatura y el tiempo de recepción.",
                       ["peso_recibido", "temperatura", "minutos_recepcion"]),
                      ("Observaciones", "Anote novedades. Después clasifique lo recibido.", ["observaciones"]),
                  ]),
    "lote": ("Crear un lote", "Agrupa cosechas recibidas; genera el código y el QR.", "bi-box-seam",
             lotes.Crear, Area.LOTES, [
                 ("Producto y origen", "Elija el producto y las cosechas recibidas que forman el lote (Ctrl + clic para varias).",
                  ["producto", "cosechas"]),
                 ("Cantidad y calidad", "La cantidad no puede superar lo aprovechable de esas cosechas (recibido menos rechazo).",
                  ["categoria", "cantidad_inicial", "fecha_creacion"]),
                 ("Ubicación y proceso", "Indique dónde se guarda y qué proceso se aplicó realmente.", ["ubicacion", "proceso", "publicado"]),
             ]),
    "venta": ("Registrar una venta", "Compromete cantidad de un lote para un cliente.", "bi-cart-plus",
              comercial.VCrear, Area.COMERCIAL, [
                  ("Cliente", "Elija el cliente. Si no existe, regístrelo primero en Clientes.", ["cliente"]),
                  ("Lote y cantidad", "Elija el lote. Solo puede vender lo disponible que no esté comprometido en otras ventas.",
                   ["lote", "cantidad"]),
                  ("Precio y referencia", "Si deja vacío el precio se usa el referencial del producto.",
                   ["precio_unitario", "canal", "fecha", "referencia", "observaciones"]),
              ]),
}


def clase_agente(clave):
    titulo, desc, icono, Vista, area, pasos = AGENTES[clave]

    def contexto_base(self, **extra):
        ctx = Vista.contexto_base(self, **extra)
        ctx.update(agente={"clave": clave, "titulo": titulo, "descripcion": desc, "icono": icono}, pasos=pasos,
                   titulo=titulo, todos_los_campos=[c for _t, _a, campos in pasos for c in campos])
        return ctx

    return type(f"Agente_{clave}", (Vista,), {"plantilla_form": "asistente/agente.html", "contexto_base": contexto_base})
