# Ejemplos de Uso: BLOQUES 1 y 2

## BLOQUE 1: Empaques Secundarios

### Ejemplo 1: Crear un Empaque

1. Ir a `/empaques`
2. En la sección "Calculadora de Empaques":
   - Seleccionar producto: "Chocolate Premium 100g"
   - Altura: 15.5
   - Ancho: 10.0
   - Largo: 8.5
   - Peso unitario: 0.5 kg
   - Peso máximo caja: 25.0 kg
3. Click en "Calcular Opciones"

**Resultado de Cálculo**:
- max_unidades = floor(25.0 / 0.5) = 50
- opciones sugeridas: [6, 12, 24, 48] → todas caben
- Se muestran 3 opciones (6, 12, 24)

**Opción 1: 6 unidades/caja**
- Dimensiones caja: 17.5 × 12.0 × 53.5 cm
- Peso total: 3.0 kg
- [Botón "Usar esta opción"]

**Opción 2: 12 unidades/caja**
- Dimensiones caja: 17.5 × 12.0 × 104.5 cm
- Peso total: 6.0 kg

**Opción 3: 24 unidades/caja**
- Dimensiones caja: 17.5 × 12.0 × 206.5 cm
- Peso total: 12.0 kg

4. Click "Usar esta opción" en Opción 2
5. Se pre-llena formulario con:
   - Producto: "Chocolate Premium 100g"
   - Alto: 17.5
   - Ancho: 12.0
   - Largo: 104.5
   - Peso unitario: 0.5
   - Peso máximo caja: 25.0
   - Unidades por caja: 12
6. Click "Crear Empaque"
7. Flash: "Empaque para 'Chocolate Premium 100g' creado como borrador."

### Ejemplo 2: Aprobar Empaque

1. En lista de empaques, encontrar "Chocolate Premium 100g"
2. Estado: "Borrador"
3. Click botón "Aprobar"
4. Confirmación: "¿Aprobar este empaque? Se creará una materia prima automáticamente."
5. Click "OK"
6. Flash: "Empaque aprobado. Materia prima 'Caja Chocolate Premium 100g x12' creada automáticamente."

**Resultado**:
- Nueva entrada en MateriaPrima:
  - nombre: "Caja Chocolate Premium 100g x12"
  - categoria: "empaques"
  - unidad: "unidades"
  - stock_disponible: 0
  - activo: True

### Ejemplo 3: Usar en Producción

Cuando se reserve producción para "Chocolate Premium 100g" (cantidad 36 unidades):
- Empaque.unidades_por_caja = 12
- Cajas necesarias = ceil(36 / 12) = 3 cajas
- Sistema reserva: MateriaPrima "Caja Chocolate Premium 100g x12" × 3

---

## BLOQUE 2: Servicios

### Ejemplo 1: Crear un Servicio

1. Ir a `/servicios`
2. Click "Nuevo Servicio"
3. Formulario:
   - Nombre: "Consultoría Técnica"
   - Descripción: "Asesoría especializada para implementación de sistemas"
   - Categoría: "Técnico"
   - Costo interno: $50,000 COP
   - Precio venta: $150,000 COP
   - Unidad: "hora"
4. En panel de previsualización (lado derecho):
   - Costo Interno: $ 50,000.00
   - Precio de Venta: $ 150,000.00
   - Ganancia Bruta: $ 100,000.00
   - Margen de Ganancia: 66.7%
   - Badge: "✓ Margen saludable" (verde)
5. Click "Crear Servicio"
6. Flash: "Servicio 'Consultoría Técnica' creado exitosamente."

### Ejemplo 2: Editar Servicio

1. En `/servicios`, click en "Consultoría Técnica"
2. Click botón "Editar" (icono lápiz)
3. Cambiar:
   - Precio venta: $175,000
4. Panel actualiza:
   - Ganancia Bruta: $ 125,000.00
   - Margen: 71.4%
   - Badge: "✓ Margen saludable" (verde)
5. Click "Actualizar Servicio"
6. Flash: "Servicio 'Consultoría Técnica' actualizado exitosamente."

### Ejemplo 3: Desactivar Servicio

1. En `/servicios`, ver "Instalación" (en lista)
2. Estado: "Activo" (badge verde)
3. Click toggle (icono power)
4. Confirmación implícita
5. Página refresca
6. Flash: "Servicio 'Instalación' desactivado."
7. Estado: "Inactivo" (badge rojo)

### Ejemplo 4: Usar API en Venta

**En formulario de venta** (JavaScript):

```javascript
fetch('/api/servicios/json')
  .then(r => r.json())
  .then(servicios => {
    const select = document.getElementById('servicio_id');
    servicios.forEach(s => {
      const option = document.createElement('option');
      option.value = s.id;
      option.textContent = `${s.nombre} - ${s.precio_venta} (Margen: ${s.margen}%)`;
      select.appendChild(option);
    });
  });
```

