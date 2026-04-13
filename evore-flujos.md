# evore-crm — Diagrama de Flujos Completo
> Generado: 2026-04-11
> Propósito: auditoría pre-limpieza para Claude Code

---

## Leyenda

| Símbolo | Significado |
|---------|-------------|
| ✅ | Flujo funcional y completo |
| ⚠️ | Flujo parcial / funciona pero incompleto |
| ❌ | Flujo roto / función llamada que no existe o tiene error crítico |
| 🚫 | Feature solicitada pero no implementada |
| 🐛 | Bug conocido |

---

## 1. AUTENTICACIÓN

```
[Login /login]
  ├─✅ POST válido → redirect dashboard
  ├─✅ POST inválido → flash error
  └─✅ Logout /logout → session.clear → redirect login

[Admin: impersonar usuario]
  ├─✅ POST /admin/impersonar/<id> → login_user(target)
  └─✅ POST /admin/volver → restaurar sesión original
```

---

## 2. DASHBOARD & UTILIDADES

```
[Dashboard /]
  ├─✅ KPIs: ventas mes, gastos, cotizaciones pendientes, tareas vencidas
  ├─✅ Alertas stock bajo, cotizaciones vencidas, reservas pendientes
  └─✅ Actividad reciente

[Reportes /reportes]
  ├─✅ Vista resumen: ventas, gastos, utilidad, impuestos
  ├─✅ Exportar ventas.xlsx
  ├─✅ Exportar gastos.xlsx
  ├─✅ Exportar inventario.xlsx
  ├─✅ Exportar clientes.xlsx
  ├─🚫 P&L / Estado de resultados (no existe ruta ni template)
  └─🚫 Balance general (no existe)

[Buscador /buscador]
  └─✅ Búsqueda cross-módulo (clientes, ventas, cotizaciones, tareas)

[Calendario /calendario]
  ├─✅ Vista mensual con eventos
  ├─✅ POST /eventos/nuevo
  ├─✅ POST /eventos/<id>/editar
  └─✅ POST /eventos/<id>/eliminar

[Notificaciones /notificaciones]
  ├─✅ Lista, marcar leída, marcar todas
  └─✅ API /notificaciones/recientes (polling)

[Tareas /tareas]
  ├─✅ CRUD completo (nueva, ver, editar, eliminar)
  ├─✅ Comentarios /tareas/<id>/comentar
  └─✅ Completar /tareas/<id>/completar

[Notas /notas]
  └─✅ CRUD completo (nueva, editar, eliminar)

[Actividad /actividad]
  └─✅ Log de actividad del usuario

[Mi actividad /mi-actividad]
  └─✅ Estadísticas personales (ventas, tareas, cotizaciones)
```

---

## 3. CLIENTES

```
[Clientes /clientes]
  ├─✅ Lista con filtros (estado, búsqueda)
  ├─✅ Nuevo /clientes/nuevo → guarda contactos adicionales
  ├─✅ Ver /clientes/<id> → historial ventas + cotizaciones + tareas
  ├─✅ Editar /clientes/<id>/editar
  └─✅ Eliminar /clientes/<id>/eliminar

[Portal cliente /portal]   ← acceso público externo
  ├─⚠️ /portal → requiere login_required (¡cliente externo no puede entrar sin cuenta!)
  ├─⚠️ /portal/mensaje/nuevo → login_required (no hay auth pública para clientes)
  ├─⚠️ /portal/pre-cotizacion/nueva → login_required
  ├─⚠️ /portal/ticket/nuevo → login_required
  └─🚫 Login público para clientes (no existe; todos los endpoints exigen sesión interna)
```

**Bug portal:** Todas las rutas del portal cliente tienen `@login_required`, lo que significa que un cliente externo nunca puede acceder. Falta una vista pública con token o login separado para clientes.

---

## 4. COTIZACIONES (clientes)

```
[Cotizaciones /cotizaciones]
  ├─✅ Lista con filtros de estado
  ├─✅ Nueva /cotizaciones/nueva → items (productos + servicios), anticipo, días entrega
  ├─✅ Ver /cotizaciones/<id>
  ├─✅ Editar /cotizaciones/<id>/editar
  ├─✅ PDF /cotizaciones/<id>/pdf
  ├─✅ Eliminar /cotizaciones/<id>/eliminar
  └─✅ Cambiar estado /cotizaciones/<id>/estado

[Máquina de estados Cotización]
  borrador → enviada → aprobada → confirmacion_orden
                                        │
                                        ↓
                          ⚠️ llama _procesar_orden_produccion(cot)
                             (función definida en utils.py ← importada OK)
                             PERO: no crea Venta automáticamente
                                        │
                                        ↓
                          ❌ NO existe botón "Crear Venta desde esta Cotización"
                             El flujo cotización → venta está ROTO en la UI
                             (la cotización queda en confirmacion_orden para siempre)

  🚫 FEATURE FALTANTE: Convertir cotización aprobada en Venta con un click
```

