# BLOQUES 1 y 2 - DOCUMENTACIÓN TÉCNICA v30

## Resumen de Implementación

Se han implementado completamente dos módulos nuevos para el CRM/ERP Evore v30:
- **BLOQUE 1**: Módulo Empaques Secundarios (`routes/empaques.py` + templates)
- **BLOQUE 2**: Módulo Servicios (`routes/servicios.py` + templates)

Todos los archivos incluyen sintaxis válida, manejo de errores, validaciones y UX profesional.

---

## BLOQUE 1: EMPAQUES SECUNDARIOS

### Ubicación de Archivos
- Rutas: `/routes/empaques.py`
- Templates: `/templates/empaques/index.html`, `/templates/empaques/form.html`

### Modelo Utilizado
```python
class EmpaqueSecundario(db.Model):
    id, producto_id, alto, ancho, largo, peso_unitario, peso_max_caja
    unidades_por_caja, materia_prima_id, aprobado, notas, creado_por, creado_en
```

### Rutas Disponibles

#### 1. GET/POST `/empaques` - Lista y Calculadora
- **GET**: Muestra tabla de empaques existentes + formulario calculadora
- **Parámetros**: Ninguno (query string)
- **Roles**: @requiere_modulo('produccion')

#### 2. GET/POST `/empaques/nuevo` - Crear Empaque
- **GET**: Formulario vacío
- **POST**: Crear novo EmpaqueSecundario
- **Parámetros POST**:
  ```
  producto_id (requerido)
  alto, ancho, largo (cm)
  peso_unitario (kg)
  peso_max_caja (kg)
  unidades_por_caja
  notas
  ```

#### 3. POST `/empaques/calcular` - API Calculadora (JSON)
- **Content-Type**: application/json
- **Input**:
  ```json
  {
    "alto_prod": 15.5,
    "ancho_prod": 10.0,
    "largo_prod": 8.5,
    "peso_unitario": 0.5,
    "peso_max_caja": 25.0
  }
  ```
- **Output**:
  ```json
  {
    "opciones": [
      {
        "unidades": 6,
        "alto_caja": 17.5,
        "ancho_caja": 12.0,
        "largo_caja": 53.5,
        "peso_total": 3.0
      },
      ...
    ]
  }
  ```

#### 4. POST `/empaques/<id>/aprobar` - Aprobar y Crear MateriaPrima
- **Acción**:
  1. Crea MateriaPrima con nombre: `"Caja {producto_nombre} x{unidades}"`
  2. Establece `categoria='empaques'`, `unidad='unidades'`
  3. Vincula `empaque.materia_prima_id = mp.id`
  4. Marca `empaque.aprobado = True`
- **Respuesta**: Redirecciona a `/empaques` con flash success

#### 5. POST `/empaques/<id>/eliminar` - Eliminar Empaque
- **Restricción**: Solo empaques no aprobados, a menos que sea admin
- **Respuesta**: Redirecciona a `/empaques`

### Lógica de Calculadora

**Algoritmo**:
```python
max_unidades_por_peso = math.floor(peso_max_caja / peso_unitario)
opciones_sugeridas = [6, 12, 24, 48]
opciones = [o for o in opciones_sugeridas if o <= max_unidades_por_peso][:3]

Para cada opción:
  alto_caja = alto_prod + 2
  ancho_caja = ancho_prod + 2
  largo_caja = (largo_prod * unidades) + 2
  peso_total = unidades * peso_unitario
```

### Validaciones
- Producto requerido
- Todos los campos numéricos obligatorios (> 0)
- Al guardar: verifica que unidades × peso_unitario ≤ peso_max_caja
- Alerta si se excede peso máximo

### Integración en Reservas
Cuando se muestren reservas de un producto con EmpaqueSecundario aprobado:
```python
empaque = EmpaqueSecundario.query.filter_by(producto_id=p.id, aprobado=True).first()
if empaque:
    cajas_necesarias = math.ceil(cantidad_pedido / empaque.unidades_por_caja)
    # mostrar: "Se requieren X cajas"
```

---

## BLOQUE 2: SERVICIOS