**Respuesta de API**:
```json
[
  {
    "id": 1,
    "nombre": "Consultoría Técnica",
    "categoria": "Técnico",
    "precio_venta": 175000.0,
    "costo_interno": 50000.0,
    "unidad": "hora",
    "margen": 71.4
  },
  {
    "id": 2,
    "nombre": "Instalación",
    "categoria": "Técnico",
    "precio_venta": 500000.0,
    "costo_interno": 200000.0,
    "unidad": "proyecto",
    "margen": 60.0
  },
  {
    "id": 3,
    "nombre": "Mantenimiento Mensual",
    "categoria": "Soporte",
    "precio_venta": 100000.0,
    "costo_interno": 30000.0,
    "unidad": "mes",
    "margen": 70.0
  }
]
```

### Ejemplo 5: Crear Venta con Servicio

1. En `/ventas/nueva`
2. Seleccionar cliente
3. En sección "Items de la Venta":
   - Tipo: "Servicio"
   - Servicio: "Consultoría Técnica" (select con opciones de API)
   - Cantidad: 2
   - Precio unitario: $175,000 (pre-llenado)
   - Subtotal: $350,000 (calculado)
4. Guardar venta
5. Confirmación

---

## Casos de Uso Combinados

### Escenario 1: Producto con Empaque + Incluir Servicio

**Cliente pide**: 20 unidades de "Chocolate Premium 100g" + servicio de empaque personalizado

**Proceso**:

1. **Venta producto**:
   - Producto: "Chocolate Premium 100g"
   - Cantidad: 20
   - Precio: $5,000 c/u
   - Subtotal: $100,000

2. **Reserva producción**:
   - Detecta EmpaqueSecundario aprobado (12 unidades/caja)
   - Calcula: ceil(20 / 12) = 2 cajas
   - Reserva MateriaPrima "Caja Chocolate Premium 100g x12" × 2

3. **Agregar servicio**:
   - Servicio: "Empaque Personalizado"
   - Cantidad: 1
   - Precio: $50,000
   - Subtotal: $50,000

4. **Venta total**:
   - Productos: $100,000
   - Servicios: $50,000
   - Total: $150,000

---

## Validaciones en Acción

### Empaque: Peso Excedido

**Usuario intenta**:
- Unidades por caja: 100
- Peso unitario: 0.5 kg
- Peso máximo: 25 kg
- Total: 100 × 0.5 = 50 kg > 25 kg

**Resultado**:
- Input recibe `onchange` event
- JavaScript valida: 50 > 25
- Alerta: "⚠️ Advertencia: El peso total de 100 unidades es 50.00 kg, que excede el peso máximo de 25 kg."

### Servicio: Nombre Duplicado

**Usuario intenta**:
- Crear servicio: "Consultoría Técnica"
- Ya existe uno con ese nombre

**Resultado**:
- POST a `/servicios/nuevo`
- Backend query: `Servicio.query.filter_by(nombre='Consultoría Técnica').first()`
- Encuentra duplicado
- Flash: "Ya existe un servicio llamado 'Consultoría Técnica'."
- Retorna formulario con datos


---

## Estadísticas en Dashboard

### Empaques
- Número de empaques aprobados: 3
- Número de empaques en borrador: 1
- Productos sin empaque: 5

### Servicios
- Servicios activos: 5
- Rango de precios: $50,000 - $500,000 COP
- Margen promedio: 65.3%
- Servicio más caro: "Instalación" ($500,000)

---

## Integración con Otras Funciones

### Desde Inventario
- Ver MateriaPrimas de tipo "empaques"
- Historial de cajas utilizadas
- Stock de empaques por producto

### Desde Reportes
- Análisis de margen por servicio
- Costo de empaque como % del producto
- Servicios más utilizados en ventas

---

## Errores Comunes y Soluciones

### Error 1: "No tienes acceso a este módulo"
**Causa**: Usuario no tiene módulo asignado
**Solución**: Admin asigna módulo 'produccion' o 'ventas' al usuario

### Error 2: "El nombre del servicio es obligatorio"
**Causa**: Usuario no completó nombre
**Solución**: Completar campo obligatorio

### Error 3: Calculadora no muestra opciones
**Causa**: peso_unitario > peso_max_caja
**Solución**: Aumentar peso máximo de caja

### Error 4: No puedo eliminar servicio
**Causa**: Solo admin puede eliminar
**Solución**: Desactivar servicio (toggle) o pedir a admin

---

## Testing Checklist

- [ ] Crear empaque, aprobar, verificar MateriaPrima
- [ ] Calcular con diferentes pesos
- [ ] Crear servicio con margen > 40%
- [ ] Crear servicio con margen < 20% (badge diferente)
- [ ] Editar servicio y ver margen actualizado
- [ ] Llamar `/api/servicios/json` con curl
- [ ] Desactivar/Activar servicio
- [ ] Intentar crear dupicado (debe fallar)
- [ ] Intentar eliminar como no-admin (debe fallar)
- [ ] Verificar MateriaPrimas en inventario
- [ ] Usar servicio en cotización
- [ ] Usar servicio en venta

---

FIN EJEMPLOS DE USO
