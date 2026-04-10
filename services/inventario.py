# services/inventario.py — Inventario es el núcleo del sistema
# Toda modificación de stock DEBE pasar por esta clase.
from extensions import db
from models import Producto, LoteProducto
# MovimientoInventario se importa de forma lazy dentro de cada método (puede no existir en todos los entornos)
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
                cant = int(round(item.cantidad or 0))
                prod.stock = max(0, int(prod.stock or 0) - cant)
                # Registrar movimiento si el modelo existe
                try:
                    from models import MovimientoInventario as _MI
                    mv = _MI(
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
            prod.stock = int(prod.stock or 0) + int(round(cantidad))
            try:
                from models import MovimientoInventario as _MI
                mv = _MI(
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
    def validar_materias_produccion(venta_id):
        """
        Valida si todas las materias primas de una venta están disponibles para producir.
        Retorna dict: { 'ok': bool, 'faltantes': [...], 'proximos_vencer': [...] }
        Faltante = reserva con notas FALTANTE/Sin stock, o stock_disponible < cantidad reservada.
        """
        from models import ReservaProduccion
        from datetime import date, timedelta
        reservas = ReservaProduccion.query.filter(
            ReservaProduccion.venta_id == venta_id,
            ReservaProduccion.estado == 'reservado'
        ).all()

        faltantes = []
        proximos_vencer = []

        for r in reservas:
            notas = r.notas or ''
            es_faltante = ('FALTANTE' in notas or 'Sin stock' in notas)
            mp = r.materia
            if not mp:
                continue

            if es_faltante:
                faltantes.append({
                    'nombre': mp.nombre,
                    'unidad': mp.unidad,
                    'necesario': r.cantidad,
                    'disponible': float(mp.stock_disponible or 0),
                    'falta': round(r.cantidad - float(mp.stock_disponible or 0), 3)
                })
            elif float(mp.stock_disponible or 0) < r.cantidad:
                faltan = round(r.cantidad - float(mp.stock_disponible or 0), 3)
                faltantes.append({
                    'nombre': mp.nombre,
                    'unidad': mp.unidad,
                    'necesario': r.cantidad,
                    'disponible': float(mp.stock_disponible or 0),
                    'falta': faltan
                })
            # Detectar próximos a vencer
            if r.lote_mp and r.lote_mp.fecha_vencimiento:
                dias = (r.lote_mp.fecha_vencimiento - date.today()).days
                if 0 < dias <= 90:
                    proximos_vencer.append({
                        'nombre': mp.nombre,
                        'lote': r.lote_mp.numero_lote or f'ID-{r.lote_mp.id}',
                        'dias': dias,
                        'fecha': r.lote_mp.fecha_vencimiento.strftime('%d/%m/%Y')
                    })

        return {
            'ok': len(faltantes) == 0,
            'faltantes': faltantes,
            'proximos_vencer': proximos_vencer
        }

    @staticmethod
    def descontar_materias_produccion(venta_id):
        """
        Descuenta materias primas del stock al iniciar producción.
        stock_disponible -= cantidad  /  stock_reservado += cantidad
        Solo procesa reservas sin marca FALTANTE.
        Retorna (ok: bool, msg: str)
        """
        from models import ReservaProduccion
        try:
            reservas = ReservaProduccion.query.filter(
                ReservaProduccion.venta_id == venta_id,
                ReservaProduccion.estado == 'reservado'
            ).all()
            for r in reservas:
                notas = r.notas or ''
                if 'FALTANTE' in notas or 'Sin stock' in notas:
                    continue
                mp = r.materia
                if not mp:
                    continue
                mp.stock_disponible = max(0.0, float(mp.stock_disponible or 0) - r.cantidad)
                mp.stock_reservado  = float(mp.stock_reservado or 0) + r.cantidad
                # Movimiento omitido — MovimientoInventario es solo para productos terminados
            return True, 'Stock de materias primas descontado correctamente.'
        except Exception as ex:
            logging.warning(f'InventarioService.descontar_materias_produccion error: {ex}')
            return False, str(ex)

    @staticmethod
    def devolver_materias_venta(venta_id):
        """
        Devuelve al stock disponible las materias reservadas de una venta cancelada/eliminada.
        """
        from models import ReservaProduccion
        try:
            reservas = ReservaProduccion.query.filter(
                ReservaProduccion.venta_id == venta_id,
                ReservaProduccion.estado == 'reservado'
            ).all()
            for r in reservas:
                mp = r.materia
                if not mp:
                    continue
                notas = r.notas or ''
                if 'FALTANTE' in notas or 'Sin stock' in notas:
                    r.estado = 'cancelado'
                    continue
                mp.stock_disponible = float(mp.stock_disponible or 0) + r.cantidad
                mp.stock_reservado  = max(0.0, float(mp.stock_reservado or 0) - r.cantidad)
                r.estado = 'cancelado'
            return True
        except Exception as ex:
            logging.warning(f'InventarioService.devolver_materias_venta error: {ex}')
            return False

    @staticmethod
    def ajustar_stock(producto_id, cantidad_nueva, motivo='Ajuste manual'):
        """Ajusta el stock a un valor específico."""
        try:
            prod = db.session.get(Producto, producto_id)
            if not prod:
                return False
            anterior = int(prod.stock or 0)
            prod.stock = max(0, int(round(cantidad_nueva)))
            diff = cantidad_nueva - anterior
            tipo = 'entrada' if diff > 0 else 'salida'
            try:
                from models import MovimientoInventario as _MI
                mv = _MI(
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
