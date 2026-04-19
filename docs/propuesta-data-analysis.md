# 📊 Propuesta: Proyecto de Data Analysis — PremierPluss Taquilla

## Contexto del Negocio

PremierPluss es una **plataforma de loterías y animalitos** que opera a escala nacional con una arquitectura jerárquica: **Admin → Master Center (89) → Center (273) → Group (826) → Agency (5,474)**. La plataforma gestiona ~65 productos de apuestas (animalitos, triples, tripletas, pollas, centenas) a través de 7 proveedores externos activos.

### Magnitud de los Datos

| Métrica | Valor |
|---|---|
| **Rango de datos** | Oct 2025 → Abr 2026 (~6 meses) |
| **Tickets totales** | ~24 millones |
| **Apuestas (bets)** | ~112 millones |
| **Apuestas anuladas** | ~148 millones |
| **Productos activos** | ~45 de 65 |
| **Sorteos (loteries)** | 641 |
| **Usuarios** | ~158K |
| **Agencias activas** | 5,474 |
| **Cuotas configuradas** | ~77 millones |
| **Monedas** | VES (1), USD (2), COP (3), moneda_5 |
| **Proveedores externos** | NewTachira, Ijapos, MaxPlay, NewBanklot, NewChance, NewBetM3, Tote |

### Crecimiento Observado (Tickets/mes)

```
Oct 2025:    184,355  ████
Nov 2025:  1,541,724  ████████████████████████████████
Dic 2025:  4,188,665  ████████████████████████████████████████████████████████████████████████████████████████
Ene 2026:  4,663,085  ██████████████████████████████████████████████████████████████████████████████████████████████████
Feb 2026:  6,571,171  ██████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████
Mar 2026:  6,864,160  ██████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████
```

> [!IMPORTANT]
> **Crecimiento brutal: 37x en 5 meses** (184K → 6.8M tickets/mes). Esto indica una plataforma en fase de escalamiento agresivo, lo cual hace que el análisis de datos sea CRÍTICO para la toma de decisiones.

---

## Propuesta: 6 Ejes de Análisis

### Eje 1: 📈 Dashboard de Performance Comercial

**Problema que resuelve:** No hay visibilidad consolidada del rendimiento del negocio. Las ventas, premios, comisiones y márgenes están dispersos en múltiples tablas.

**Qué construir:**
- Dashboard interactivo con métricas de ventas diarias/semanales/mensuales
- Análisis de **margen bruto** por producto (ventas - premios pagados)
- Ranking de agencias, grupos y centros por rendimiento
- Tendencias de crecimiento y estacionalidad
- Ratio de premios vs. ventas por producto (payout ratio)

**Tablas clave:**
- `sales_by_new_products_agency` (ventas por agencia, 2.6M registros)
- `sales_by_loteries` (ventas por sorteo, 2.5M registros)
- `sales_by_new_products_group` / `_center` / `_master_center`
- `sales_commissions` (comisiones, 6.7M registros)

**Métricas descubiertas (ventas mensuales VES):**

| Mes | Ventas VES | Premios VES | Margen Bruto | % Margen |
|---|---|---|---|---|
| Oct 2025 | 34.5M | 26.9M | 7.5M | 21.8% |
| Nov 2025 | 357.6M | 269.6M | 88.0M | 24.6% |
| Dic 2025 | 1,111.5M | 819.3M | 292.2M | 26.3% |
| Ene 2026 | 1,479.0M | 1,080.3M | 398.7M | 27.0% |
| Feb 2026 | 2,180.7M | 1,590.9M | 589.9M | 27.0% |
| Mar 2026 | 2,586.4M | 1,901.0M | 685.4M | 26.5% |

> [!TIP]
> El **margen bruto se estabiliza alrededor del 26-27%**, lo cual es saludable para una plataforma de loterías. Pero hay oportunidad de analizar si ciertos productos o sorteos tienen margenes significativamente distintos.

**Stack Python sugerido:** `pandas`, `plotly/dash` o `streamlit`, `sqlalchemy`

---

### Eje 2: 🔍 Detección de Fraude y Apuestas Sospechosas

**Problema que resuelve:** El sistema actual tiene un detector básico (>15 jugadas por lotería = sospechoso, documentado en `09-ventas-y-reportes.md`), pero no hay un análisis retroactivo ni predictivo.

**Qué construir:**
- Análisis de patrones anómalos de apuestas (clustering de comportamiento)
- Detección de agencias con tasas de anulación inusualmente altas
- Correlación entre apuestas y resultados (¿alguien apuesta consistentemente a números ganadores?)
- Detección de colusión entre agencias del mismo grupo
- Análisis temporal de picos de anulaciones cercanos al cierre de sorteos

