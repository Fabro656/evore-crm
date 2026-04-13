# Diagrama de Flujo Completo — Evore CRM v40

## 1. Flujo General del Sistema

```mermaid
flowchart TB
    subgraph PORTAL_CLI["PORTAL CLIENTE"]
        PC_inicio[Dashboard cliente]
        PC_precot[Nueva solicitud]
        PC_pago[Reportar pago enviado]
        PC_docs[Documentos legales]
        PC_firma[Firma digital + selfie]
        PC_msg[Mensajes]
    end

    subgraph PORTAL_PROV["PORTAL PROVEEDOR"]
        PP_inicio[Dashboard proveedor]
        PP_confirmar[Confirmar OC]
        PP_anticipo[Confirmar anticipo recibido]
        PP_docs[Documentos legales]
        PP_firma[Firma digital + selfie]
        PP_msg[Mensajes]
    end

    subgraph COMERCIAL["COMERCIAL"]
        CLI[Clientes]
        COT[Cotizaciones]
        VNT[Ventas]
        SRV[Servicios]
        PROD_CAT[Productos]
    end

    subgraph COMPRAS["COMPRAS"]
        PROV[Proveedores]
        COT_PROV[Cotizaciones proveedor]
        OC[Ordenes de compra]
        REG_COMPRAS[Registro compras MP]
    end

    subgraph PRODUCCION["PRODUCCION"]
        REC[Recetas / BOM]
        OP[Ordenes produccion]
        GANTT[Gantt por venta]
        RECEPCION[Recepcion material]
        CALIDAD[Control calidad]
    end

    subgraph INVENTARIO["INVENTARIO"]
        INV_PT[Stock productos terminados]
        INV_MP[Stock materias primas]
        LOTES[Lotes con vencimiento]
        MOV[Movimientos inventario]
    end

    subgraph FINANZAS["FINANZAS / CONTABLE"]
        PUC[Plan Unico de Cuentas]
        ASI[Asientos contables]
        ASI_GEN[Generados - OC/Ventas]
        ASI_MAN[Manuales - Caja chica]
        CONC[Reconciliacion bancaria]
        IVA[IVA generado vs descontable]
        RET[Retenciones]
        BAL[Balance general]
        RES[Estado de resultados]
        CIERRE[Cierre de periodo]
    end

    subgraph NOMINA["NOMINA"]
        EMP[Empleados]
        NOM_MES[Cierre mensual]
        PARAMS[Parametros editables]
        LIQ[Liquidaciones]
        RECIBO[Recibos de pago]
    end

    subgraph LEGAL["LEGAL"]
        DOC_LEG[9 plantillas colombianas]
        GEN_DOC[Generador de documentos]
        FIRMA_EMP[Firma empresa]
        FIRMA_PORT[Firma portal + selfie]
        REG_DOC[Registro documentos]
    end

    subgraph ADMIN["ADMINISTRACION"]
        USR[Usuarios y roles]
        CFG[Config empresa]
        APROB[Aprobaciones]
        TICK[Tickets]
        NOTAS[Notas]
        CAL[Calendario]
        WIKI[Wiki del sistema]
    end

    %% ═══ FLUJOS PRINCIPALES ═══

    CLI -->|crea| COT
    COT -->|aprueba| VNT
    VNT -->|auto-genera| ASI_GEN
    VNT -->|auto-genera| DOC_LEG
    VNT -->|anticipo confirmado| OP
    VNT -->|MP faltante| OC

    PROV --> COT_PROV
    COT_PROV --> OC
    OC -->|auto-genera| ASI_GEN
    OC -->|auto-genera| DOC_LEG
    OC --> REG_COMPRAS

    OP --> REC
    OP --> GANTT
    REC --> INV_MP
    RECEPCION --> INV_MP
    RECEPCION --> LOTES
    OP -->|completada| INV_PT

    ASI_GEN -->|confirmar pago| OC
    ASI_GEN -->|confirmar ingreso| VNT
    ASI --> PUC
    ASI --> BAL
    ASI --> RES
    CONC --> ASI

    DOC_LEG --> PC_docs
    DOC_LEG --> PP_docs
    PC_firma --> DOC_LEG
    PP_firma --> DOC_LEG

    PC_pago -->|notifica| ASI_GEN
    PP_anticipo -->|actualiza| ASI_GEN

    EMP --> NOM_MES
    PARAMS --> NOM_MES
    NOM_MES --> ASI
    LIQ --> ASI

    CALIDAD -->|problema| TICK
    CALIDAD -->|retraso| TICK
```

