# DB local read-only — mapa de datos para chat/LLM

## Objetivo

Documentar la base local clonada de producción para habilitar consultas complejas desde el chat/LLM sin depender solo del catálogo curado actual.

## Conexión actual

- Motor: PostgreSQL local
- Configuración: `etl/config.py`
- Variables: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- Uso actual del proyecto:
  - ETL extrae desde PostgreSQL a Parquet
  - Dashboard consume mayormente Parquet/DuckDB
  - Chat actual usa vistas curadas, no la BD completa

## Hallazgos clave del esquema

### Jerarquía comercial

La jerarquía comercial usable para preguntas legibles es:

`agency -> group -> center -> master_center`

Join recomendado:

```sql
SELECT
  a.id   AS agency_id,
  a.name AS agency_name,
  g.name AS group_name,
  c.name AS center_name,
  mc.name AS master_center_name
FROM agencys a
LEFT JOIN groups g ON a.group_id = g.id
LEFT JOIN centers c ON g.center_id = c.id
LEFT JOIN master_centers mc ON c.master_center_id = mc.id;
```

Esto permite responder preguntas como:

- "¿A qué grupo pertenece esta agencia?"
- "¿En qué banca/centro cae esta agencia?"
- "Mostrame la jerarquía comercial de una agencia por nombre"

### Productos y sorteos

Tablas principales:

- `new_products` → producto comercial (`LA GRANJITA`, `LA RICACHONA`, etc.)
- `loteries` → sorteo puntual / franja horaria (`LA GRANJITA 07:00 PM`)
- `numbers` → catálogo de números
- `results` / `new_results` → resultados históricos
- `new_results_segment` → segmentos del resultado cuando aplica

Relaciones observadas:

- `sales_by_new_products_agency.new_product_id -> new_products.id`
- `sales_by_loteries.lotery_id -> loteries.id`
- `sales_by_loteries.new_product_id -> new_products.id`
- `results.lotery_id -> loteries.id`
- `results.number_id -> numbers.id`
- `new_results.lotery_id -> loteries.id`
- `new_results_segment.new_result_id -> new_results.id`

## Tablas de negocio más útiles para el chat

### 1. `sales_by_new_products_agency`

Uso: ventas agregadas por producto/agencia/fecha.

Columnas relevantes:

- `agency_id`
- `group_id`
- `new_product_id`
- `fecha`
- `sales`
- `prize`
- `currency_id`

⚠️ Importante: la clave del producto es **`new_product_id`**, NO `product_id`.

Ejemplo real:

```sql
SELECT np.name AS producto, SUM(s.sales) AS ventas
FROM sales_by_new_products_agency s
LEFT JOIN new_products np ON s.new_product_id = np.id
GROUP BY 1
ORDER BY ventas DESC;
```

### 2. `sales_by_loteries`

Uso: ventas agregadas por sorteo específico.

Columnas relevantes:

- `new_product_id`
- `lotery_id`
- `sales`
- `prize`
- `fecha`
- `moneda_id`

Ejemplo:

```sql
SELECT l.name AS sorteo, l.lotery_hour, SUM(s.sales) AS ventas
FROM sales_by_loteries s
LEFT JOIN loteries l ON s.lotery_id = l.id
GROUP BY 1,2
ORDER BY ventas DESC;
```

### 3. `agencys`, `groups`, `centers`, `master_centers`

Uso: lookup semántico de agencia → grupo → banca → master.

### 4. `results`, `new_results`, `new_results_segment`

Uso: responder preguntas sobre resultados históricos, por ejemplo:

- "¿Cuáles números han salido más en La Granjita 07:00 PM?"
- "¿Qué salió más en el sorteo X?"

Consulta validada en la base:

```sql
SELECT
  l.name AS sorteo,
  l.lotery_hour,
  COALESCE(n.value, n.name, nr.result) AS numero,
  COUNT(*) AS veces
FROM loteries l
LEFT JOIN results r ON r.lotery_id = l.id
LEFT JOIN numbers n ON r.number_id = n.id
LEFT JOIN new_results nr ON nr.lotery_id = l.id AND nr.procesed = r.procesed
WHERE UPPER(l.name) = 'LA GRANJITA 07:00 PM'
GROUP BY 1,2,3
HAVING COALESCE(n.value, n.name, nr.result) IS NOT NULL
ORDER BY veces DESC, numero;
```