---

## 5. VENTAS

```
[Ventas /ventas]
  ├─✅ Lista con filtros (estado, fecha, búsqueda)
  ├─✅ Nueva /ventas/nueva → items, impuesto automático, crea cotización si no existe
  ├─✅ Editar /ventas/<id>/editar
  ├─✅ Eliminar /ventas/<id>/eliminar (solo admin)
  ├─✅ Remisión PDF /ventas/<id>/remision
  ├─✅ Factura PDF /ventas/<id>/factura (HTML-to-print, no PDF real)
  └─✅ Cambiar estado /ventas/<id>/estado

[Máquina de estados Venta]
  prospecto → negociacion → anticipo_pagado → pagado → entregado
                                │                │
                                ↓                ↓
                          pausa produccion  completa produccion
                                │
                    cancelado / perdido (reversión stock)

  ✅ Estado 'anticipo_pagado' → reactiva órdenes de producción pausadas
  ✅ Estado 'pagado' → ejecuta _descontar_stock_venta() + descuenta stock
  ✅ Estado 'cancelado' → cancela órdenes de producción activas

[Acciones adicionales]
  ├─✅ Informar cliente /ventas/<id>/informar_cliente (flash/email mock)
  ├─✅ Entregar /ventas/<id>/entregar → estado = 'pagado'
  └─✅ API material_status /api/ventas/<id>/material_status

[Factura]
  ├─⚠️ /ventas/<id>/factura → template HTML (para imprimir)
  └─🚫 Generación real de PDF (no usa WeasyPrint ni similar; solo HTML print)
```

---

## 6. SERVICIOS

```
[Servicios /servicios]
  ├─✅ Lista
  ├─✅ Nuevo /servicios/nuevo (con categorías, unidades, markup)
  ├─✅ Editar /servicios/<id>/editar
  ├─✅ Toggle activo/inactivo /servicios/<id>/toggle
  ├─✅ Eliminar /servicios/<id>/eliminar
  └─✅ API JSON /api/servicios/json (usada por formulario cotizaciones)
```

---

## 7. PROVEEDORES & COMPRAS

```
[Proveedores /proveedores]
  ├─✅ Lista (con filtro tipo: proveedor / transportista)
  ├─✅ Nuevo /proveedores/nuevo
  ├─✅ Editar /proveedores/<id>/editar
  └─✅ Eliminar /proveedores/<id>/eliminar

[Portal proveedor /portal-proveedor]
  ├─⚠️ /portal-proveedor → login_required (mismo problema que portal cliente)
  ├─⚠️ Confirmar OC /portal-proveedor/confirmar-oc/<id>
  ├─⚠️ Ticket /portal-proveedor/ticket/nuevo
  └─⚠️ Anticipo OC /portal-proveedor/oc/<id>/anticipo

[Cotizaciones proveedor /cotizaciones-proveedor]
  ├─✅ Lista (tipo: granel / general)
  ├─✅ Nueva /cotizaciones-proveedor/nueva
  ├─✅ Editar /cotizaciones-proveedor/<id>/editar
  ├─✅ JSON /cotizaciones-proveedor/<id>/json (AJAX para OC)
  └─✅ Eliminar /cotizaciones-proveedor/<id>/eliminar

[Órdenes de Compra /ordenes-compra]
  ├─✅ Lista
  ├─✅ Nueva /ordenes-compra/nueva (puede partir de cotización proveedor)
  ├─✅ PDF /ordenes_compra/<id>/pdf
  ├─✅ Editar /ordenes-compra/<id>/editar
  ├─✅ Cambiar estado /ordenes-compra/<id>/estado
  ├─✅ Anticipo recibido /ordenes-compra/<id>/anticipo-recibido
  └─✅ Eliminar /ordenes-compra/<id>/eliminar

[Máquina de estados OC]
  borrador → pendiente → enviada → recibida → completada
                                      │
                                      ↓
                          ⚠️ "recibida" solo crea evento en Calendario
                             NO actualiza stock de MateriaPrima automáticamente
                             (debe hacerse manualmente vía compra_ingresar_mp)
                                      │
                                      ↓
                          🚫 FEATURE FALTANTE: al marcar OC como "completada/recibida"
                             debería ingresar automáticamente la MP al inventario

[Compra MP /produccion/compras]
  ├─✅ Lista
  ├─✅ Nueva /produccion/compras/nueva
  ├─✅ Editar /produccion/compras/<id>/editar
  ├─✅ Eliminar /produccion/compras/<id>/eliminar
  └─✅ Ingresar MP /produccion/compras/<id>/ingresar_mp → actualiza stock MateriaPrima
```