### Ubicación de Archivos
- Rutas: `/routes/servicios.py`
- Templates: `/templates/servicios/index.html`, `/templates/servicios/form.html`

### Modelo Utilizado
```python
class Servicio(db.Model):
    id, nombre, descripcion, costo_interno, precio_venta
    unidad, categoria, activo, creado_por, creado_en

    @property
    def margen(self):
        # % de margen = (precio - costo) / precio * 100
```

### Rutas Disponibles

#### 1. GET `/servicios` - Lista Servicios
- **Parámetros**: Ninguno
- **Respuesta**:
  - Tabla con todos los servicios
  - Estadísticas: activos_count, precio_min, precio_max
- **Roles**: @requiere_modulo('ventas')

#### 2. GET/POST `/servicios/nuevo` - Crear Servicio
- **GET**: Formulario vacío
- **POST**: Crear nuevo Servicio
- **Parámetros POST**:
  ```
  nombre (requerido, máx 200 chars, no duplicado)
  descripcion (texto)
  categoria (máx 100 chars)
  costo_interno (float >= 0)
  precio_venta (float >= 0)
  unidad: [servicio | hora | día | proyecto | consultoría]
  ```
- **Validaciones**:
  - Nombre no puede duplicarse
  - Todos los campos numéricos validados
  - Flash success/warning en español

#### 3. GET/POST `/servicios/<id>/editar` - Editar Servicio
- **GET**: Formulario con valores actuales
- **POST**: Actualizar Servicio
- **Parámetros**: Iguales a crear
- **Validaciones**: No permite duplicar nombre (excluyendo el mismo objeto)

#### 4. POST `/servicios/<id>/toggle` - Activar/Desactivar
- **Acción**: Invierte valor de `activo` (True/False)
- **Respuesta**: Flash "activado"/"desactivado"

#### 5. POST `/servicios/<id>/eliminar` - Eliminar Servicio
- **Restricción**: Solo admin (`current_user.rol != 'admin'`)
- **Acción**: DELETE desde DB
- **Respuesta**: Flash info "eliminado"

#### 6. GET `/api/servicios/json` - API JSON
- **Content-Type**: application/json
- **Filtro**: Solo servicios activos (`activo=True`)
- **Output**:
  ```json
  [
    {
      "id": 1,
      "nombre": "Consultoría",
      "categoria": "Técnico",
      "precio_venta": 150000.0,
      "costo_interno": 50000.0,
      "unidad": "hora",
      "margen": 66.7
    },
    ...
  ]
  ```

### Cálculo de Margen
```python
@property
def margen(self):
    if not self.precio_venta or self.precio_venta == 0:
        return 0
    return round((self.precio_venta - self.costo_interno) / self.precio_venta * 100, 1)
```

**Interpretación**:
- `< 20%`: Margen bajo (badge rojo - warning)
- `20-40%`: Margen moderado (badge azul - info)
- `> 40%`: Margen saludable (badge verde - success)

### Previsualización en Tiempo Real
El formulario de servicios incluye panel en tiempo real que muestra:
- Costo Interno (COP)
- Precio de Venta (COP)
- Ganancia Bruta = Precio - Costo
- Margen % con badge dinámico
- Interpretación de rentabilidad

JavaScript ejecuta `actualizarMargen()` al cambiar valores.

### Validaciones
- Nombre requerido y único
- Campos numéricos >= 0
- Unidad es select con opciones predefinidas
- Flash messages en español

---

## Integración en Ventas y Cotizaciones

### En Formulario de Venta
```html
<!-- Agregar a venta_productos -->
<select name="servicio_id">
    <!-- Cargar desde /api/servicios/json -->
</select>
```

### En Formulario de Cotización
```html
<!-- Agregar a cotizacion_items -->
<select name="servicio_id">
    <!-- Cargar desde /api/servicios/json -->
</select>
```

### En VentaProducto
```python
servicio_id = db.Column(db.Integer, db.ForeignKey('servicios.id'), nullable=True)
es_servicio = db.Column(db.Boolean, default=False)
servicio = db.relationship('Servicio', foreign_keys=[servicio_id])
```

