# Diagrama de Interacciones entre Modulos — Evore CRM v41

## Mapa completo de conexiones

```
╔══════════════════════════════════════════════════════════════════════════════════╗
║                           EVORE CRM — MAPA DE INTERACCIONES                     ║
╠══════════════════════════════════════════════════════════════════════════════════╣
║                                                                                  ║
║  ┌─────────────┐      ┌──────────────┐      ┌─────────────┐                     ║
║  │  CLIENTES   │─────▶│ COTIZACIONES │─────▶│   VENTAS    │                     ║
║  │             │      │              │      │             │                     ║
║  │ • nombre    │      │ • items      │      │ • pipeline  │                     ║
║  │ • empresa   │      │ • precio     │      │ • anticipo  │                     ║
║  │ • contactos │      │ • IVA        │      │ • total     │                     ║
║  │ • NIT       │      │ • PDF        │      │ • estado    │                     ║
║  └──────┬──────┘      └──────────────┘      └──────┬──────┘                     ║
║         │                                           │                            ║
║         │ cliente_id                                │ Al crear/anticipo:         ║
║         ▼                                           ▼                            ║
║  ┌─────────────┐                             ┌─────────────┐                     ║
║  │   PORTAL    │◀────────────────────────────│  CONTABLE   │                     ║
║  │  CLIENTE    │  firma docs, reporta pago   │             │                     ║
║  │             │                              │ • asiento   │                     ║
║  │ • compras   │                              │   ingreso   │                     ║
║  │ • pagos     │  confirmar ingreso ────────▶│ • estado    │                     ║
║  │ • docs      │                              │   pago      │                     ║
║  │ • tracking  │                              │ • PUC       │                     ║
║  │ • mensajes  │                              └──────┬──────┘                     ║
║  └─────────────┘                                     │                            ║
║                                                      │ Al confirmar              ║
║                                                      │ anticipo venta:           ║
║                                                      ▼                            ║
║                                               ┌─────────────┐                     ║
║                                               │ INVENTARIO  │◀─── Stock PT       ║
║                                               │             │                     ║
║                                               │ • reservar  │                     ║
║                                               │   stock     │                     ║
║                                               │ • FIFO      │                     ║
║                                               │ • lotes     │                     ║
║                                               └──────┬──────┘                     ║
║                                                      │                            ║
║                                                      │ Si falta MP:              ║
║                                                      ▼                            ║
║  ┌─────────────┐      ┌──────────────┐      ┌─────────────┐                     ║
║  │PROVEEDORES  │─────▶│ COT.PROVEEDOR│─────▶│   ORDENES   │                     ║
║  │             │      │              │      │  DE COMPRA  │                     ║
║  │ • empresa   │      │ • precio     │      │             │                     ║
║  │ • score     │      │ • plazo      │      │ • items     │                     ║
║  │ • categoria │      │ • vigencia   │      │ • total     │                     ║
║  │ • NIT       │      │ • comparativ │      │ • estado    │                     ║
║  └──────┬──────┘      └──────────────┘      └──────┬──────┘                     ║
║         │                                           │                            ║
║         │ proveedor_id                              │ Al crear OC:              ║
║         ▼                                           ▼                            ║
║  ┌─────────────┐                             ┌─────────────┐                     ║
║  │   PORTAL    │◀────────────────────────────│  CONTABLE   │                     ║
║  │ PROVEEDOR   │  firma docs, confirma pago  │             │                     ║
║  │             │                              │ • asiento   │                     ║
║  │ • OC        │                              │   egreso    │                     ║
║  │ • confirmar │  anticipo enviado ─────────▶│ • confirmar │                     ║
║  │ • anticipo  │◀── anticipo recibido ───────│   pago      │                     ║
║  │ • docs      │                              └──────┬──────┘                     ║
║  │ • mensajes  │                                     │                            ║
║  └─────────────┘                                     │ Al pagar OC:             ║
║                                                      ▼                            ║
║                                               ┌─────────────┐                     ║
║                                               │ PRODUCCION  │                     ║
║                                               │             │                     ║
║                                               │ • recetas   │◀─── BOM            ║
║                                               │ • ordenes   │◀─── x venta        ║
║                                               │ • gantt     │◀─── x venta        ║
║                                               │ • recepcion │◀─── x OC           ║
║                                               │ • calidad   │───▶ TICKETS        ║
║                                               └──────┬──────┘                     ║
║                                                      │                            ║
║                                                      │ Recepcion MP:             ║
║                                                      ▼                            ║
║                                               ┌─────────────┐                     ║
║                                               │ INVENTARIO  │◀─── Stock MP       ║
║                                               │             │                     ║
║                                               │ • stock +   │                     ║
║                                               │ • lote      │                     ║
║                                               │ • movimiento│                     ║
║                                               └─────────────┘                     ║
║                                                                                  ║
╠══════════════════════════════════════════════════════════════════════════════════╣
║                        MODULOS TRANSVERSALES                                     ║
╠══════════════════════════════════════════════════════════════════════════════════╣
║                                                                                  ║
║  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐         ║
║  │    LEGAL    │   │   NOMINA    │   │  TICKETS    │   │APROBACIONES │         ║
║  │             │   │             │   │             │   │             │         ║
║  │ 9 plantillas│   │ • cierre    │   │ • prioridad │   │ • OC        │         ║
║  │ firma+selfie│   │ • horas ext │   │ • asignacion│   │ • ventas    │         ║
║  │ auto-genera │   │ • retencion │   │ • auto-gen  │   │ • cotizac   │         ║
║  │ portal firma│   │ • liquidac  │   │ • categorias│   │ • asientos  │         ║
║  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘         ║
║         │                  │                  │                  │                ║
║         ▼                  ▼                  ▼                  ▼                ║
║  ╔═══════════════════════════════════════════════════════════════════╗            ║
║  ║                    CONTABILIDAD (PUC)                            ║            ║
║  ║                                                                   ║            ║
║  ║  Asientos generados ◀── OC, Ventas, Nomina, Liquidaciones       ║            ║
║  ║  Asientos manuales  ◀── Caja chica, Gastos, Inversiones         ║            ║
║  ║  Reconciliacion     ◀── CSV banco → auto-match                  ║            ║
║  ║  Reportes: Balance, P&G, IVA, Retenciones, Libro auxiliar      ║            ║
║  ║  Export CSV: ventas, clientes, produccion, asientos, empleados  ║            ║
║  ╚═══════════════════════════════════════════════════════════════════╝            ║
║                                                                                  ║
╠══════════════════════════════════════════════════════════════════════════════════╣
║                        SOPORTE / ADMIN                                           ║
╠══════════════════════════════════════════════════════════════════════════════════╣
║                                                                                  ║
║  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          ║
║  │ Usuarios │  │Calendario│  │  Notas   │  │   Wiki   │  │    IA    │          ║
║  │ 10 roles │  │ eventos  │  │ por OC/V │  │ 21 mods  │  │ OpenAI/  │          ║
║  │ modulos  │  │ citas    │  │ alertas  │  │ flujos   │  │ Anthropic│          ║
║  │ permisos │  │ recordat │  │ seguimie │  │ roles    │  │ Ollama   │          ║
║  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘          ║
║                                                                                  ║
╚══════════════════════════════════════════════════════════════════════════════════╝
```

