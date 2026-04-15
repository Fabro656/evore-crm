# routes/site.py — Public marketing pages for each module
from flask import render_template, abort

MODULES = {
    'ventas': {
        'name': 'Ventas', 'label': 'Ventas y CRM',
        'headline': 'De prospecto a entrega,\nsin perder un peso.',
        'tagline': 'Pipeline visual, cotizaciones, anticipos y trazabilidad completa.',
        'subline': 'Cada venta pasa por estados automáticos. Al confirmar anticipo se reserva inventario, se generan órdenes de compra y documentos legales.',
        'features': [
            {'label': 'Pipeline visual', 'title': 'Tarjetas que muestran todo de un vistazo.',
             'desc': 'Cada venta es una tarjeta con barra de color por estado, monto prominente, cliente, y badges de producción. Cambia el estado con un dropdown inline.',
             'checks': ['Prospecto → Negociación → Anticipo → Pagado → Entregado', 'Vista de tarjetas o tabla (toggle por usuario)', 'Buscador con filtros por estado'],
             'cards': [
                 {'icon': 'bi-bag', 'color': '#DD7A01', 'title': 'Textiles del Norte', 'sub': 'Negociación · 3 productos', 'value': '$12.5M'},
                 {'icon': 'bi-bag-check', 'color': '#0176D3', 'title': 'Industrias MakerCo', 'sub': 'Anticipo pagado · En producción', 'value': '$8.2M'},
                 {'icon': 'bi-check-circle', 'color': '#2E844A', 'title': 'Cosméticos Luna', 'sub': 'Entregado · Pagado completo', 'value': '$5.8M'},
             ]},
            {'label': 'Cotizaciones', 'title': 'Cotiza en minutos, cierra en horas.',
             'desc': 'Crea cotizaciones profesionales con productos, cantidades, precios y condiciones. Genera PDF automático para enviar al cliente.',
             'checks': ['PDF profesional con logo de tu empresa', 'Anticipo configurable por cliente', 'Seguimiento de cotizaciones enviadas vs aprobadas'],
             'cards': [
                 {'icon': 'bi-file-earmark-text', 'color': '#0176D3', 'title': 'COT-2026-089', 'sub': 'Textiles del Norte · 5 items', 'value': '$14.2M'},
                 {'icon': 'bi-clock', 'color': '#DD7A01', 'title': 'COT-2026-088', 'sub': 'Enviada hace 3 días', 'value': '$6.8M'},
                 {'icon': 'bi-check-all', 'color': '#2E844A', 'title': 'COT-2026-085', 'sub': 'Aprobada → Venta creada', 'value': '$9.1M'},
             ]},
            {'label': 'Comisiones', 'title': 'Tu equipo de ventas, motivado.',
             'desc': 'Calcula comisiones automáticamente por vendedor basado en ventas completadas. Porcentaje configurable por producto o por vendedor.',
             'checks': ['Comisión automática al completar venta', 'Reporte por vendedor y período', 'Marcado de pago desde el sistema'],
             'cards': [
                 {'icon': 'bi-person', 'color': '#7C3AED', 'title': 'Ana Martínez', 'sub': 'Sales Manager · 8 ventas', 'value': '$2.4M'},
                 {'icon': 'bi-person', 'color': '#0176D3', 'title': 'Carlos Ruiz', 'sub': 'Vendedor · 5 ventas', 'value': '$1.1M'},
                 {'icon': 'bi-graph-up', 'color': '#2E844A', 'title': 'Total Q1 2026', 'sub': '23 ventas cerradas', 'value': '$8.9M'},
             ]},
        ],
        'stats': [
            {'value': '100%', 'label': 'Trazabilidad de cada peso'},
            {'value': '7', 'label': 'Estados de venta'},
            {'value': 'PDF', 'label': 'Cotizaciones y facturas automáticas'},
            {'value': '∞', 'label': 'Ventas sin límite'},
        ]
    },
    'produccion': {
        'name': 'Producción', 'label': 'Producción y BOM',
        'headline': 'Recetas, órdenes\ny trazabilidad total.',
        'tagline': 'Control de producción con recetas BOM, lotes FIFO y Gantt de planta.',
        'subline': 'Define las recetas de tus productos, crea órdenes de producción, asigna operarios y controla cada gramo de materia prima consumida.',
        'features': [
            {'label': 'Recetas BOM', 'title': 'El ADN de cada producto.',
             'desc': 'Cada receta define ingredientes, cantidades, clasificación (materia prima, empaque primario, secundario) y calcula el costo automáticamente.',
             'checks': ['Costo automático basado en cotizaciones vigentes', 'Margen y precio de venta con IVA', 'Alertas de ingredientes sin cotización'],
             'cards': [
                 {'icon': 'bi-diagram-3', 'color': '#7C3AED', 'title': 'Crema Hidratante 250ml', 'sub': '8 ingredientes · Margen 42%', 'value': '$18.500'},
                 {'icon': 'bi-box2-heart', 'color': '#DD7A01', 'title': 'Empaque secundario', 'sub': 'Caja x24 + cinta embalaje', 'value': '$2.100'},
                 {'icon': 'bi-calculator', 'color': '#2E844A', 'title': 'Precio venta c/IVA', 'sub': 'Margen 42% + IVA 19%', 'value': '$31.200'},
             ]},
            {'label': 'Órdenes de producción', 'title': 'Del pedido a la planta, automático.',
             'desc': 'Al confirmar una venta, se generan órdenes de producción que consumen stock reservado con lógica FIFO. Asigna operarios y trackea progreso.',
             'checks': ['Generación automática desde venta confirmada', 'Asignación de operarios por orden', 'Gantt visual de carga de planta'],
             'cards': [
                 {'icon': 'bi-gear-wide-connected', 'color': '#0176D3', 'title': 'OP-2026-0047', 'sub': 'En producción · Carlos M.', 'value': '500 uds'},
                 {'icon': 'bi-hourglass-split', 'color': '#DD7A01', 'title': 'OP-2026-0048', 'sub': 'Pendiente materiales', 'value': '200 uds'},
                 {'icon': 'bi-check-all', 'color': '#2E844A', 'title': 'OP-2026-0045', 'sub': 'Completado · Lote L-0045', 'value': '1.200 uds'},
             ]},
        ],
        'stats': [
            {'value': 'FIFO', 'label': 'Consumo de materia prima'},
            {'value': 'BOM', 'label': 'Recetas con costo automático'},
            {'value': 'Gantt', 'label': 'Carga visual de planta'},
        ]
    },
    'inventario': {
        'name': 'Inventario', 'label': 'Inventario',
        'headline': 'Cada gramo, cada lote,\ncada vencimiento.',
        'tagline': 'Control de stock en tiempo real con alertas, lotes y reservas automáticas.',
        'subline': 'Productos terminados, materias primas, lotes con fecha de vencimiento, reservas vinculadas a ventas, y alertas de stock bajo.',
        'features': [
            {'label': 'Stock en tiempo real', 'title': 'Nunca más "se nos acabó".',
             'desc': 'Dashboard de inventario con tarjetas que muestran stock disponible, reservado y mínimo. Barra de color indica el estado: verde (ok), rojo (bajo).',
             'checks': ['Alertas automáticas de stock bajo', 'Tarjetas con indicador visual de nivel', 'Búsqueda por nombre, SKU o categoría'],
             'cards': [
                 {'icon': 'bi-box-seam', 'color': '#2E844A', 'title': 'Glicerina vegetal', 'sub': '3 lotes · Min: 50kg', 'value': '128.5 kg'},
                 {'icon': 'bi-exclamation-triangle', 'color': '#C23934', 'title': 'Fragancia lavanda', 'sub': '1 lote · Vence en 15 días', 'value': '2.3 lt'},
                 {'icon': 'bi-layers', 'color': '#DD7A01', 'title': 'Envase 250ml', 'sub': 'Reservado: 500 uds', 'value': '1.200 uds'},
             ]},
            {'label': 'Lotes y trazabilidad', 'title': 'Del proveedor al cliente, todo rastreado.',
             'desc': 'Cada compra genera un lote con número, proveedor, fecha de compra y vencimiento. El consumo sigue orden FIFO automáticamente.',
             'checks': ['Número de lote único por compra', 'Fecha de vencimiento con alertas (30/90 días)', 'Consumo FIFO automático en producción'],
             'cards': [
                 {'icon': 'bi-upc-scan', 'color': '#0176D3', 'title': 'L-2026-0089', 'sub': 'Glicerina · QuímicosCO', 'value': '50.0 kg'},
                 {'icon': 'bi-calendar-x', 'color': '#C23934', 'title': 'L-2026-0072', 'sub': 'Fragancia · Vence 30/04', 'value': '2.3 lt'},
                 {'icon': 'bi-arrow-repeat', 'color': '#2E844A', 'title': 'Consumo FIFO', 'sub': 'Lote más antiguo primero', 'value': 'Auto'},
             ]},
        ],
        'stats': [
            {'value': '∞', 'label': 'Productos sin límite'},
            {'value': 'FIFO', 'label': 'Consumo automático'},
            {'value': '30d', 'label': 'Alerta pre-vencimiento'},
        ]
    },
    'contabilidad': {
        'name': 'Contabilidad', 'label': 'Contabilidad PUC colombiana',
        'headline': 'Contabilidad colombiana\ncompleta y automatizada.',
        'tagline': 'PUC con 102 cuentas, asientos automáticos, 18 funcionalidades financieras y reportes fiscales.',
        'subline': 'Desde el asiento contable hasta el cierre de periodo. Todo lo que tu contador necesita, integrado con ventas, compras y nómina.',
        'features': [
            {'label': 'Asientos automáticos', 'title': 'Vendes o compras → se contabiliza solo.',
             'desc': 'Al crear una venta o confirmar una OC, el sistema genera el asiento contable con las cuentas PUC correctas automáticamente. El contador solo revisa y aprueba.',
             'checks': ['PUC completo Decreto 2650/1993 (102 cuentas)', 'Asiento de ingreso al confirmar venta', 'Asiento de egreso al crear OC', 'Confirmación bidireccional de pagos'],
             'cards': [
                 {'icon': 'bi-arrow-down-circle', 'color': '#2E844A', 'title': 'Ingreso VT-2026-089', 'sub': 'Textiles del Norte · Confirmado', 'value': '$12.5M'},
                 {'icon': 'bi-arrow-up-circle', 'color': '#C23934', 'title': 'Egreso OC-2026-034', 'sub': 'Químicos S.A. · Anticipo pagado', 'value': '$3.2M'},
                 {'icon': 'bi-journal-check', 'color': '#0176D3', 'title': 'Asiento NC-2026-012', 'sub': 'Nota crédito · Devolución parcial', 'value': '$450K'},
             ]},
            {'label': 'Reportes financieros', 'title': '6 reportes que tu contador va a amar.',
             'desc': 'Balance de prueba, balance general, estado de resultados, flujo de caja actual y proyectado, y libro auxiliar. Todo generado desde los asientos reales del sistema.',
             'checks': ['Balance de prueba por periodo', 'Balance general con activos/pasivos/patrimonio', 'Estado de resultados (P&L)', 'Flujo de caja proyectado'],
             'cards': [
                 {'icon': 'bi-bar-chart', 'color': '#0176D3', 'title': 'Balance de prueba', 'sub': 'Abril 2026 · 102 cuentas activas', 'value': 'Cuadrado'},
                 {'icon': 'bi-pie-chart', 'color': '#2E844A', 'title': 'Estado de resultados', 'sub': 'Ingresos $85M · Gastos $52M', 'value': '$33M'},
                 {'icon': 'bi-graph-up-arrow', 'color': '#7C3AED', 'title': 'Flujo de caja proyectado', 'sub': 'Mayo-Julio 2026 · 3 meses', 'value': '+$12M'},
             ]},
            {'label': 'Fiscal y tributario', 'title': 'IVA, retenciones y cierre sin dolor.',
             'desc': 'Calcula IVA generado vs descontable, retenciones en la fuente, certificados de retención, y cierre de periodo contable. Reglas tributarias configurables.',
             'checks': ['IVA generado vs descontable automático', 'Retención en la fuente por proveedor', 'Certificados de retención descargables', 'Cierre de periodo con un clic', 'Reglas tributarias personalizables'],
             'cards': [
                 {'icon': 'bi-percent', 'color': '#DD7A01', 'title': 'IVA Abril 2026', 'sub': 'Generado $8.2M · Descontable $3.1M', 'value': '$5.1M'},
                 {'icon': 'bi-file-earmark-ruled', 'color': '#0176D3', 'title': 'Retenciones fuente', 'sub': '15 proveedores · Abril 2026', 'value': '$1.8M'},
                 {'icon': 'bi-lock', 'color': '#2E844A', 'title': 'Cierre Marzo 2026', 'sub': '847 asientos · Aprobado', 'value': 'Cerrado'},
             ]},
            {'label': 'Operaciones diarias', 'title': 'Conciliación, notas y gastos en un lugar.',
             'desc': 'Reconciliación bancaria automática, notas crédito y débito, registro de gastos operativos, y movimientos bancarios trazables.',
             'checks': ['Conciliación bancaria con matching automático', 'Notas crédito y débito vinculadas', 'Gastos operativos con tipo y recurrencia', 'Libro diario con todos los movimientos'],
             'cards': [
                 {'icon': 'bi-bank', 'color': '#06B6D4', 'title': 'Conciliación Bancolombia', 'sub': '23 movimientos · 18 conciliados', 'value': '78%'},
                 {'icon': 'bi-receipt', 'color': '#C23934', 'title': 'Gasto: Arriendo bodega', 'sub': 'Recurrente mensual · Mayo 2026', 'value': '$4.5M'},
                 {'icon': 'bi-file-earmark-minus', 'color': '#DD7A01', 'title': 'Nota crédito NC-008', 'sub': 'Devolución Cosméticos Luna', 'value': '$890K'},
             ]},
        ],
        'stats': [
            {'value': '102', 'label': 'Cuentas PUC'},
            {'value': '18', 'label': 'Funcionalidades financieras'},
            {'value': '6', 'label': 'Reportes contables'},
            {'value': 'Auto', 'label': 'Asientos desde ventas y OC'},
        ]
    },
    'nomina': {
        'name': 'Nómina', 'label': 'Nómina colombiana',
        'headline': 'Nómina con toda\nla ley colombiana.',
        'tagline': 'Liquidación automática con Art. 383 ET, cesantías, prima, vacaciones y PILA.',
        'subline': 'Calcula la nómina de tu equipo con todos los conceptos de ley: horas extra, retención en la fuente, prestaciones sociales y aportes parafiscales.',
        'features': [
            {'label': 'Liquidación automática', 'title': 'De salario bruto a neto, un clic.',
             'desc': 'Ingresa el salario, las horas extra y las novedades. Evore calcula automáticamente todos los descuentos y aportes según ley vigente.',
             'checks': ['Retención fuente Art. 383 ET con UVT', 'Horas extra diurnas, nocturnas, festivas', 'Salud, pensión, ARL, caja, SENA, ICBF'],
             'cards': [
                 {'icon': 'bi-person', 'color': '#EC4899', 'title': 'María García', 'sub': 'Operaria · 2 H.E. diurnas', 'value': '$1.423.500'},
                 {'icon': 'bi-person', 'color': '#EC4899', 'title': 'Carlos Rodríguez', 'sub': 'Jefe producción · 0 H.E.', 'value': '$3.200.000'},
                 {'icon': 'bi-file-earmark-check', 'color': '#2E844A', 'title': 'Nómina Marzo', 'sub': '12 empleados · Cerrada', 'value': '$28.4M'},
             ]},
        ],
        'stats': [
            {'value': 'Art. 383', 'label': 'Retención en la fuente'},
            {'value': 'PILA', 'label': 'Archivo de aportes'},
            {'value': 'Auto', 'label': 'Liquidación de contrato'},
        ]
    },
    'compras': {
        'name': 'Compras', 'label': 'Compras y proveedores',
        'headline': 'Compra inteligente,\nproveedores calificados.',
        'tagline': 'Órdenes de compra con aprobaciones, cotizaciones comparativas y scoring.',
        'subline': 'Gestiona tus proveedores, compara cotizaciones, aprueba órdenes de compra y califica automáticamente a cada proveedor por cumplimiento.',
        'features': [
            {'label': 'Órdenes de compra', 'title': 'Del requerimiento al despacho.',
             'desc': 'Crea OC desde requisiciones o manualmente. Flujo de aprobación integrado. Al confirmar, se genera asiento contable y documento legal.',
             'checks': ['Flujo: borrador → anticipo → recibida', 'Aprobaciones por monto', 'Documento legal auto-generado'],
             'cards': [
                 {'icon': 'bi-cart-check', 'color': '#0176D3', 'title': 'OC-2026-034', 'sub': 'Químicos S.A. · Anticipo pagado', 'value': '$3.2M'},
                 {'icon': 'bi-truck', 'color': '#DD7A01', 'title': 'OC-2026-035', 'sub': 'LogiExpress · En tránsito', 'value': '$890K'},
                 {'icon': 'bi-check-circle', 'color': '#2E844A', 'title': 'OC-2026-031', 'sub': 'Empaques CO · Recibida', 'value': '$1.5M'},
             ]},
        ],
        'stats': [
            {'value': 'Score', 'label': 'Calificación automática'},
            {'value': '∞', 'label': 'Proveedores sin límite'},
            {'value': 'PDF', 'label': 'OC con formato profesional'},
        ]
    },
    'marketplace': {
        'name': 'Marketplace', 'label': 'Somos Evore',
        'headline': 'El marketplace\ndonde tu calidad habla.',
        'tagline': 'Publica productos, conecta con empresas y construye reputación.',
        'subline': 'Somos Evore es el foro-marketplace donde las empresas publican sus productos y servicios, se descubren mutuamente, y la comunidad califica la calidad.',
        'features': [
            {'label': 'Publicar', 'title': 'Tu vitrina para toda la comunidad.',
             'desc': 'Publica tus productos y servicios con imagen, precio, industria y descripción. Los usuarios buscan por industria, tipo o valoración.',
             'checks': ['Imágenes de producto', '30 categorías de industria', 'Filtros por tipo y valoración'],
             'cards': [
                 {'icon': 'bi-shop', 'color': '#8B5CF6', 'title': 'Empaques PlástiCo', 'sub': 'Envases PET · ★★★★★ (23)', 'value': '$850/und'},
                 {'icon': 'bi-truck', 'color': '#06B6D4', 'title': 'LogiExpress Colombia', 'sub': 'Transporte · ★★★★☆ (15)', 'value': 'Servicio'},
                 {'icon': 'bi-link-45deg', 'color': '#2E844A', 'title': 'Conexión creada', 'sub': 'Chat + Portal + Tarjetas', 'value': '✓'},
             ]},
            {'label': 'Valoraciones', 'title': 'La comunidad decide quién sube.',
             'desc': 'Después de una venta, el cliente valora de 1 a 5 estrellas con comentario. Los mejores proveedores suben al top. Apelaciones mediadas por Evore.',
             'checks': ['Estrellas 1-5 + comentario', 'Ranking por valoración promedio', 'Sistema de apelaciones con mediador'],
             'cards': [
                 {'icon': 'bi-star-fill', 'color': '#F59E0B', 'title': '4.8 promedio', 'sub': '23 valoraciones · 0 apelaciones', 'value': '★★★★★'},
                 {'icon': 'bi-chat-quote', 'color': '#0176D3', 'title': '"Excelente calidad"', 'sub': 'Industrias MakerCo · 5★', 'value': 'Hace 2d'},
                 {'icon': 'bi-shield-check', 'color': '#2E844A', 'title': 'Apelación resuelta', 'sub': 'A favor del proveedor', 'value': 'Eliminada'},
             ]},
        ],
        'stats': [
            {'value': '30', 'label': 'Industrias'},
            {'value': '1 clic', 'label': 'Para conectar'},
            {'value': '★★★★★', 'label': 'Sistema de reputación'},
        ]
    },
    'chat': {
        'name': 'Chat', 'label': 'Chat integrado',
        'headline': 'Comunica sin salir\ndel sistema.',
        'tagline': 'Chat interno entre empleados y chat inter-empresa con clientes y proveedores.',
        'subline': 'Panel flotante con pestañas, archivos adjuntos, y notificaciones automáticas desde MyEvore para recordatorios de pago y confirmaciones.',
        'features': [
            {'label': 'Chat en tiempo real', 'title': 'Adiós WhatsApp laboral.',
             'desc': 'Panel flotante estilo dock con pestañas por sala. Cada relación comercial tiene su canal de chat dedicado. Archivos adjuntos hasta 10MB.',
             'checks': ['Chat interno entre empleados', 'Chat inter-empresa automático', 'Archivos adjuntos (PDF, imágenes)', 'MyEvore: notificaciones automáticas'],
             'cards': [
                 {'icon': 'bi-chat-dots', 'color': '#06B6D4', 'title': 'Equipo Producción', 'sub': 'Chat interno · 5 miembros', 'value': '3 nuevos'},
                 {'icon': 'bi-building', 'color': '#0176D3', 'title': 'Químicos S.A.', 'sub': 'Chat proveedor', 'value': 'Hoy'},
                 {'icon': 'bi-robot', 'color': '#8B5CF6', 'title': 'MyEvore', 'sub': 'Recordatorio de pago enviado', 'value': 'Auto'},
             ]},
        ],
        'stats': None
    },
    'legal': {
        'name': 'Legal', 'label': 'Documentos legales',
        'headline': 'Documentos legales\nauto-generados.',
        'tagline': '9 plantillas colombianas con firma digital y selfie de verificación.',
        'subline': 'Contratos, actas de entrega, NDAs y autorizaciones de datos personales se generan automáticamente al crear ventas y órdenes de compra.',
        'features': [
            {'label': '9 plantillas', 'title': 'Todo listo para firmar.',
             'desc': 'Contrato cliente, contrato proveedor, prestación de servicios, contrato fijo, indefinido, carta de terminación, acta de entrega, NDA, y autorización de datos.',
             'checks': ['Firma digital con captura de selfie', 'Cumplimiento Ley 527/1999', 'Auto-generados al crear venta/OC', 'Visibles en portal del cliente/proveedor'],
             'cards': [
                 {'icon': 'bi-file-earmark-check', 'color': '#2E844A', 'title': 'Contrato cliente', 'sub': 'Textiles del Norte · Firmado', 'value': '2 firmas'},
                 {'icon': 'bi-file-earmark-text', 'color': '#DD7A01', 'title': 'Acta de entrega', 'sub': 'VT-2026-089 · Pendiente', 'value': '0 firmas'},
                 {'icon': 'bi-shield-lock', 'color': '#0176D3', 'title': 'NDA', 'sub': 'Químicos S.A. · Firmado', 'value': '2 firmas'},
             ]},
        ],
        'stats': [
            {'value': '9', 'label': 'Plantillas colombianas'},
            {'value': 'Selfie', 'label': 'Verificación de identidad'},
            {'value': 'Ley 527', 'label': 'Comercio electrónico'},
        ]
    },
}


def register(app):

    @app.route('/modulo/<slug>')
    def site_modulo(slug):
        module = MODULES.get(slug)
        if not module:
            abort(404)
        return render_template('site/modulo.html', module=module, active_module=slug)