---

## Tablas en Base de Datos

### Ya Existentes (v30)
- `servicios` - tabla de servicios
- `empaques_secundarios` - tabla de empaques

### Cambios Relacionados (ya realizados en v30)
- `venta_productos`: agregado `servicio_id`, `es_servicio`, `unidad`
- `cotizacion_items`: agregado `servicio_id`, `unidad`, `iva_pct`, `tipo_item`

---

## Seguridad y Control de Acceso

### Decoradores Utilizados

```python
@login_required                      # Requiere usuario autenticado
@requiere_modulo('produccion')       # Para empaques
@requiere_modulo('ventas')           # Para servicios
```

El decorador `requiere_modulo` verifica:
- Usuario autenticado
- Usuario es admin O tiene acceso al módulo
- Si no: flash "No tienes acceso a este módulo" y redirecciona

### Operaciones Restringidas

**Solo Admin**:
- Eliminar servicios
- Eliminar empaques aprobados

**Registrada por Usuario**:
- Campo `creado_por` = `current_user.id`
- Campo `creado_en` = `datetime.utcnow()`

---

## Errores y Manejo de Excepciones

### En Rutas
```python
try:
    # operación de base de datos
    db.session.add(...)
    db.session.commit()
except Exception as e:
    db.session.rollback()
    flash(f'Error al {acción}: {str(e)}', 'danger')
```

### Validaciones de Entrada
- Campos requeridos: `if not valor`
- Duplicados: `query.filter_by(nombre=valor).first()`
- Numéricos: `float(...) / int(...)` con try/except
- Rango: `step="0.01" min="0"`

---

## URLs de Referencia

| Ruta | Método | Descripción |
|------|--------|-------------|
| `/empaques` | GET | Lista empaques + calculadora |
| `/empaques/nuevo` | GET/POST | Crear empaque |
| `/empaques/calcular` | POST | API calculadora (JSON) |
| `/empaques/<id>/aprobar` | POST | Aprobar + crear MP |
| `/empaques/<id>/eliminar` | POST | Eliminar empaque |
| `/servicios` | GET | Lista servicios |
| `/servicios/nuevo` | GET/POST | Crear servicio |
| `/servicios/<id>/editar` | GET/POST | Editar servicio |
| `/servicios/<id>/toggle` | POST | Activar/Desactivar |
| `/servicios/<id>/eliminar` | POST | Eliminar servicio |
| `/api/servicios/json` | GET | JSON de servicios activos |

---

## Pruebas Sugeridas

### BLOQUE 1 - Empaques
1. [ ] Crear empaque (verificar validaciones)
2. [ ] Usar calculadora (diferentes pesos)
3. [ ] Aprobar empaque (verificar creación de MP)
4. [ ] Verificar MateriaPrima creada en inventario
5. [ ] Eliminar empaque no aprobado
6. [ ] Intentar eliminar aprobado como no-admin (debe fallar)

### BLOQUE 2 - Servicios
1. [ ] Crear servicio (verificar nombre único)
2. [ ] Editar servicio (cambiar precios)
3. [ ] Verificar margen en tiempo real
4. [ ] Desactivar servicio (toggle)
5. [ ] Llamar `/api/servicios/json` (verificar JSON)
6. [ ] Intentar eliminar como no-admin (debe fallar)

---

## Notas de Desarrollo

- Todos los mensajes flash en español
- Utilizados iconos Font Awesome 6
- Bootstrap 5 para estilos
- Jinja2 para templates
- SQLAlchemy ORM para BD
- JavaScript vanilla (sin dependencias)
- Responsive design mobile-first

---

## Archivos Modificados

- `routes/__init__.py`: Agregados imports y registros

## Archivos Creados

1. `routes/empaques.py` (200 líneas)
2. `routes/servicios.py` (190 líneas)
3. `templates/empaques/index.html` (250 líneas)
4. `templates/empaques/form.html` (150 líneas)
5. `templates/servicios/index.html` (220 líneas)
6. `templates/servicios/form.html` (250 líneas)

**Total**: 6 archivos, ~1300 líneas de código funcional