## Matriz de interacciones directas

| Modulo origen | Modulo destino | Tipo de interaccion | Automatico |
|---------------|---------------|---------------------|------------|
| **Cotizacion** | Venta | Conversion directa | Manual |
| **Venta** | AsientoContable | Auto-genera asiento ingreso | Si |
| **Venta** | DocumentoLegal | Auto-genera contrato cliente | Si |
| **Venta** | OrdenCompra | Auto-genera OC para MP faltante | Si |
| **Venta** | Inventario | Reserva stock PT (FIFO) | Si |
| **Venta** | OrdenProduccion | Crea orden al confirmar anticipo | Manual |
| **Venta** | Portal Cliente | Notifica contrato + tracking | Si |
| **OC** | AsientoContable | Auto-genera asiento egreso | Si |
| **OC** | DocumentoLegal | Auto-genera contrato proveedor | Si |
| **OC** | CompraMateria | Crea registros en produccion | Si |
| **OC** | Portal Proveedor | Notifica OC + anticipo | Si |
| **OC** | Tarea | Auto-tarea transportista | Si |
| **AsientoContable** | OC | Confirmar pago → cambia estado OC | Manual |
| **AsientoContable** | Venta | Confirmar ingreso → cambia estado venta | Manual |
| **AsientoContable** | Inventario | Confirmar ingreso → reservar stock | Si |
| **AsientoContable** | Nomina | Cierre genera asiento nomina | Si |
| **Portal Cliente** | PagoVenta | Reportar pago enviado | Manual |
| **Portal Cliente** | AsientoContable | Badge "cliente reporto pago" | Si |
| **Portal Cliente** | DocumentoLegal | Firma digital + selfie | Manual |
| **Portal Proveedor** | OC | Confirmar OC | Manual |
| **Portal Proveedor** | AsientoContable | Confirmar anticipo recibido | Manual |
| **Portal Proveedor** | DocumentoLegal | Firma digital + selfie | Manual |
| **Produccion** | Inventario | Recepcion MP → stock + lote | Si |
| **Produccion** | Inventario | Completar orden → stock PT | Si |
| **Produccion** | Proveedor | Problema calidad → score baja | Si |
| **Produccion** | Tarea | Problema calidad → 2 tickets auto | Si |
| **Nomina** | GastoOperativo | Cierre mensual → gasto | Si |
| **Nomina** | AsientoContable | Cierre → asiento nomina | Si |
| **Nomina** | HoraExtra | Suma horas extra al cierre | Si |
| **Nomina** | GastoOperativo | Liquidacion → gasto inmediato | Si |
| **Nomina** | AsientoContable | Liquidacion → asiento | Si |
| **Legal** | Portal Cliente | Doc requiere firma → aparece en portal | Si |
| **Legal** | Portal Proveedor | Doc requiere firma → aparece en portal | Si |
| **Legal** | Notificacion | Al crear doc → notifica contraparte | Si |
| **Aprobacion** | OC | Bloquea hasta aprobar | Si |
| **Aprobacion** | Venta | Bloquea hasta aprobar | Si |
| **Aprobacion** | Cotizacion | Bloquea hasta aprobar | Si |
| **Reconciliacion** | AsientoContable | Auto-match por monto/fecha | Semi |
| **Calendario** | Evento | CRUD eventos | Manual |
| **IA** | Todo | Consulta datos, crea entidades | Manual |

