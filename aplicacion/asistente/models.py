from django.conf import settings
from django.db import models


class MensajeAsistente(models.Model):
    """Registro de las preguntas al asistente y de los comandos de voz (sirve como evidencia de uso y usabilidad)."""
    CANALES = [("chat", "Chat escrito"), ("voz_chat", "Chat dictado por voz"), ("voz", "Comando de voz")]
    FUENTES = [("reglas", "Reglas con consultas a la base de datos"), ("ia", "IA externa con contexto"), ("navegador", "Navegador")]
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)
    canal = models.CharField(max_length=10, choices=CANALES, default="chat")
    pregunta = models.CharField(max_length=500)
    respuesta = models.TextField(blank=True)
    intencion = models.CharField(max_length=30, blank=True)
    fuente = models.CharField(max_length=10, choices=FUENTES, default="reglas")
    resuelto = models.BooleanField(null=True, blank=True, help_text="Valoración del usuario: útil o no útil")

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "mensaje del asistente"
        verbose_name_plural = "mensajes del asistente"

    def __str__(self):
        return f"{self.fecha:%d/%m/%Y %H:%M} · {self.pregunta[:40]}"
