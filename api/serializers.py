"""Serializadores de salida. Las altas y cambios se validan con los mismos formularios de la web."""
from rest_framework import serializers

from comercial.models import Cliente, Venta
from cosechas.models import Clasificacion, Cosecha, Recepcion
from cuentas import permissions as perm
from cuentas.models import Area
from lotes.models import Lote
from parcelas.models import Labor, Parcela
from productores.models import Productor
from productos.models import Producto
from trazabilidad.models import EventoTrazabilidad
from transporte.models import Despacho, Transportista

COMUNES = ["responsable_nombre", "creado_en", "actualizado_en", "estado_revision"]


class Base(serializers.ModelSerializer):
    responsable_nombre = serializers.SerializerMethodField()
    privados = []                 # campos que solo ve quien administra el área dueña de esos datos
    area_privada = None

    def get_responsable_nombre(self, o):
        r = getattr(o, "responsable", None)
        return (r.get_full_name() or r.get_username()) if r else None

    def to_representation(self, obj):
        data = super().to_representation(obj)
        req = self.context.get("request")
        if self.privados and req is not None:
            u = req.user
            ve = perm.es_admin(u) or (perm.area_de(u) == self.area_privada and obj.responsable_id == u.id)
            if not ve:
                for c in self.privados:
                    data.pop(c, None)
        return data


class ProductorSerializer(Base):
    privados, area_privada = ["identificacion", "telefono", "correo"], Area.PRODUCTORES

    class Meta:
        model = Productor
        fields = ["id", "codigo", "nombre", "tipo", "identificacion", "provincia", "canton", "parroquia", "telefono",
                  "correo", "estado", "mostrar_nombre_publico"] + COMUNES


class ParcelaSerializer(Base):
    class Meta:
        model = Parcela
        fields = ["id", "codigo", "nombre", "productor", "cultivo", "variedad", "latitud", "longitud", "altitud_msnm",
                  "superficie", "unidad_superficie", "fecha_siembra", "estado_cultivo", "gln"] + COMUNES


class LaborSerializer(Base):
    class Meta:
        model = Labor
        fields = ["id", "parcela", "tipo", "fecha", "insumo", "dosis", "descripcion"] + COMUNES


class ProductoSerializer(Base):
    class Meta:
        model = Producto
        fields = ["id", "codigo", "nombre", "categoria", "variedad", "unidad", "descripcion", "vida_util_dias", "precio",
                  "stock_minimo", "gtin", "estado", "foto"] + COMUNES


class CosechaSerializer(Base):
    recibida = serializers.BooleanField(read_only=True)

    class Meta:
        model = Cosecha
        fields = ["id", "codigo", "parcela", "productor", "producto", "fecha", "cantidad", "unidad", "observaciones",
                  "recibida"] + COMUNES


class RecepcionSerializer(Base):
    porcentaje_rechazo = serializers.DecimalField(max_digits=5, decimal_places=1, read_only=True)

    class Meta:
        model = Recepcion
        fields = ["id", "cosecha", "fecha_hora", "peso_recibido", "temperatura", "minutos_recepcion", "observaciones",
                  "porcentaje_rechazo"] + COMUNES


class ClasificacionSerializer(Base):
    class Meta:
        model = Clasificacion
        fields = ["id", "recepcion", "categoria", "cantidad", "metodo", "confianza_modelo", "causa_rechazo"] + COMUNES


class LoteSerializer(Base):
    producto_nombre = serializers.CharField(source="producto.__str__", read_only=True)
    link_gs1 = serializers.CharField(read_only=True)
    completitud = serializers.IntegerField(read_only=True)

    class Meta:
        model = Lote
        fields = ["id", "codigo", "producto", "producto_nombre", "cosechas", "categoria", "fecha_creacion", "fecha_vencimiento",
                  "cantidad_inicial", "cantidad_disponible", "ubicacion", "proceso", "estado", "publicado", "link_gs1",
                  "completitud"] + COMUNES


class TransportistaSerializer(Base):
    privados, area_privada = ["identificacion", "telefono"], Area.TRANSPORTE

    class Meta:
        model = Transportista
        fields = ["id", "nombre", "identificacion", "telefono", "vehiculo_placa", "tipo_vehiculo", "refrigerado", "activo"] + COMUNES


class DespachoSerializer(Base):
    class Meta:
        model = Despacho
        fields = ["id", "codigo", "venta", "lote", "cantidad", "transportista", "vehiculo", "salida", "origen", "tipo_destino",
                  "destino", "llegada", "estado", "entregado_a_tiempo", "km_recorridos", "observaciones"] + COMUNES


class ClienteSerializer(Base):
    privados, area_privada = ["identificacion", "telefono", "correo", "direccion"], Area.COMERCIAL

    class Meta:
        model = Cliente
        fields = ["id", "codigo", "nombre", "tipo", "identificacion", "ciudad", "direccion", "telefono", "correo", "activo"] + COMUNES


class VentaSerializer(Base):
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    por_despachar = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Venta
        fields = ["id", "codigo", "cliente", "lote", "fecha", "cantidad", "precio_unitario", "total", "canal", "referencia",
                  "estado", "por_despachar", "observaciones"] + COMUNES


class EventoSerializer(serializers.ModelSerializer):
    tipo_nombre = serializers.CharField(source="get_tipo_display", read_only=True)
    lote_codigo = serializers.CharField(source="lote.codigo", read_only=True, default=None)
    cosecha_codigo = serializers.CharField(source="cosecha.codigo", read_only=True, default=None)
    biz_step = serializers.CharField(read_only=True)

    class Meta:
        model = EventoTrazabilidad
        fields = ["id", "tipo", "tipo_nombre", "tipo_epcis", "biz_step", "lote", "lote_codigo", "cosecha", "cosecha_codigo",
                  "parcela", "fecha_hora", "lugar", "cantidad", "unidad", "descripcion", "disposicion", "origen", "corrige"]