## Flujo de datos por entidad

### Venta (12 conexiones)
```
Venta ──▶ AsientoContable (ingreso)
      ──▶ DocumentoLegal (contrato cliente)
      ──▶ OrdenCompra (auto, MP faltante)
      ──▶ Inventario (reservar stock PT)
      ──▶ OrdenProduccion (crear)
      ──▶ Portal Cliente (notificar)
      ──▶ Aprobacion (solicitar)
      ──▶ PagoVenta (registros de pago)
      ──▶ Transportista (envio)
      ──▶ Factura PDF
      ──▶ Remision PDF
      ──▶ Tarea (tickets)
```

### Orden de Compra (10 conexiones)
```
OC ──▶ AsientoContable (egreso)
   ──▶ DocumentoLegal (contrato proveedor)
   ──▶ CompraMateria (registros produccion)
   ──▶ Portal Proveedor (notificar)
   ──▶ Aprobacion (solicitar)
   ──▶ Tarea (transportista)
   ──▶ Proveedor (score)
   ──▶ Inventario (recepcion → stock MP)
   ──▶ LoteMateriaPrima (trazabilidad)
   ──▶ MovimientoInventario (auditoria)
```

### AsientoContable (8 conexiones)
```
Asiento ──▶ OC (confirmar pago → cambiar estado)
        ──▶ Venta (confirmar ingreso → cambiar estado)
        ──▶ LineaAsiento (partida doble PUC)
        ──▶ CuentaPUC (clasificacion)
        ──▶ MovimientoBancario (reconciliacion)
        ──▶ Balance/P&G (reportes)
        ──▶ IVA/Retenciones (reportes tributarios)
        ──▶ Libro Auxiliar (por tercero)
```

