import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from cuentas import permissions as perm

from .agentes import AGENTES
from .models import MensajeAsistente
from .motor import Motor, ia_configurada


@login_required
def chat(request):
    historial = MensajeAsistente.objects.filter(usuario=request.user, canal__in=["chat", "voz_chat"])[:10]
    return render(request, "asistente/chat.html", {"titulo": "Asistente virtual", "historial": reversed(list(historial)),
                                                   "ia": ia_configurada()})


@login_required
@require_POST
def mensaje(request):
    try:
        datos = json.loads(request.body or "{}")
    except ValueError:
        datos = {}
    pregunta = str(datos.get("pregunta", "")).strip()[:500]
    if not pregunta:
        return JsonResponse({"error": "Escriba una pregunta."}, status=400)
    r = Motor(request.user).responder(pregunta)
    m = MensajeAsistente.objects.create(usuario=request.user, pregunta=pregunta, respuesta=r.texto, intencion=r.intencion,
                                        fuente=r.fuente, canal="voz_chat" if datos.get("dictado") else "chat")
    return JsonResponse({**r.como_dict(), "id": m.pk})


@login_required
@require_POST
def valorar(request, pk):
    m = get_object_or_404(MensajeAsistente, pk=pk, usuario=request.user)
    m.resuelto = request.POST.get("util") == "1"
    m.save(update_fields=["resuelto"])
    return JsonResponse({"ok": True})


@login_required
@require_POST
def registrar_voz(request):
    """Deja constancia del comando de voz reconocido y de la acción tomada (evidencia de uso)."""
    try:
        datos = json.loads(request.body or "{}")
    except ValueError:
        datos = {}
    texto = str(datos.get("texto", ""))[:500]
    if texto:
        MensajeAsistente.objects.create(usuario=request.user, canal="voz", pregunta=texto, fuente="navegador",
                                        respuesta=str(datos.get("accion", ""))[:500], intencion=str(datos.get("comando", ""))[:30])
    return JsonResponse({"ok": True})


@login_required
def agentes(request):
    lista = [(clave, a[0], a[1], a[2], perm.puede(request.user, "crear", a[4])) for clave, a in AGENTES.items()]
    return render(request, "asistente/agentes.html", {"titulo": "Agentes guiados", "agentes": lista})


@login_required
def agente_trazabilidad(request):
    return render(request, "asistente/agente_trazabilidad.html", {"titulo": "Consultar la trazabilidad de un lote"})


@login_required
def voz(request):
    usos = MensajeAsistente.objects.filter(usuario=request.user, canal="voz")[:8]
    return render(request, "asistente/voz.html", {"titulo": "Control por voz", "usos": usos})


@login_required
def uso(request):
    """Resumen de uso del asistente (evidencia para la validación con usuarios)."""
    perm.exigir(perm.es_admin(request.user), request, "Acceso al registro de uso del asistente")
    from django.db.models import Count
    qs = MensajeAsistente.objects.all()
    return render(request, "asistente/uso.html", {
        "titulo": "Uso del asistente y la voz", "total": qs.count(),
        "por_canal": qs.values("canal").annotate(n=Count("id")).order_by("-n"),
        "por_intencion": qs.exclude(canal="voz").values("intencion").annotate(n=Count("id")).order_by("-n")[:10],
        "utiles": qs.filter(resuelto=True).count(), "no_utiles": qs.filter(resuelto=False).count(),
        "ultimos": qs.select_related("usuario")[:30]})
