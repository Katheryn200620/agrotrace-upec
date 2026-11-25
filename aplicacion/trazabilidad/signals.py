"""Eventos automáticos: cada registro de procedencia deja su evento en el historial."""
from datetime import datetime, time, timedelta

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from cosechas.models import Clasificacion, Cosecha, Recepcion
from lotes.models import Lote
from parcelas.models import Labor

from .servicios import PLANTA, avisar_cosecha_n8n, registrar_evento


def _momento(fecha, hora):
    if fecha >= timezone.localdate():
        return timezone.now()
    return timezone.make_aware(datetime.combine(fecha, time(hora, 0)))


@receiver(post_save, sender=Labor)
def ev_labor(sender, instance, created, **kw):
    if created:
        p = instance.parcela
        registrar_evento("cultivo", instance.responsable, f"{instance.get_tipo_display()} en {p.codigo}",
                         lugar=f"Parcela {p.codigo} (GLN {p.gln})", parcela=p, fecha_hora=_momento(instance.fecha, 8),
                         observaciones=" ".join(x for x in [instance.insumo, instance.dosis] if x))


@receiver(post_save, sender=Cosecha)
def ev_cosecha(sender, instance, created, **kw):
    if created:
        p = instance.parcela
        registrar_evento("cosecha", instance.responsable,
                         f"Cosecha {instance.codigo}: {instance.cantidad} {instance.unidad} de {instance.producto.nombre}",
                         lugar=f"Parcela {p.codigo} (GLN {p.gln})", cosecha=instance, parcela=p,
                         cantidad=instance.cantidad, unidad=instance.unidad, fecha_hora=_momento(instance.fecha, 7))
        avisar_cosecha_n8n(instance)


@receiver(post_save, sender=Recepcion)
def ev_recepcion(sender, instance, created, **kw):
    if created:
        t = f"; temperatura {instance.temperatura} °C" if instance.temperatura is not None else ""
        registrar_evento("recepcion", instance.responsable, f"Recepción de la cosecha {instance.cosecha.codigo}{t}",
                         lugar=f"{PLANTA} – área de recepción", cosecha=instance.cosecha,
                         cantidad=instance.peso_recibido, unidad="kg", fecha_hora=instance.fecha_hora,
                         disposicion="in_progress")


@receiver(post_save, sender=Clasificacion)
def ev_clasificacion(sender, instance, created, **kw):
    if created:
        r = instance.recepcion
        causa = f" (causa: {instance.causa_rechazo})" if instance.causa_rechazo else ""
        registrar_evento("clasificacion", instance.responsable,
                         f"{instance.get_categoria_display()}: {instance.cantidad} kg – {instance.get_metodo_display()}{causa}",
                         lugar=f"{PLANTA} – mesa de clasificación", cosecha=r.cosecha, cantidad=instance.cantidad,
                         unidad="kg", fecha_hora=r.fecha_hora + timedelta(minutes=30),
                         disposicion="non_conformant" if instance.categoria == "rechazo" else "conformant")


@receiver(post_save, sender=Lote)
def ev_lote(sender, instance, created, **kw):
    if created and not getattr(instance, "_sin_evento", False):
        registrar_evento("creacion_lote", instance.responsable,
                         f"Creación del lote {instance.codigo}: {instance.cantidad_inicial} {instance.unidad} "
                         f"de {instance.producto.nombre}" + (f" ({instance.proceso})" if instance.proceso else ""),
                         lugar=f"{PLANTA} – {instance.ubicacion}", lote=instance, cantidad=instance.cantidad_inicial,
                         unidad=instance.unidad, fecha_hora=_momento(instance.fecha_creacion, 14))
