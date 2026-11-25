"""Reglas comerciales: reservas de stock y estado de las ventas según sus despachos."""
from decimal import Decimal

from django.db.models import Sum


def reservado(lote, excluir_venta=None):
    """Cantidad de un lote comprometida en ventas que todavía no se despachan."""
    from .models import Venta
    total = Decimal("0")
    qs = Venta.objects.filter(lote=lote, estado__in=["pendiente", "parcial"])
    if excluir_venta is not None and excluir_venta.pk:
        qs = qs.exclude(pk=excluir_venta.pk)
    for v in qs:
        total += v.por_despachar
    return total


def disponible_para_vender(lote, excluir_venta=None):
    return max(lote.cantidad_disponible - reservado(lote, excluir_venta), Decimal("0"))


def actualizar_estado(venta):
    """Recalcula el estado de la venta a partir de sus despachos (no toca las anuladas)."""
    if venta.estado == "anulada":
        return venta.estado
    activos = venta.despachos.exclude(estado="cancelado")
    despachado = activos.aggregate(t=Sum("cantidad"))["t"] or Decimal("0")
    if despachado <= 0:
        nuevo = "pendiente"
    elif despachado < venta.cantidad:
        nuevo = "parcial"
    elif activos.exclude(estado="entregado").exists():
        nuevo = "despachada"
    else:
        nuevo = "entregada"
    if nuevo != venta.estado:
        venta.estado = nuevo
        venta.save(update_fields=["estado", "actualizado_en"])
    return nuevo