---

## 8. PRODUCCIÓN

```
[Producción /produccion]
  └─✅ Dashboard con KPIs producción

[Materias Primas /produccion/materias]
  ├─✅ Lista con stock actual y alertas
  ├─✅ Nueva /produccion/materias/nueva
  ├─✅ AJAX nueva rápida /produccion/materias/nueva-rapida (desde recetas)
  ├─✅ Editar /produccion/materias/<id>/editar
  └─✅ Eliminar /produccion/materias/<id>/eliminar

[Granel /produccion/granel]
  ├─✅ Lista
  ├─✅ Nueva /produccion/granel/nueva
  ├─✅ Editar /produccion/granel/<id>/editar
  └─✅ Eliminar /produccion/granel/<id>/eliminar

[Recetas /produccion/recetas]
  ├─✅ Lista con costo calculado
  ├─✅ Nueva /produccion/recetas/nueva (ingredientes con cantidades)
  ├─✅ Editar /produccion/recetas/<id>/editar
  └─✅ Eliminar /produccion/recetas/<id>/eliminar

[Reservas /produccion/reservas]
  ├─✅ Lista
  ├─✅ Nueva /produccion/reservas/nueva
  ├─✅ Cancelar /produccion/reservas/<id>/cancelar
  ├─✅ Solicitar compra /produccion/reservas/solicitar_compra (crea OC)
  └─✅ Iniciar producción /produccion/reservas/venta/<venta_id>/iniciar

[Órdenes de Producción /produccion/ordenes]
  ├─✅ Lista
  ├─✅ Completar /produccion/ordenes/completar → descuenta MP, suma PT
  ├─✅ Detener /produccion/ordenes/<id>/detener → estado = pausada
  └─✅ Gantt /produccion/gantt

[Flujo completo Producción]
  Venta(anticipo_pagado)
    → reserva_iniciar_produccion()
    → crea OrdenProduccion (estado: en_produccion)
    → orden_completar() → descuenta MateriaPrima, suma stock Producto
    → Venta.estado = 'pagado' (cuando paga cliente)
    → _descontar_stock_venta() → descuenta stock Producto terminado

  ✅ Flujo completo y funcional
```

---

## 9. INVENTARIO

```
[Inventario /inventario]
  ├─✅ Lista productos con stock, precio, fecha caducidad
  ├─✅ Nuevo /inventario/nuevo
  ├─✅ Editar /inventario/<id>/editar
  └─✅ Eliminar /inventario/<id>/eliminar

[Lotes /inventario/lotes]
  ├─✅ Lista
  ├─✅ Nuevo /inventario/lotes/nuevo
  ├─✅ Editar /inventario/lotes/<id>/editar
  └─✅ Eliminar /inventario/lotes/<id>/eliminar

[Multi-ingreso /inventario/ingresos]
  └─✅ POST → ingresa múltiples unidades con número de lote

[FALTANTES Inventario]
  ├─🚫 Kardex / historial de movimientos por producto (no existe)
  ├─🚫 Ajuste de inventario (no existe ruta /inventario/<id>/ajustar)
  └─🚫 Transferencia entre ubicaciones (no modelado)
```

---

## 10. EMPAQUES SECUNDARIOS

```
[Empaques /empaques]
  ├─✅ Lista empaques guardados con estado (borrador/aprobado)
  ├─✅ Nuevo /empaques/nuevo
  ├─✅ API calcular /empaques/calcular (POST JSON → Top 10 variantes)
  ├─✅ Aprobar /empaques/<id>/aprobar → crea MateriaPrima automáticamente
  └─✅ Eliminar /empaques/<id>/eliminar

[Calculadora / Simulador logístico]
  ├─✅ Top 10 cajas por aprovechamiento de peso
  ├─✅ Simulador canvas 2D (top + lateral) con pallet y camión
  ├─✅ Caja óptima por tipo de vehículo (S/M/L/XL/XXL) y pallet
  ├─✅ Tab "Por cantidad" → sugiere caja + vehículo para N unidades
  ├─✅ Calculadora envío con ciudades LATAM precargadas + Google Maps
  ├─✅ % peso y % espacio/volumen claramente etiquetados
  └─✅ Costos por cantidad de unidades

[FALTANTES Empaques]
  └─🚫 Adjuntar cálculo de empaque a una cotización
```