### Empleado/Nomina (7 conexiones)
```
Empleado ──▶ NominaService (calculo)
         ──▶ HoraExtra (recargos)
         ──▶ GastoOperativo (cierre/liquidacion)
         ──▶ AsientoContable (nomina/liquidacion)
         ──▶ Tarea (auto si nomina pendiente)
         ──▶ DocumentoLegal (contrato laboral)
         ──▶ Recibo PDF (pago)
```

### DocumentoLegal (6 conexiones)
```
DocLegal ──▶ Portal Cliente (firma pendiente)
         ──▶ Portal Proveedor (firma pendiente)
         ──▶ Notificacion (alertar contraparte)
         ──▶ Firma empresa (canvas + selfie)
         ──▶ Firma portal (canvas + selfie)
         ──▶ Registro admin (badges estado)
```

## Triggers automaticos (cadena completa)

### Cadena: Venta ganada
```
1. Contable confirma ingreso en asiento
   └─▶ 2. Venta → anticipo_pagado
       ├─▶ 3. Inventario reserva stock PT (FIFO)
       ├─▶ 4. DocumentoLegal auto-creado para cliente
       │   └─▶ 5. Notificacion al portal cliente
       └─▶ 6. Para cada MP faltante:
           └─▶ 7. OC auto-creada
               ├─▶ 8. AsientoContable egreso auto
               ├─▶ 9. DocumentoLegal auto para proveedor
               │   └─▶ 10. Notificacion al portal proveedor
               └─▶ 11. CompraMateria en produccion
```

### Cadena: OC pagada y recibida
```
1. Contable confirma pago en asiento
   └─▶ 2. OC → anticipo_pagado + estado_proveedor=anticipo_enviado
       └─▶ 3. Proveedor ve "anticipo enviado" en portal
           └─▶ 4. Proveedor confirma recibido
               └─▶ 5. Nota en asiento + notificacion equipo
                   └─▶ 6. Proveedor envia material
                       └─▶ 7. Produccion registra recepcion
                           ├─▶ 8. Stock MP actualizado
                           ├─▶ 9. Lote creado con trazabilidad
                           └─▶ 10. MovimientoInventario auditado
```

### Cadena: Problema de calidad
```
1. Produccion reporta problema de calidad
   ├─▶ 2. OC.tiene_problema_calidad = True
   ├─▶ 3. CompraMateria.estado_recepcion = parcial
   ├─▶ 4. Ticket auto → creador OC: "contactar proveedor"
   ├─▶ 5. Ticket auto → vendedor venta: "retraso por calidad"
   └─▶ 6. Score proveedor recalculado (baja)
```

### Cadena: Retiro/despido empleado
```
1. Admin ejecuta retiro
   ├─▶ 2. Liquidacion calculada (cesantias, prima, vacaciones, indemnizacion)
   ├─▶ 3. GastoOperativo creado inmediato
   ├─▶ 4. AsientoContable creado inmediato
   └─▶ 5. Empleado.estado = retirado/despedido
```

### Cadena: Firma documento legal
```
1. Sistema auto-genera contrato (al crear OC o venta)
   └─▶ 2. Admin firma en generador (canvas + selfie)
       └─▶ 3. Doc aparece en portal como "pendiente firma"
           └─▶ 4. Contraparte firma en portal (canvas + selfie camara)
               └─▶ 5. Doc.estado = vigente (ambas partes firmaron)
                   └─▶ 6. Notificacion al admin + badge "firmado"
                       └─▶ 7. Doc descargable con ambas firmas + fotos
```

## Modulos sin conexiones directas (independientes)

| Modulo | Depende de | Quien depende de el |
|--------|-----------|---------------------|
| Calendario | Solo User | Nadie (standalone) |
| Wiki | Solo templates | Nadie (referencia) |
| Servicios | Solo Venta/Cotizacion items | Ventas lo consume |
| EmpaqueSecundario | Solo Producto | Logistica lo usa |

## Estadisticas de conectividad

| Metrica | Valor |
|---------|-------|
| Total interacciones directas | 42 |
| Triggers automaticos | 28 |
| Cadena mas larga (venta ganada) | 11 pasos |
| Modulo mas conectado | Venta (12 conexiones) |
| Modulo mas dependido | AsientoContable (8 conexiones entrantes) |
| Modulos independientes | 4 (calendario, wiki, servicios, empaques) |