## 2. Ciclo de Vida de una Venta

```mermaid
stateDiagram-v2
    [*] --> prospecto: Cliente registrado
    prospecto --> negociacion: Cotizacion enviada
    negociacion --> anticipo_pagado: Contable confirma ingreso
    anticipo_pagado --> pagado: Pago total confirmado
    pagado --> entregado: Envio con transportista
    entregado --> completado: Acta de entrega firmada

    negociacion --> cancelado: Cliente cancela
    negociacion --> perdido: Sin respuesta

    note right of negociacion
        Al pasar a anticipo_pagado:
        - Se reserva stock PT
        - Se generan OC automaticas para MP faltante
        - Se crea contrato cliente en portal
        - Se crea asiento contable ingreso
    end note

    note right of anticipo_pagado
        Produccion activa:
        - Ordenes de produccion creadas
        - Gantt vinculado a venta
        - Recepcion MP desde OC
    end note
```

## 3. Ciclo de Vida de una Orden de Compra

```mermaid
stateDiagram-v2
    [*] --> borrador: OC creada
    borrador --> anticipo_pagado: Contable confirma pago parcial
    borrador --> en_espera_producto: Contable confirma pago total
    anticipo_pagado --> en_espera_producto: Pago completado
    en_espera_producto --> recibida_parcial: Recepcion parcial MP
    en_espera_producto --> recibida: Recepcion total MP
    recibida_parcial --> recibida: Resto recibido

    borrador --> cancelada: Cancelar

    note right of borrador
        Al crear OC:
        - Auto-genera asiento contable egreso
        - Auto-genera contrato proveedor en portal
        - Proveedor ve OC en su portal
    end note

    note right of anticipo_pagado
        Proveedor ve "Anticipo enviado"
        en su portal y confirma recepcion
    end note
```

## 4. Flujo Bidireccional de Pagos

```mermaid
sequenceDiagram
    participant Admin as Contable/Admin
    participant ASI as Asiento Contable
    participant PROV as Portal Proveedor
    participant CLI as Portal Cliente

    Note over Admin,CLI: === FLUJO OC → PROVEEDOR ===
    Admin->>ASI: Confirmar pago OC
    ASI->>ASI: estado_pago = parcial/completo
    ASI-->>PROV: OC muestra "Anticipo enviado"
    PROV->>PROV: Click "Confirmar recibido"
    PROV-->>ASI: Nota: "Proveedor confirmo recepcion"
    PROV-->>Admin: Notificacion al equipo

    Note over Admin,CLI: === FLUJO VENTA ← CLIENTE ===
    CLI->>CLI: Click "Pagar" (monto, metodo, ref)
    CLI-->>ASI: Badge "Cliente reporto pago"
    CLI-->>Admin: Notificacion al equipo
    Admin->>ASI: Confirmar ingreso recibido
    ASI->>ASI: estado_pago = completo
    ASI-->>CLI: Venta muestra "Pago recibido"
```

## 5. Flujo de Documentos Legales

```mermaid
flowchart LR
    subgraph GENERACION["GENERACION"]
        A[Crear venta] -->|auto| B[Contrato cliente]
        C[Crear OC] -->|auto| D[Contrato proveedor]
        E[Manual] --> F[Generador 9 plantillas]
    end

    subgraph FIRMA_EMP["FIRMA EMPRESA"]
        B --> G[Admin firma + selfie]
        D --> G
        F --> G
    end

    subgraph PORTAL["PORTAL"]
        G --> H[Aparece como pendiente]
        H --> I[Cliente/proveedor firma]
        I --> J[Captura selfie camara frontal]
        J --> K[JPEG comprimido ~50KB]
    end

    subgraph REGISTRO["REGISTRO"]
        K --> L[Doc firmado completo]
        L --> M[Ambas firmas + selfies en documento]
        L --> N[Badge verde en admin]
    end
```

## 6. Flujo Contable Colombiano

