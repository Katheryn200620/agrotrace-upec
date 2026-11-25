from django.contrib import admin

from .models import Area, Perfil, RegistroAuditoria


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo", "activa")


@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = ("usuario", "es_admin_general", "area", "puede_crear", "puede_editar", "puede_eliminar")


@admin.register(RegistroAuditoria)
class AuditoriaAdmin(admin.ModelAdmin):
    """Solo lectura: la auditoría no se edita ni se borra."""
    list_display = ("fecha", "usuario_nombre", "area", "accion", "modulo", "objeto")
    list_filter = ("accion",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