---

## 11. NÓMINA

```
[Nómina /nomina]
  ├─✅ Lista empleados con salario, cargo, estado
  ├─✅ Dashboard resumen (total nómina, empleados activos)
  └─✅ Cerrar mes /nomina/cerrar-mes → genera asiento contable

[Empleado]
  ├─✅ Nuevo /nomina/nuevo
  ├─✅ Ver /nomina/<id>
  ├─✅ Editar /nomina/<id>/editar
  ├─✅ Liquidación /nomina/<id>/liquidacion → template HTML para imprimir
  ├─✅ Retirar /nomina/<id>/retirar → estado = retirado
  └─✅ Parámetros /nomina/parametros (IMSS, ARL, pensión, etc.)

[BUGS Nómina]
  └─🐛 CRÍTICO: templates/nomina/liquidacion.html contiene líneas 66-4215
       con el código Python completo de una versión monolítica anterior.
       El template HTML termina en la línea 65 ({% endblock %}).
       Las 4150 líneas restantes son código Python muerto que no debería
       estar en un archivo de template Jinja2.
       → Acción: truncar liquidacion.html en la línea 65.

[FALTANTES Nómina]
  ├─🚫 Recibo de pago PDF / comprobante mensual por empleado
  ├─🚫 Exportar nómina a Excel
  └─🚫 Historial de pagos por empleado
```

---

## 12. CONTABILIDAD

```
[Contable /contable]
  ├─✅ Dashboard: ingresos, egresos, utilidad, IVA, ISR
  ├─✅ Ingresos /contable/ingresos (ventas cobradas)
  ├─✅ Egresos /contable/egresos (gastos + nómina)
  ├─✅ Libro diario /contable/libro-diario
  └─✅ Exportar /contable/exportar (Excel)

[Asientos manuales /contable/asientos]
  ├─✅ Lista
  ├─✅ Nuevo /contable/asientos/nuevo
  ├─✅ Editar /contable/asientos/<id>/editar
  ├─✅ Marcar caja chica /contable/asientos/<id>/caja-chica
  ├─✅ Comprobante PDF /contable/asientos/<id>/comprobante
  └─✅ Eliminar /contable/asientos/<id>/eliminar

[Gastos /gastos]
  ├─✅ Lista con filtros y plantillas recurrentes
  ├─✅ Nuevo /gastos/nuevo
  ├─✅ Editar /gastos/<id>/editar
  ├─✅ Eliminar /gastos/<id>/eliminar
  └─✅ Usar plantilla /gastos/plantilla/<id>/usar

[Impuestos/Reglas tributarias /finanzas/impuestos]
  ├─✅ CRUD completo
  └─⚠️ Cálculo base IVA: corregido (÷ 1+tasa) pero solo aplica a ventas/ingresos

[FALTANTES Contabilidad]
  ├─🚫 Estado de Resultados (P&L) formal
  ├─🚫 Balance General
  └─🚫 Conciliación bancaria
```

---

## 13. ADMIN & CONFIGURACIÓN

```
[Usuarios /admin/usuarios]
  ├─✅ Lista
  ├─✅ Nuevo /admin/usuarios/nuevo
  ├─✅ Editar /admin/usuarios/<id>/editar
  ├─✅ Toggle activo/inactivo /admin/usuarios/<id>/toggle
  ├─✅ Impersonar /admin/impersonar/<id>
  └─✅ Reset total /admin/reset-total (borra toda la BD — solo admin)

[Empresa /admin/empresa]
  └─✅ Configuración: nombre, RFC, dirección, logo, moneda

[Documentos Legales /legal]
  ├─✅ Lista
  ├─✅ Nuevo /legal/nuevo
  ├─✅ Editar /legal/<id>/editar
  └─✅ Eliminar /legal/<id>/eliminar
```

---

## 14. AI (módulo auxiliar)

