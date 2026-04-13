---
name: Nunca eliminar datos automáticamente al iniciar
description: No agregar funciones de limpieza de datos en init_db o startup que modifiquen recetas, stock o cotizaciones
type: feedback
---

NUNCA agregar funciones automáticas en init_db() o al inicio de la app que eliminen o modifiquen datos de recetas, stock, cotizaciones o ingredientes.

**Why:** Se agregó _limpiar_empaques_huerfanos() que eliminaba cajas de recetas en cada deploy si no encontraba EmpaqueSecundario vinculado. Esto eliminó ingredientes que se habían agregado manualmente, causando cotizaciones sin costo de empaque — pérdida económica potencial.

**How to apply:** Las modificaciones a datos de negocio (recetas, stock, cotizaciones) solo deben ocurrir por acción explícita del usuario. Las funciones de init_db solo deben: crear tablas, ejecutar migraciones DDL, sembrar datos iniciales (PUC, admin), y generar SKUs faltantes.
