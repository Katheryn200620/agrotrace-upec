"""
F3 – Contratos de datos en JSON.
1) «Cosecha del centro → planta» (propio del proyecto 3).
2) «Despacho de planta → recepción en CEDI» (común a los siete proyectos del libro).
"""
from django.utils import timezone

VERSION = "1.1"


def cosecha_a_planta(c):
    p = c.parcela
    return {
        "contrato": "cosecha_centro_a_planta", "version": VERSION,
        "origen": {"productor_codigo": c.productor.codigo, "productor": c.productor.nombre_publico,
                   "parcela_codigo": p.codigo, "parcela_gln": p.gln, "cultivo": p.cultivo.nombre, "variedad": p.variedad,
                   "coordenadas": {"lat": float(p.latitud), "lon": float(p.longitud)} if p.latitud is not None else None},
        "cosecha": {"codigo": c.codigo, "fecha": c.fecha.isoformat(), "producto": c.producto.nombre,
                    "gtin": c.producto.gtin, "cantidad": float(c.cantidad), "unidad": c.unidad},
        "labores_previas": [{"tipo": l.tipo, "fecha": l.fecha.isoformat(), "insumo": l.insumo, "dosis": l.dosis}
                            for l in p.labores.filter(fecha__lte=c.fecha)[:10]],
        "destino": {"planta": "Planta Hortofrutícola UPEC"},
    }


def despacho_a_cedi(d):
    lote = d.lote
    return {
        "contrato": "despacho_planta_a_cedi", "version": VERSION,
        "despacho_id": d.codigo, "planta_origen": "hortofruticola",
        "fecha_despacho": timezone.localtime(d.salida).isoformat(),
        "producto": {"gtin": lote.producto.gtin, "nombre": lote.producto.nombre, "unidad": lote.unidad},
        "lote": {"codigo": lote.codigo, "fecha_produccion": lote.fecha_creacion.isoformat(),
                 "fecha_vencimiento": lote.fecha_vencimiento.isoformat() if lote.fecha_vencimiento else None,
                 "categoria_calidad": lote.categoria, "parcelas_origen": [p.codigo for p in lote.parcelas()]},
        "cantidad": float(d.cantidad),
        "transporte": {"transportista": d.transportista.nombre if d.transportista else None, "vehiculo": d.vehiculo,
                       "refrigerado": bool(d.transportista and d.transportista.refrigerado)},
        "condiciones": {"temperatura_recomendada_c": "4–8", "fragil": True},
        "gs1_digital_link": lote.link_gs1,
        "destino": {"tipo": d.tipo_destino, "nombre": d.destino},
    }
