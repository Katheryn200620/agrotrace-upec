"""Utilidades de identificación GS1 (GTIN, GLN, GS1 Digital Link)."""
from django.conf import settings


def digito_control(numero: str) -> str:
    """Dígito de control GS1 (módulo 10)."""
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(numero)))
    return str((10 - total % 10) % 10)


def generar_gtin(n: int) -> str:
    base = ("0" + settings.GS1_PREFIJO_EMPRESA + str(n).zfill(5))[:13]
    return base + digito_control(base)


def generar_gln(n: int) -> str:
    base = (settings.GS1_PREFIJO_EMPRESA + "9" + str(n).zfill(4)).ljust(12, "0")[:12]
    return base + digito_control(base)


def digital_link(gtin: str, lote: str) -> str:
    return f"{settings.SITE_URL.rstrip('/')}/01/{gtin}/10/{lote}"