```mermaid
flowchart TB
    subgraph ENTRADAS["ORIGENES"]
        V[Venta creada] -->|auto| AI[Asiento Ingreso]
        OC[OC creada] -->|auto| AE[Asiento Egreso]
        G[Gasto manual] --> AM[Asiento Manual]
        N[Nomina cerrada] --> AN[Asiento Nomina]
        CC[Caja chica] --> ACC[Asiento Caja Chica]
    end

    subgraph PUC_LINEAS["PARTIDA DOBLE"]
        AI --> L1[LineaAsiento DEBE: 1305 Clientes]
        AI --> L2[LineaAsiento HABER: 4135 Comercio]
        AE --> L3[LineaAsiento DEBE: 1405 Inventarios]
        AE --> L4[LineaAsiento HABER: 220505 Proveedores]
    end

    subgraph REPORTES["REPORTES"]
        L1 & L2 & L3 & L4 --> BP[Balance de Prueba]
        BP --> BG[Balance General]
        BP --> ER[Estado de Resultados]
        BP --> IVA[IVA: generado vs descontable]
        BP --> RET[Retenciones en la fuente]
        BP --> CIERRE[Cierre de periodo]
    end

    subgraph BANCO["RECONCILIACION"]
        CSV[Upload CSV banco] --> MB[Movimientos bancarios]
        MB -->|auto-match monto±$1 fecha±3d| AI & AE
        MB -->|manual match| AM
    end
```

## 7. Flujo de Produccion

```mermaid
flowchart TB
    VNT[Venta anticipo_pagado] -->|auto| OP[Orden Produccion]
    VNT -->|MP faltante| OC[OC automatica]

    OC -->|pago confirmado| PROV[Proveedor envia]
    PROV --> RECEP[Recepcion material]
    RECEP -->|OK| STOCK_MP[Stock MP +]
    RECEP -->|problema| CAL[Problema calidad]

    CAL --> T1[Ticket: contactar proveedor]
    CAL --> T2[Ticket: retraso venta]
    CAL -->|reabrir OC| OC

    OP --> RESERVA[Reservar MP FIFO]
    RESERVA --> PROD[Producir]
    PROD --> STOCK_PT[Stock PT +]
    STOCK_PT --> ENVIO[Envio con transportista]
    ENVIO --> ENTREGA[Acta de entrega]

    subgraph GANTT["GANTT"]
        OP -->|timeline| G1[Barra produccion]
        OC -->|timeline per-venta| G2[Barra materiales]
    end
```

## 8. Flujo de Nomina Colombiana

```mermaid
flowchart TB
    EMP[Empleados activos] --> CIERRE[Cerrar mes]
    PARAMS[Parametros editables] --> CIERRE
    CIERRE -->|prorrateo por dias| CALC[Calculo]

    CALC --> DED[Deducciones empleado]
    DED --> SAL_EMP[Salud 4%]
    DED --> PEN_EMP[Pension 4%]
    DED --> RET[Retencion fuente Art.383 ET]

    CALC --> APO[Aportes empleador]
    APO --> SAL_EMPR[Salud 8.5%]
    APO --> PEN_EMPR[Pension 12%]
    APO --> ARL[ARL segun nivel]
    APO --> CAJA[Caja 4%]
    APO --> SENA_[SENA 2%]
    APO --> ICBF_[ICBF 3%]

    CALC --> PREST[Prestaciones]
    PREST --> CES[Cesantias 1/12]
    PREST --> INT[Intereses cesantias 12%]
    PREST --> PRIMA[Prima 1/12]
    PREST --> VAC[Vacaciones 4.17%]

    CIERRE --> ASI[Asiento contable nomina]
    CIERRE --> RECIBO[Recibo de pago PDF]

    subgraph RETIRO["RETIRO / DESPIDO"]
        R1[Renuncia voluntaria]
        R2[Despido con justa causa]
        R3[Despido sin justa causa]
        R3 --> INDEM[Indemnizacion Art.64 CST]
        R1 & R2 & R3 --> LIQ[Liquidacion inmediata]
        LIQ --> GASTO[GastoOperativo]
        LIQ --> ASI_LIQ[Asiento contable]
    end
```

## 9. Mapa de Roles y Permisos

```mermaid
flowchart LR
    subgraph ROLES["ROLES DEL SISTEMA"]
        ADM[admin — Todo]
        DF[director_financiero — Finanzas + Aprobaciones]
        DO[director_operativo — Produccion + Compras + Aprobaciones]
        VEN[vendedor — Comercial]
        SM[sales_manager — Comercial + Portal]
        PRD[produccion — Produccion + Inventario]
        CON[contador — Finanzas]
        USU[usuario — Basico]
        CLI[cliente — Portal cliente]
        PRV[proveedor — Portal proveedor]
    end

    subgraph MODULOS["21 MODULOS"]
        M1[clientes]
        M2[ventas]
        M3[cotizaciones]
        M4[inventario]
        M5[produccion]
        M6[ordenes_compra]
        M7[finanzas]
        M8[nomina]
        M9[legal]
        M10[aprobaciones]
        M11[tareas]
        M12[notas]
        M13[calendario]
        M14[servicios]
        M15[logistica]
        M16[admin]
        M17[reportes]
        M18[empaques]
        M19[proveedores]
        M20[gastos]
        M21[portal]
    end

    ADM --> M1 & M2 & M3 & M4 & M5 & M6 & M7 & M8 & M9 & M10 & M16
    VEN --> M1 & M2 & M3 & M11
    PRD --> M4 & M5 & M18
    CON --> M7 & M8 & M20
    CLI --> M21
    PRV --> M21
```