```
[AI /ai]
  ├─✅ Chat /ai/chat (POST, requiere API key configurada)
  ├─✅ Data /ai/data (contexto del ERP para prompts)
  └─✅ Status /ai/status
```

---

## RESUMEN DE PROBLEMAS CRÍTICOS

### 🐛 Bugs que rompen código

| # | Archivo | Línea | Descripción | Acción |
|---|---------|-------|-------------|--------|
| 1 | `templates/nomina/liquidacion.html` | 66–4215 | Código Python de app monolítica embebido en template | Truncar en línea 65 |
| 2 | `routes/ventas.py` | 941 | `_procesar_orden_produccion` se llama pero viene de `utils.py` vía `from utils import *` — funciona pero es frágil | Importar explícitamente |

### ❌ Flujos rotos en UI

| # | Flujo | Problema |
|---|-------|---------|
| 1 | Cotización → Venta | No existe botón en `cotizaciones/ver.html` para crear una Venta desde una cotización aprobada |
| 2 | OC recibida → Stock MP | Al marcar OC como "recibida" solo crea evento calendario; el ingreso al stock es manual y separado |
| 3 | Portal cliente externo | Todos los endpoints tienen `@login_required`; cliente externo no puede acceder |
| 4 | Portal proveedor externo | Mismo problema: todos los endpoints exigen sesión interna |

### 🚫 Features solicitadas / pendientes

| # | Feature | Módulo |
|---|---------|--------|
| 1 | P&L / Estado de Resultados | Reportes / Contabilidad |
| 2 | Balance General | Contabilidad |
| 3 | Kardex de inventario | Inventario |
| 4 | Ajuste de inventario | Inventario |
| 5 | Recibo de pago mensual por empleado (PDF) | Nómina |
| 6 | Exportar nómina a Excel | Nómina |
| 7 | Convertir cotización en venta (1 click) | Cotizaciones → Ventas |
| 8 | OC completada → ingreso automático de MP | Compras → Inventario MP |
| 9 | Login público para clientes (portal) | Portal cliente |
| 10 | Adjuntar cálculo de empaques a cotización | Empaques |
| 11 | Generación real de PDF (WeasyPrint) | Ventas / Cotizaciones |
| 12 | Historial pagos por empleado | Nómina |

---

## MAPA DE RELACIONES ENTRE MÓDULOS

```
Cliente ──────────────────────────────────────────────────────┐
    │ 1:N                                                       │
    ├─── Cotización ──(confirmacion_orden)──❌──── Venta        │
    │         │                                    │            │
    │         └── CotizacionItem                  │            │
    │                                              │            │
    │                            ┌─────────────────┘            │
    │                            ↓                              │
    │                        VentaProducto                      │
    │                            │                              │
    │                            ↓                              │
Producto ←────── OrdenProduccion ←── ReservaProduccion          │
    │                  │                                        │
    │                  ↓                                        │
    │           RecetaProducto                                  │
    │                  │                                        │
    │                  ↓                                        │
MateriaPrima ←── CompraMateria ←── OrdenCompra ←── Proveedor   │
    │                                   │                       │
    │                                   └── CotizacionProveedor │
    │                                                           │
    └────────────────── AsientoContable ─────────────────────── ┘
                              │
                        ReglaTributaria
                              │
                         GastoOperativo
```

---

## ESTRUCTURA DE ARCHIVOS (rutas por módulo)

```
routes/
├── auth.py         login, logout, perfil, onboarding
├── dashboard.py    dashboard, reportes, exportar_*, calendario, notificaciones, actividad
├── clientes.py     clientes CRUD + portal cliente
├── ventas.py       ventas CRUD + cotizaciones CRUD (cliente)
├── servicios.py    servicios CRUD + API JSON
├── compras.py      cotizaciones_proveedor + ordenes_compra
├── produccion.py   produccion, compras_mp, granel, materias, recetas, reservas, ordenes, gantt
├── inventario.py   productos, lotes, multi-ingreso
├── empaques.py     empaques + calculadora API
├── nomina.py       empleados, liquidacion, parametros
├── contable.py     asientos, ingresos, egresos, libro_diario, exportar
├── admin.py        usuarios, empresa, gastos, impuestos, documentos_legales
├── portal.py       portal cliente + portal proveedor
├── notas.py        notas CRUD
├── tareas.py       tareas CRUD + asignados + comentarios
├── api.py          buscador API
└── ai.py           chat IA
```

---

*Fin del documento — para uso exclusivo de Claude Code en limpieza de código*