**Tablas clave:**
- `bets_*` (particiones diarias, 112M registros) — amount, number, lotery_id, ticket_id
- `tickets_*` (particiones diarias, 24M registros) — ticket_status_id, anull_by, anull_date
- `bets_anull` (148M registros anulados — **más que bets activos**, esto es una señal)
- `tickets_anull` (747K tickets anulados)
- `results` (324K resultados)
- `suca_anull_directory` (2.4M registros)

> [!WARNING]
> **Red flag encontrada:** Hay **148M bets anuladas vs ~112M bets activas**. Un ratio de anulación >1.3x es anormal y merece investigación profunda. ¿Son re-intentos fallidos de providers? ¿Fraude? ¿UX que causa anulaciones accidentales?

**Técnicas:** Anomaly detection (Isolation Forest, DBSCAN), análisis estadístico de distribuciones de apuestas, series temporales con Prophet

**Stack Python sugerido:** `scikit-learn`, `pandas`, `matplotlib/seaborn`, `scipy.stats`

---

### Eje 3: 🏪 Segmentación y Health Score de Agencias

**Problema que resuelve:** Con 5,474 agencias activas, no hay forma de identificar cuáles son las más rentables, cuáles están en declive, y cuáles podrían estar abusando del sistema.

**Qué construir:**
- **Health Score** por agencia con múltiples dimensiones:
  - Volumen de ventas (absoluto y tendencia)
  - Diversificación de productos (¿apuestan en muchos productos o solo uno?)
  - Ratio de anulaciones
  - Frecuencia de operación (días activos por semana/mes)
  - Proximidad a límites de venta (`agency_sale_by_currencies`)
  - Ratio premio/venta
- **Segmentación (clustering):** Identificar grupos naturales de agencias (alto volumen/bajo margen, bajo volumen/alto margen, etc.)
- **Churn prediction:** ¿Qué agencias están en riesgo de dejar de operar?

**Tablas clave:**
- `agencys` (67K registros, incluye inactivas)
- `sales_by_new_products_agency` — ventas, premios, comisiones, utilidad, ganancias
- `agency_sale_by_currencies` — límites configurados
- `provider_agency_blocked` — agencias bloqueadas
- `tickets_*` por agency_id
- `agencys_products` (9.5M registros — productos habilitados por agencia)
- `agencys_currencies` (266K — monedas por agencia)

**Stack Python sugerido:** `scikit-learn` (KMeans, PCA), `pandas`, `plotly`

---

### Eje 4: 🎰 Análisis de Productos y Sorteos

**Problema que resuelve:** Con ~45 productos activos y ~641 sorteos, no hay claridad sobre cuáles generan más valor, cuáles están sub-utilizados, y cómo optimizar la oferta.

**Qué construir:**
- **Ranking de productos** por: ventas totales, margen, crecimiento, concentración de agencias
- **Análisis de canibalización**: ¿Productos nuevos canibalizan ventas de productos existentes?
- **Horarios óptimos**: ¿Qué horas generan más ventas? (los sorteos van de 9AM a 7PM con ventanas horarias)
- **Market basket analysis**: ¿Qué combinaciones de productos se compran juntas en un mismo ticket?
- **Análisis por tipo de producto**: Comparar performance de animalitos (type_id=1) vs triples (type_id=2) vs tripletas (type_id=4) vs centenas (type_id=5)

**Tipos de producto detectados:**

| type_id | Tipo | Productos Activos | Ejemplo |
|---|---|---|---|
| 1 | Animalitos | ~15 | La Granjita, Lotto Activo, CazaLoton |
| 2 | Triples | ~10 | Triple Zulia, Triple Tachira, Triple Caracas |
| 3 | Terminales | ~3 | La Ruca, El Ruco, Terminal La Granjita |
| 4 | Tripletas | ~8 | Tripleta La Granjita, Tripleta Lotto Activo |
| 5 | Centenas/Zoo | ~8 | Zoologico Activo, Granjita Plus, Centena Plus |
| 6 | Pega | 0 (disabled) | Pega 5 |
| 7 | Pollas | 0 (disabled) | La Polla Pluss, La Polla Express |

**Tablas clave:**
- `new_products` — catálogo de productos con config JSON
- `loteries` — sorteos individuales con horarios y días
- `sales_by_loteries` — ventas y premios por sorteo/día
- `results` (324K) — números ganadores
- `winning_lotteries` (235K) — loterías ganadoras

**Stack Python sugerido:** `pandas`, `mlxtend` (association rules), `plotly`, `statsmodels`

---

### Eje 5: 💰 Análisis de Cuotas y Gestión de Riesgo