## 10. Arquitectura de Archivos

```
evore-crm/
├── app.py                    # Flask factory + error handlers
├── extensions.py             # db, login_manager, mail singletons
├── models.py                 # 51 modelos + init_db() + migraciones
├── utils.py                  # Decoradores, filtros, constantes nomina
├── company_config.py         # Multi-empresa (CO/MX)
├── routes/
│   ├── __init__.py           # register_all()
│   ├── auth.py               # Login, logout, demo, onboarding
│   ├── dashboard.py          # Home, reportes, calendario, notificaciones
│   ├── clientes.py           # CRUD clientes + contactos
│   ├── ventas.py             # Ventas, cotizaciones, estados, PDFs
│   ├── compras.py            # OC, cotizaciones proveedor
│   ├── produccion.py         # Ordenes, recetas, gantt, recepcion MP
│   ├── inventario.py         # Productos, lotes, import masivo
│   ├── contable.py           # Asientos, PUC, balances, IVA, reconciliacion
│   ├── nomina.py             # Empleados, cierre, liquidacion, parametros
│   ├── admin.py              # Usuarios, legal, gastos, impuestos
│   ├── portal.py             # Portal cliente + proveedor + firma docs
│   ├── aprobaciones.py       # Workflow aprobaciones
│   ├── tareas.py             # Tickets
│   ├── notas.py              # Notas vinculadas
│   ├── empaques.py           # Empaque, simulador logistica
│   ├── servicios.py          # Catalogo servicios
│   ├── proveedores.py        # CRUD proveedores
│   └── api.py                # Busqueda global, health, AI
├── services/
│   ├── inventario.py         # Stock FIFO, reservas, lotes
│   └── nomina.py             # Calculo nomina CO/MX
├── templates/                # 135+ templates Jinja2
│   ├── base.html             # Dock sidebar + workspace tabs + onboarding
│   ├── portal_base.html      # Layout portal cliente/proveedor
│   └── [24 carpetas por modulo]
└── static/                   # Assets estaticos
```

## 11. Integraciones y Automatizaciones

| Trigger | Accion automatica |
|---------|------------------|
| Crear venta | Asiento contable ingreso + contrato cliente en portal |
| Crear OC | Asiento contable egreso + contrato proveedor en portal |
| Confirmar pago OC (contable) | OC → anticipo_pagado, proveedor ve "anticipo enviado" |
| Proveedor confirma anticipo | AsientoContable nota + notificacion equipo |
| Cliente reporta pago (portal) | PagoVenta + notificacion contable + badge en asiento |
| Confirmar ingreso (contable) | Venta → anticipo_pagado + reservar stock + generar OC auto |
| Venta anticipo_pagado | Stock reservado + OC auto para MP faltante |
| Recepcion MP (produccion) | Stock MP + + LoteMateriaPrima + MovimientoInventario |
| Problema calidad | 2 tickets auto (compras + ventas) + score proveedor |
| Despido/retiro empleado | Liquidacion + GastoOperativo + AsientoContable inmediato |
| Nomina sin cerrar dia 5 | Ticket automatico al admin |
| Documento firmado portal | Notificacion admin + badge "firmado" en registro |
| Upload CSV banco | MovimientoBancario + auto-match con asientos |

## 12. Stack Tecnologico

| Componente | Tecnologia |
|------------|-----------|
| Backend | Python 3.11 + Flask 3.x |
| ORM | SQLAlchemy + Flask-SQLAlchemy |
| DB produccion | PostgreSQL (Railway) |
| DB desarrollo | SQLite |
| Auth | Flask-Login + bcrypt |
| Templates | Jinja2 server-side |
| CSS | Bootstrap 5.3 + variables CSS custom |
| Icons | Bootstrap Icons |
| UI | Dock sidebar + iframe workspace tabs |
| Deploy | Railway.app (Gunicorn) |
| AI | OpenAI → Anthropic → Ollama (fallback chain) |
| Pais | Colombia (PUC, CST, Ley 100) / Mexico (CUC, IMSS) |