## Ejemplos de preguntas que la base YA soporta

### ¿Cuál producto vendió más?

Sí. Se responde con `sales_by_new_products_agency + new_products`.

Resultado validado: `LA GRANJITA` aparece como producto líder en ventas acumuladas.

### ¿Esta agencia a qué grupo pertenece?

Sí. Se responde con `agencys + groups + centers + master_centers`.

Debe resolverse por nombre amigable, no solo por ID.

### ¿Cuáles son los números que más han salido en La Granjita 07:00 PM?

Sí. La base soporta esa pregunta usando `loteries + results + numbers (+ new_results)`.

Resultado validado en muestra histórica: aparecen frecuencias altas para números como `23`, `25`, `15`, `24`, `14`, `16` en `LA GRANJITA 07:00 PM`.

## Tablas particionadas diarias

La operación transaccional está particionada por día:

- `tickets_YYYYMMDD`
- `bets_YYYYMMDD`

Ejemplos confirmados:

- `tickets_20251027`
- `bets_20251027`

Columnas útiles observadas:

### `tickets_YYYYMMDD`

- `id`
- `created`
- `total_amount`
- `cant_bets`
- `agency_id`
- `group_id`
- `center_id`
- `master_center_id`
- `ticket_status_id`
- `prize`
- `moneda_id`
- `transacction_id`

### `bets_YYYYMMDD`

- `id`
- `created`
- `amount`
- `prize`
- `ticket_id`
- `lotery_id`
- `number`
- `bet_statu_id`
- `tripleta_count`

## Implicaciones para el chat/LLM

### Lo que hoy falla

El chat actual trabaja con un catálogo corto de vistas/funciones. Eso lo hace seguro, pero ciego frente a preguntas fuera del catálogo.

### Lo que conviene hacer ahora

Implementar una **capa híbrida**:

1. **Modo curado** para preguntas frecuentes y rápidas.
2. **Modo exploratorio read-only** sobre la base local para preguntas complejas.

### Reglas mínimas para el modo exploratorio

- Solo `SELECT`
- Límite automático de filas
- Timeout corto
- Catálogo/schema visible al LLM
- Resolución por nombre amigable (`ILIKE`) para agencias, productos y sorteos
- Respuestas redactadas en lenguaje de negocio

## Ambigüedades a resolver antes de automatizar todo

1. **"Lo que más salió" vs "lo más apostado"**
   - `results/new_results` = resultados históricos
   - `bets/sales` = comportamiento de apuesta/venta
   - El chat debe diferenciar ambos conceptos explícitamente.

2. **Sorteos con minutos desplazados**
   - Ejemplo: `LA GRANJITA 07:00 PM` está guardado como `19:02`.
   - El chat debe mapear horario comercial ↔ horario real de base.

3. **Particiones diarias**
   - Para detalle transaccional, el motor debe poder consultar múltiples tablas `tickets_YYYYMMDD` / `bets_YYYYMMDD` sin que el LLM improvise nombres incorrectos.

## Recomendación técnica

Crear una réplica analítica local con DuckDB o vistas materializadas que unifiquen:

- jerarquía comercial,
- ventas por producto,
- ventas por sorteo,
- resultados históricos,
- detalle transaccional reciente.

Eso permitiría que el chat responda consultas complejas sin depender de joins improvisados sobre tablas particionadas.

## Implementación realizada (capa híbrida)

Se construyó una **capa híbrida** que mantiene el catálogo curado DuckDB y agrega acceso read-only controlado a PostgreSQL local.

### Archivos nuevos/modificados

- `dashboard/db_local.py` — funciones seguras de consulta a PostgreSQL local.
- `dashboard/llm/chat_assistant.py` — integración de la capa híbrida en el flujo de respuesta.

### Funciones expuestas (`dashboard/db_local.py`)

