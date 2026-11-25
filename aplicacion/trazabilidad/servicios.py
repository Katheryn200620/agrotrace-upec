"""Servicios de trazabilidad: registrar eventos y avisos automáticos."""
import json
import logging
import threading
import urllib.request

from django.conf import settings

from .models import EventoTrazabilidad

log = logging.getLogger(__name__)
PLANTA = "Planta Hortofrutícola UPEC, Tulcán"
TIPO_EPCIS = {"creacion_lote": "TransformationEvent", "transformacion": "TransformationEvent",
              "division": "TransformationEvent", "combinacion": "TransformationEvent"}


def registrar_evento(tipo, responsable, descripcion, lugar=PLANTA, lote=None, cosecha=None, parcela=None,
                     cantidad=None, unidad="", observaciones="", fecha_hora=None, disposicion="active",
                     origen="sistema", corrige=None):
    datos = dict(tipo=tipo, tipo_epcis=TIPO_EPCIS.get(tipo, "ObjectEvent"), responsable=responsable,
                 descripcion=descripcion[:250], lugar=lugar[:150], lote=lote, cosecha=cosecha, parcela=parcela,
                 cantidad=cantidad, unidad=unidad, observaciones=observaciones, disposicion=disposicion,
                 origen=origen, corrige=corrige)
    if fecha_hora is not None:
        datos["fecha_hora"] = fecha_hora
    return EventoTrazabilidad.objects.create(**datos)


def avisar_cosecha_n8n(cosecha):
    """F5: aviso automático de cosecha mediante un webhook de n8n (si está configurado)."""
    url = settings.N8N_WEBHOOK_COSECHA
    if not url:
        return
    datos = {"evento": "cosecha_registrada", "codigo": cosecha.codigo, "parcela": cosecha.parcela.codigo,
             "producto": cosecha.producto.nombre, "cantidad_kg": float(cosecha.cantidad),
             "fecha": cosecha.fecha.isoformat(), "responsable": cosecha.responsable.get_full_name()}

    def enviar():
        try:
            req = urllib.request.Request(url, data=json.dumps(datos).encode(), headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5)
        except Exception as exc:  # el aplicativo sigue funcionando aunque n8n no responda
            log.warning("No se pudo avisar a n8n: %s", exc)

    threading.Thread(target=enviar, daemon=True).start()
