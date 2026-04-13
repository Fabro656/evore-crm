# Analisis Evore CRM v41 — 13 Abril 2026

## Metricas del proyecto

| Metrica | Valor |
|---------|-------|
| Lineas Python | 14,628 |
| Lineas HTML | 22,195 |
| Total LOC | 36,823 |
| Rutas | 245 |
| Modelos | 50 |
| Tablas DB | 50 |
| Templates | 119 |
| Modulos de rutas | 20 |

## Estado actual: PRODUCCION

Todo el codigo compila, esta publicado en Railway, y no tiene bugs criticos conocidos.

## Bugs corregidos en esta sesion

| Bug | Severidad | Fix |
|-----|-----------|-----|
| Race condition doble pago (confirmar_pago) | CRITICO | SELECT FOR UPDATE + re-verificar |
| monto_pagado excede total | CRITICO | min() cap server-side |
| Portal pago sin validar monto/rol | CRITICO | Check cliente_id + monto <= saldo |
| Retencion nomina base inconsistente | CRITICO | base_gravable usa salario_completo consistente |
| Recepcion parcial deja OC stuck | ALTO | Re-evalua estado cada CompraMateria |
| Nomina doble ejecucion | ALTO | Placeholder GastoOperativo como lock |
| Items OC sin validacion | ALTO | qty>0, precio>=0, proveedor existe, min 1 item |
| Modelos faltantes en __all__ | CRITICO | +5 modelos (HoraExtra, MovimientoBancario, etc.) |
| Onboarding fuera de pantalla | MEDIO | clampToViewport + centro en movil |
| Portal sin nav movil | MEDIO | Barra de navegacion mobile |

## Features agregados en esta sesion

### Criticos (flujo de dinero)
- Pagos bidireccionales OC ↔ Proveedor (anticipo enviado → confirmacion)
- Pagos bidireccionales Venta ↔ Cliente (reportar pago → confirmar recepcion)
- Reconciliacion bancaria (upload CSV, auto-match, match manual)

### Legales
- 9 templates legales fortalecidos (hasta 22 clausulas c/u)
- Firma digital con captura de selfie (camara frontal, JPEG comprimido)
- Auto-generacion de contratos al crear OC o confirmar venta
- Descarga de documento firmado completo (ambas firmas + selfies)
- Aviso "firmar desde movil"

### Contables
- Libro auxiliar por tercero con saldo acumulado
- Parametros de nomina editables desde UI
- Horas extra (4 tipos, Art. 168-170 CST, integrado al cierre)
- Export CSV: ventas, clientes, produccion, asientos, empleados

### Operativos
- Tracking de envios (guia transporte, estado en portal)
- Comparativo de cotizaciones proveedor (side-by-side)
- Gantt filtra OC por venta (antes era global)
- Onboarding con iconos ilustrativos

### Movil
- Portal cliente/proveedor con barra de navegacion mobile
- Onboarding centrado en pantalla (no anclado a dock inexistente)
- Dock panels full-width en mobile
- Tooltip responsive

---

## Plan para proxima sesion

### PRIORIDAD ALTA (obligaciones legales/tributarias colombianas)

1. **Notas credito/debito**
   - Mecanismo formal de anulacion parcial de facturas
   - Exigido por DIAN para correccion de facturas electronicas
   - Modelo: NotaContable (tipo: credito/debito, venta_id, monto, motivo)
   - Auto-genera asiento contable inverso
   - Archivos: models.py, routes/contable.py, templates/contable/nota_contable.html

2. **Certificados de retencion**
   - Art. 381 ET obliga a emitir certificados anuales a proveedores
   - Endpoint: /contable/certificado-retencion/<proveedor_id>/<año>
   - PDF con: NIT, retenciones aplicadas, base, periodo
   - Archivos: routes/contable.py, templates/contable/certificado_retencion.html