**Problema que resuelve:** La tabla `quotas` tiene **77 millones de registros** — la segunda tabla más grande del sistema. Los cupos limitan cuánto se puede apostar a un número específico en un sorteo. ¿Están bien calibrados?

**Qué construir:**
- **Análisis de utilización de cuotas**: ¿Qué porcentaje de los cupos se usa realmente?
- **Números calientes**: ¿Cuáles son los números más apostados? ¿Coincide con los más premiados?
- **Calibración de riesgo**: Comparar exposure máxima (si todos los cupos se llenan) vs. premios históricamente pagados
- **Simulación Monte Carlo**: ¿Cuál es la probabilidad de pérdida catastrófica en un día?
- **Optimización de cupos**: Recomendar ajustes basados en datos históricos

**Tablas clave:**
- `quotas` (77M) — cupos por número/lotería/rol/entidad/moneda
- `results` (324K) — para cruzar con números apostados
- `numbers` (101K) — catálogo de números
- `bets_*` — volumen real por número
- `setups` — configuración global de quota_min/quota_max

**Stack Python sugerido:** `numpy`, `scipy`, `pandas`, simulación Monte Carlo custom

---

### Eje 6: 🌐 Análisis de Proveedores Externos

**Problema que resuelve:** La plataforma depende de 7 proveedores externos para enviar apuestas. ¿Cuáles fallan más? ¿Cuáles son más lentos? ¿Cómo se distribuye el volumen?

**Qué construir:**
- **Distribución de volumen** por proveedor (tickets_provider tiene 6.1M registros)
- **Análisis de fallos**: Correlacionar `log_api_provider` (744K logs) con tasas de error por proveedor
- **Latencia por proveedor** (si los logs incluyen timestamps de request/response)
- **Dependencia operativa**: ¿Qué pasa si un proveedor cae? ¿Cuántas agencias se afectan?
- **Evolución temporal**: ¿Qué proveedores están creciendo/disminuyendo?

**Proveedores activos:**

| Provider | Código | Estado |
|---|---|---|
| NewTachira | NewTachira | ✅ Activo |
| Ijapos | Ijapos | ✅ Activo |
| MaxPlay | MaxPlay | ✅ Activo |
| NewBanklot | NewBanklot | ✅ Activo |
| NewChance | NewChance | ✅ Activo |
| NewBetM3 | NewBetM3 | ✅ Activo |
| Tote | Tote | ✅ Activo (nuevo) |
| VentaActiva | VentaActiva | ❌ Inactivo |
| Betf4 | Betf4 | ❌ Inactivo |

**Tablas clave:**
- `tickets_provider` (6.1M) — ticket_id → provider mapping
- `log_api_provider` (744K) — logs de llamadas a providers
- `external_providers` — configuración
- `provider_agency_blocked` — agencias bloqueadas por provider

**Stack Python sugerido:** `pandas`, `plotly`, `requests` (para health checks en vivo)

---

## Stack Tecnológico Recomendado

### Core

| Librería | Uso |
|---|---|
| **Python 3.12+** | Lenguaje base |
| **pandas** | Manipulación y análisis de datos |
| **sqlalchemy + psycopg2** | Conexión a PostgreSQL |
| **numpy** | Cálculos numéricos |

### Visualización

| Librería | Uso |
|---|---|
| **Streamlit** | Dashboard interactivo (rápido de implementar, ideal para MVP) |
| **Plotly** | Gráficos interactivos embebidos |
| **Seaborn/Matplotlib** | Gráficos estáticos para reportes |

### Machine Learning / Estadística

| Librería | Uso |
|---|---|
| **scikit-learn** | Clustering, anomaly detection, classification |
| **scipy** | Tests estadísticos, distribuciones |
| **Prophet** (Meta) | Forecasting de series temporales |
| **mlxtend** | Association rules (market basket) |

### Infraestructura

| Herramienta | Uso |
|---|---|
| **Jupyter Notebooks** | Exploración y documentación de análisis |
| **DuckDB** | Procesamiento local de datasets grandes (alternativa a cargar todo en pandas) |
| **Docker** | Containerización del dashboard |

---

## Roadmap de Implementación

### Fase 1: Fundación (Semana 1-2)
- [ ] Setup del proyecto Python con `pyproject.toml`
- [ ] Conexión a PostgreSQL con connection pooling
- [ ] Scripts de extracción de datos (ETL básico)
- [ ] Notebook exploratorio de cada eje

### Fase 2: Dashboard Comercial — Eje 1 (Semana 3-4)
- [ ] Pipeline de datos para métricas de ventas
- [ ] Dashboard Streamlit con KPIs principales
- [ ] Filtros por fecha, producto, agencia, moneda
- [ ] Exportación de reportes en PDF/Excel

