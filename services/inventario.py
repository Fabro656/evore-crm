# services/inventario.py — Inventario es el núcleo del sistema
# Toda modificación de stock DEBE pasar por esta clase.
from extensions import db
from models import Producto, LoteProducto, MovimientoInventario
from datetime import datetime
import logging


class InventarioService:

    @staticmethod
    def descontar_stock_venta(venta):
        """
        Descuenta del inventario las cantidades de los ítems de una venta.
        Se llama exactamente una vez al entregar la venta.
        """
        try:
            for item in venta.items:
                if not item.producto_id:
                    continue
                prod = db.session.get(Producto, item.producto_id)
                if not prod:
                    continue
                cant = item.cantidad
                prod.stock = max(0, (prod.stock or 0) - cant)
                # Registrar movimiento si el modelo existe
                try:
                    mv = MovimientoInventario(
                        producto_id=prod.id,
                        tipo='salida',
                        cantidad=cant,
                        referencia=f'Venta #{venta.id}',
                        fecha=datetime.utcnow()
                    )
                    db.session.add(mv)
                except Exception:
                    pass  # MovimientoInventario puede no existir en todos los deploys
        except Exception as ex:
            logging.warning(f'InventarioService.descontar_stock_venta error: {ex}')

    @staticmethod
    def aumentar_stock(producto_id, cantidad, referencia=''):
        """Aumenta el stock de un producto (e.g., al recibir una OC)."""
        try:
            prod = db.session.get(Producto, producto_id)
            if not prod:
                return False
            prod.stock = (prod.stock or 0) + cantidad
            try:
                mv = MovimientoInventario(
                    producto_id=prod.id,
                    tipo='entrada',
                    cantidad=cantidad,
                    referencia=referencia,
                    fecha=datetime.utcnow()
                )
                db.session.add(mv)
            except Exception:
                pass
            return True
        except Exception as ex:
            logging.warning(f'InventarioService.aumentar_stock error: {ex}')
            return False

    @staticmethod
    def validar_stock_venta(venta_items):
        """
        Valida que haya stock suficiente para todos los ítems.
        Retorna lista de problemas (vacía = OK).
        """
        problemas = []
        for item in venta_items:
            if not item.get('producto_id'):
                continue
            prod = db.session.get(Producto, item['producto_id'])
            if not prod:
                continue
            stock_actual = prod.stock or 0
            if stock_actual < item.get('cantidad', 0):
                problemas.append(
                    f'{prod.nombre}: stock {stock_actual}, requerido {item["cantidad"]}'
                )
        return problemas

    @staticmethod
    def ajustar_stock(producto_id, cantidad_nueva, motivo='Ajuste manual'):
        """Ajusta el stock a un valor específico."""
        try:
            prod = db.session.get(Producto, producto_id)
            if not prod:
                return False
            anterior = prod.stock or 0
            prod.stock = max(0, cantidad_nueva)
            diff = cantidad_nueva - anterior
            tipo = 'entrada' if diff > 0 else 'salida'
            try:
                mv = MovimientoInventario(
                    producto_id=prod.id,
                    tipo=tipo,
                    cantidad=abs(diff),
                    referencia=motivo,
                    fecha=datetime.utcnow()
                )
                db.session.add(mv)
            except Exception:
                pass
            return True
        except Exception as ex:
            logging.warning(f'InventarioService.ajustar_stock error: {ex}')
            return False