3. **Incapacidades medicas**
   - Registro de incapacidades (fecha inicio/fin, tipo, EPS/ARL)
   - Descuento proporcional de dias en nomina
   - Reconocimiento por EPS (primeros 2 dias empleador, resto EPS)
   - Modelo: Incapacidad (empleado_id, fecha_inicio, fecha_fin, tipo, entidad)
   - Archivos: models.py, routes/nomina.py, services/nomina.py

4. **Archivo plano PILA**
   - Resolucion 2388/2016: reporte mensual de aportes a seguridad social
   - Genera archivo .txt con formato fijo (tipo 1: encabezado, tipo 2: detalle)
   - Incluye: IBC, aportes salud/pension/ARL/caja/SENA/ICBF
   - Archivos: routes/nomina.py, templates/nomina/pila.html

### PRIORIDAD MEDIA (valor de negocio)

5. **Pipeline kanban visual**
   - Vista drag-and-drop del pipeline de ventas
   - Columnas: prospecto, negociacion, anticipo, pagado, entregado
   - Cards con: cliente, titulo, monto, dias en etapa
   - JavaScript vanilla (no framework), sortable
   - Archivos: routes/ventas.py, templates/ventas/kanban.html

6. **Integracion email nativa**
   - Enviar cotizaciones y facturas por email desde boton en la UI
   - Template HTML para email (responsive)
   - Usar Flask-Mail (ya instalado)
   - Archivos: utils.py, routes/ventas.py, templates/email/

7. **Comisiones vendedor**
   - Porcentaje configurable por vendedor o por tipo de producto
   - Calculo automatico al cerrar venta (estado=completado)
   - Reporte mensual de comisiones con export CSV
   - Modelo: Comision (vendedor_id, venta_id, monto, porcentaje, estado)
   - Archivos: models.py, routes/ventas.py

8. **Multi-bodega**
   - Campo bodega_id en Producto y MateriaPrima
   - Selector de bodega en formularios de stock
   - Transferencias entre bodegas con MovimientoInventario
   - Modelo: Bodega (id, nombre, direccion, responsable_id)
   - Archivos: models.py, routes/inventario.py

### PRIORIDAD BAJA (nice-to-have)

9. **API REST publica** — Para integraciones externas
10. **Medios magneticos DIAN** — Reporte anual Art. 631 ET
11. **Contrato por obra/labor** — Plantilla legal adicional
12. **Dashboard configurable** — KPIs seleccionables por rol
13. **Historial de precios por proveedor** — Tracking de cambios
14. **Vacaciones en dinero** — Art. 189 CST compensacion

---

## Archivos criticos (no tocar sin entender)

| Archivo | Lineas | Complejidad | Cuidado |
|---------|--------|-------------|---------|
| models.py | 2,254 | Alta | __all__ debe incluir TODOS los modelos |
| utils.py | 1,493 | Alta | Constantes de nomina, decoradores, filtros |
| routes/ventas.py | ~1,200 | Alta | State machine, auto-asiento, auto-doc, auto-OC |
| routes/contable.py | ~1,300 | Alta | Race condition fix, partida doble, reconciliacion |
| routes/produccion.py | ~1,200 | Alta | FIFO, lotes, recepcion, calidad |
| routes/nomina.py | ~560 | Media | Prorrateo, horas extra, liquidacion |
| templates/base.html | ~1,600 | Muy alta | Dock, flyouts, onboarding, workspace, dark mode |
| services/nomina.py | ~250 | Media | Calculo retencion fuente Art. 383 ET |

## Notas tecnicas

- PostgreSQL en Railway, SQLite local. Las migraciones usan IF NOT EXISTS (PostgreSQL) + fallback sin IF NOT EXISTS (SQLite). Ambas variantes en _migrate().
- SECRET_KEY debe configurarse en Railway (actualmente usa fallback inseguro).
- Flask-Mail es opcional. Si no esta configurado, los emails fallan silenciosamente.
- La AI (routes/ai.py) intenta OpenAI → Anthropic → Ollama en cascada.
- El onboarding usa posicionamiento fijo con clampToViewport para mantenerse en pantalla.
- Los portales tienen nav movil con scroll horizontal.