| Función | Uso |
|---------|-----|
| `jerarquia_agencia(nombre_fragmento)` | Busca agencia por nombre y devuelve grupo/centro/master. |
| `producto_mas_vendido(rango_dias, n)` | Top productos por ventas (histórico o con filtro de días). |
| `sorteos_por_nombre(nombre_fragmento)` | Lookup de sorteos por nombre amigable. |
| `numeros_mas_apostados(sorteo_nombre, rango_dias, n)` | Frecuencia de apuestas desde tablas `bets_YYYYMMDD` particionadas. |
| `numeros_mas_salidos(sorteo_nombre, rango_dias, n)` | Frecuencia de resultados históricos (`results` + `new_results`). |

### Guardrails aplicados

- Conexión con `default_transaction_read_only=on`.
- Solo sentencias `SELECT` encapsuladas; no se expone SQL arbitrario.
- Límite de filas por consulta (`max_rows=5000`).
- Timeout de conexión (`connect_timeout=10`).
- No se permiten palabras clave de DDL/DML (mantenido del flujo DuckDB existente).

### Flujo del chat

1. El usuario hace una pregunta.
2. Se detecta intención (jerarquía, producto más vendido, números apostados/salidos).
3. Se ejecuta la función segura correspondiente en PostgreSQL local.
4. Los datos se pasan al LLM para redactar la respuesta en lenguaje de negocio.
5. Si no aplica DB local, se mantiene el flujo existente: SQL asistido sobre DuckDB → catálogo de funciones Python.

## Memoria conversacional estructurada

El chat ahora mantiene memoria conversacional explícita en sesión para no perder contexto en seguimientos ambiguos.

### Qué recuerda

- `entity_type` (`agency`, `product`, `lottery`, etc.)
- `entity_name`
- `lottery_hour`
- `months`
- `metric`
- `rango_dias`

### Qué resuelve mejor

Ejemplos de follow-up que ahora deben funcionar mejor:

- "¿Cuál es la agencia que lidera las ventas?" → "¿cuánto vende?" → "¿y en febrero vs marzo?"
- "La Granjita 07:00 PM" → "¿y ese horario cuánto mueve?"
- "¿Cuál fue la diferencia de ventas de febrero y marzo de esa agencia?"

### Regla importante

La memoria estructurada tiene prioridad sobre el matcher difuso cuando el usuario hace una referencia como:

- "esa agencia"
- "ese producto"
- "ese sorteo"
- "ese horario"

Esto evita que el chat derive a otra entidad solo por coincidencias parciales de texto.

### Reglas de negocio aplicadas

| Pregunta del usuario | Fuente usada |
|----------------------|--------------|
| "número más apostado" / "qué número apuestan más" | `bets_YYYYMMDD` (particiones diarias) |
| "número que más salió" / "cuál sale más" | `results` / `new_results` |
| "qué producto vendió más" | `sales_by_new_products_agency` |
| "últimos 30 días", "3 meses", "este mes" | Filtro de fecha aplicado cuando existe |
| "a qué grupo pertenece esta agencia" | `agencys + groups + centers + master_centers` |

### Detalles de implementación

- **Resolución por nombre amigable**: las funciones usan `ILIKE` para buscar agencias, productos y sorteos sin exigir IDs exactos.
- **Particiones diarias**: `numeros_mas_apostados` consulta `information_schema.tables` para descubrir tablas `bets_YYYYMMDD` existentes en el rango solicitado, luego construye `UNION ALL` dinámico con límite de tablas.
- **Horarios desplazados**: el sorteo `LA GRANJITA 07:00 PM` se resuelve por nombre completo (`ILIKE`) sin depender del `lotery_hour` exacto (`19:02`).

### Próximo paso sugerido

- Agregar más funciones de negocio a `dashboard/db_local.py` (ej: ventas por agencia en rango, tickets anulados recientes, proveedores más usados).
- Materializar vistas en DuckDB periódicamente para reducir latencia en preguntas frecuentes.
- Implementar cache por pregunta+sorteo+rango en `dashboard/llm/cache` para evitar reconsultas idénticas.
