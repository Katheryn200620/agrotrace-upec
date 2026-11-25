"""Crea el perfil de cada usuario y registra inicios y cierres de sesión en la auditoría."""
from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from .auditoria import registrar
from .models import Area, Perfil


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def crear_perfil(sender, instance, created, **kw):
    if created:
        Perfil.objects.get_or_create(usuario=instance, defaults={"es_admin_general": instance.is_superuser})


@receiver(user_logged_in)
def al_ingresar(sender, request, user, **kw):
    registrar(request, "ingreso", usuario=user, detalle="Inicio de sesión")


@receiver(user_logged_out)
def al_salir(sender, request, user, **kw):
    if user:
        registrar(request, "salida", usuario=user, detalle="Cierre de sesión")


@receiver(user_login_failed)
def al_fallar(sender, credentials, request=None, **kw):
    registrar(request, "ingreso_fallido", detalle=f"Usuario intentado: {credentials.get('username', '')}"[:200])


def crear_areas(sender, **kw):
    if sender.name != "cuentas":
        return
    for codigo, nombre in Area.CODIGOS:
        Area.objects.get_or_create(codigo=codigo, defaults={"nombre": nombre})


post_migrate.connect(crear_areas)