### Fase 3: Detección de Fraude — Eje 2 (Semana 5-7)
- [ ] Análisis exploratorio de anulaciones (ratio 1.3x)
- [ ] Modelo de anomaly detection
- [ ] Alertas automatizadas
- [ ] Reporte de hallazgos

### Fase 4: Segmentación de Agencias — Eje 3 (Semana 8-9)
- [ ] Feature engineering por agencia
- [ ] Clustering y health score
- [ ] Dashboard de salud de red

### Fase 5: Análisis de Productos y Riesgo — Ejes 4-5 (Semana 10-12)
- [ ] Ranking de productos
- [ ] Simulación de riesgo
- [ ] Recomendaciones de calibración de cuotas

### Fase 6: Monitoring de Proveedores — Eje 6 (Semana 13-14)
- [ ] Pipeline de logs de proveedores
- [ ] Dashboard de salud de proveedores
- [ ] Alertas de degradación

---

## Estrategia de Extracción de Datos (ETL)

Al manejar volúmenes transaccionales del orden de los **112 millones de apuestas (bets)** y **24 millones de tickets**, es fundamental definir la metodología de interacción con los datos.

### ¿Consultas Directas, CSV o Parquet?

| Enfoque | Veredicto | Por qué |
|---|---|---|
| **❌ Buscar directo en Producción** | **Peligroso** | Hacer un simple agrupamiento (GROUP BY) sobre tablas de millones de filas bloquea transacciones del usuario final y ralentiza a los proveedores de lotería. |
| **⚠️ Extraer todo a CSV** | **Ineficiente** | 112 millones en CSV te pesarán alrededor de 15 a 20 GB. La máquina tiene que inferir tipos de texto en cada lectura, tardando minutos en responderte un query básico. |
| **✅ Extraer a Parquet** | **Industrial Standard** | Comprime 15 GB de CSV a aprox. 2-3 GB. Mantiene tipos nativamente (números como números, fechas como fechas). Puedes leerlo y graficarlo a velocidades asombrosas usando Pandas o DuckDB. |

### Arquitectura de Extracción Propuesta:

El objetivo de un analista o ingeniero de datos júnior aquí es crear un script sencillo con Python para alimentar un mini "Data Lake" local:

1. **Tablas Pequeñas (Dimensiones):** Extráelas de una vez, directamente. Tablas como `agencys`, `loteries`, `new_products`, `users`, y `setups`. Puedes pasarlas todas a `.parquet`.
2. **Tablas Agregadas Intermedias:** Aprovecha que tu base de datos ya resume información, y extrae las tablas `sales_by_loteries` y `sales_by_new_products_agency` de forma íntegra.
3. **Tablas Monstruosas (Hechos):** Nunca hagas `SELECT *` a `bets` o `tickets_index`. Para estas, tu script Python debe extraerlas "iterando mes a mes" y guardando particiones (Ej: `bets/2026-01.parquet`, `bets/2026-02.parquet`).

Una vez tu data viva en Parquet en tu propia carpeta local, podrás usar `DuckDB` o `pandas` localmente desde Jupyter Notebooks para responder cualquier pregunta sin miedo a tocar la caja registradora del negocio.

---

## Recomendación Final

> [!IMPORTANT]
> **Mi recomendación: Empezar por el Eje 2 (Detección de Fraude)**, no por el Eje 1.
>
> ¿Por qué? Porque el hallazgo de **148M bets anuladas vs 112M activas** es una anomalía que requiere investigación inmediata. Si es un problema técnico (reintentos de providers), necesita corrección. Si es fraude, está costando dinero. El Eje 1 (Dashboard) es valioso pero no urgente — los datos de ventas ya existen en las tablas `sales_by_*`.
>
> El Eje 2 es donde un Data Analyst aporta valor inmediato y diferencial.

---

## Consideraciones Técnicas

### Performance
- Las tablas `bets_*` y `tickets_*` están particionadas por día (246-247 particiones). **Siempre filtrar por fecha** para evitar full scans.
- Para análisis histórico, considerar extraer a DuckDB o Parquet en vez de hacer queries repetitivas a producción.

### Monedas
El sistema maneja múltiples monedas. Los IDs detectados son:
- `1` = VES (Bolívares)
- `2` = USD (Dólares)
- `3` = COP (Pesos colombianos, según el patrón)
- `5` = Moneda adicional (requiere verificar en `MonedasTable::MONEDAS`)

### Seguridad
- **NUNCA** conectarse directamente a producción para dashboards. Usar una **réplica de lectura** o un data warehouse.
- Las credenciales deben estar en variables de entorno, no hardcodeadas.
- La columna `config` de `external_providers` está **encriptada** — no se puede leer directamente desde Python.
