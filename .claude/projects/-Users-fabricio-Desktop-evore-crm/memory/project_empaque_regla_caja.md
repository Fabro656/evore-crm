---
name: Regla de cobro de cajas en pedidos
description: Si un pedido no llena una caja completa, se cobra la caja igual (aunque vaya solo 1 unidad)
type: project
---

Las cajas de empaque secundario se cobran por unidad completa, sin importar si van llenas o no. Si un pedido requiere 13 unidades y la caja es de 12, se cobran 2 cajas (una llena + una con 1 unidad).

**Why:** Regla de negocio para manufactura — la caja se usa igual así vaya incompleta. El cliente paga el empaque completo.

**How to apply:** Al calcular costos de empaque en ventas/cotizaciones, usar `math.ceil(cantidad / unidades_por_caja)` para redondear siempre hacia arriba el número de cajas. Esto aplica tanto al costo en la cotización como al consumo de stock de cajas.
