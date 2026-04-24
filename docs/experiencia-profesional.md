# Experiencia Profesional — PremierPluss Analytics

## Perfil del Proyecto

**Nombre:** PremierPluss Analytics
**Rol:** Data Engineer / Full-Stack Data Developer
**Duración:** 6 meses (Oct 2025 — Mar 2026)
**Tipo:** Plataforma integral de análisis de datos para operaciones de loterías y apuestas a escala nacional

---

## Contexto del Negocio

PremierPluss es una plataforma de loterías y animalitos con arquitectura jerárquica multinivel:

```
Admin → Master Center (89) → Center (273) → Group (826) → Agency (5,474)
```

La plataforma gestiona **~65 productos de apuestas** (animalitos, triples, tripletas, pollas, centenas) a través de **7 proveedores externos activos**, operando en **5 monedas** (VES, USD, BRL, PEN, COP).

---

## Métricas Clave del Proyecto

### Volumen de Datos Procesados

| Métrica | Valor |
|---|---|
| Tickets totales analizados | ~24 millones |
| Apuestas (bets) procesadas | ~112 millones |
| Apuestas anuladas investigadas | ~148 millones |
| Productos activos monitoreados | ~45 de 65 |
| Sorteos (loteries) configurados | 641 |
| Usuarios en el ecosistema | ~158,000 |
| Agencias activas gestionadas | 5,474 |
| Cuotas configuradas analizadas | ~77 millones |
| Proveedores externos integrados | 7 activos |

### Crecimiento Operativo Alcanzado

```
Oct 2025:    184,355 tickets/mes   ██
Nov 2025:  1,541,724 tickets/mes   ████████████
Dic 2025:  4,188,665 tickets/mes   ██████████████████████████
Ene 2026:  4,663,085 tickets/mes   █████████████████████████████
Feb 2026:  6,571,171 tickets/mes   ████████████████████████████████████████
Mar 2026:  6,864,160 tickets/mes   █████████████████████████████████████████
```

**Factor de crecimiento: 37x en 5 meses** (184K → 6.8M tickets/mes)

### Impacto Financiero

| Mes | Ventas (VES) | Premios (VES) | Margen Bruto | % Margen |
|---|---|---|---|---|
| Oct 2025 | 34.5M | 26.9M | 7.5M | 21.8% |
| Nov 2025 | 357.6M | 269.6M | 88.0M | 24.6% |
| Dic 2025 | 1,111.5M | 819.3M | 292.2M | 26.3% |
| Ene 2026 | 1,479.0M | 1,080.3M | 398.7M | 27.0% |
| Feb 2026 | 2,180.7M | 1,590.9M | 589.9M | 27.0% |
| Mar 2026 | 2,586.4M | 1,901.0M | 685.4M | 26.5% |

**Margen bruto estabilizado en 26-27%** con crecimiento sostenido de ventas.

---

## Stack Tecnológico

### Backend & Data Engineering
- **Python 3.12** — Lenguaje principal
- **SQLAlchemy + psycopg2** — ORM y conexión a PostgreSQL
- **DuckDB** — Motor de consultas analíticas sobre Parquet (reemplaza pandas para queries pesadas)
- **Parquet** — Formato de almacenamiento columnar (compresión 6:1 vs CSV)

### Frontend & Visualización
- **Streamlit** — Framework de dashboard interactivo (6 páginas)
- **Plotly** — Gráficos interactivos (barras, líneas, scatter, heatmaps)

### DevOps & Infraestructura
- **Docker** — Containerización (Python 3.12-slim, multi-stage build)
- **Nginx** — Reverse proxy con soporte WebSocket para Streamlit
- **uv** — Gestor de dependencias ultrarrápido (reemplazo de pip)

### Data Science (opcional)
- **scikit-learn** — Anomaly detection, clustering
- **scipy** — Tests estadísticos
- **Pandas** — Manipulación de datos en notebooks exploratorios

---

## Arquitectura del Sistema

### Pipeline de Datos ETL

```
PostgreSQL (producción)
    │
    ▼
Extractores Python (etl/extractors/)
    ├── facts.py      → Particiones diarias → Parquet mensual
    ├── dimensions.py → Catálogos completos → Parquet
    ├── providers.py  → Datos de proveedores → Parquet
    └── aggregated.py → Tablas pre-agregadas → Parquet
    │
    ▼
Data Lake Local (data/)
    ├── facts/         → bets_YYYYMM.parquet, tickets_YYYYMM.parquet
    ├── dimensions/    → agencys.parquet, products.parquet, loteries.parquet
    └── aggregated/    → sales_by_agency.parquet, sales_by_loteries.parquet
    │
    ▼
DuckDB (query engine)
    │
    ▼
Streamlit Dashboard (6 páginas)
```

### Decisiones de Arquitectura

| Decisión | Alternativa descartada | Razón |
|---|---|---|
| Parquet sobre CSV | CSV plano | 15GB CSV → 2-3GB Parquet. Tipos nativos, lectura 10x más rápida |
| DuckDB sobre Pandas | Cargar todo en memoria | DuckDB queryea Parquet directo sin materializar en RAM |
| ETL particionado por mes | SELECT * completo | Evita timeouts en tablas de 112M+ registros |
| Streamlit sobre Dash/Gradio | Dash (Plotly) | Desarrollo 3x más rápido, ideal para MVP iterativo |
| Multi-currency con rates API | Hardcodear tasas | Mercado cambiario volátil (Venezuela), necesita tasas reales |

---

## Módulos Implementados (6 Ejes de Análisis)

### Eje 1: Performance Comercial
- KPIs consolidados: ventas, premios, margen bruto, agencias activas
- Tendencias mensuales con desglose por moneda
- Rankings de top productos y agencias
- **Impacto:** Visibilidad completa del negocio en un solo dashboard

### Eje 2: Detección de Anomalías
- Identificación del ratio de anulación anómalo: **148M bets anuladas vs 112M activas (1.3x)**
- Ranking de agencias con tasa de anulación sospechosa (>30%)
- Análisis de patrones por rol (quién anula, cuándo, por qué)
- **Impacto:** Red flag crítica descubierta — posible fraude o bug técnico

### Eje 3: Health Score de Agencias
- Fórmula compuesta (0-100): ventas (40pts) + margen (30pts) + actividad (20pts) - anulaciones (10pts)
- Scatter plot ventas vs margen para segmentación visual
- Tabla buscable con 5,474 agencias rankeadas
- **Impacto:** Priorización de agencias para intervención o incentivo

### Eje 4: Análisis de Productos
- Participación por tipo: Animalitos, Triples, Terminales, Tripletas, Centenas/Zoo
- Evolución temporal de cada tipo de producto
- Rankings de sorteos por volumen y margen
- **Impacto:** Decisiones de catálogo basadas en datos

### Eje 5: Gestión de Riesgo
- Payout ratio por producto y por mes
- Números más apostados con correlación de premios
- Análisis de exposure máxima por cuota
- **Impacto:** Calibración de cuotas basada en comportamiento real

### Eje 6: Monitoreo de Proveedores
- Distribución de volumen por proveedor (7 activos)
- Tasas de fallo por proveedor (logs de 744K llamadas API)
- Evolución mensual de cada proveedor
- **Impacto:** SLA de proveedores y decisiones de dependencia

---

## Hallazgos Técnicos Destacados

### 1. Ratio de Anulación Anómalo (1.3x)
Se descubrieron **148 millones de apuestas anuladas frente a 112 millones activas**. Un ratio >1x es inusual en la industria de loterías. Posibles causas investigadas:
- Reintentos fallidos de proveedores externos
- UX que genera anulaciones accidentales
- Potencial fraude interno

### 2. Crecimiento 37x en 5 meses
La plataforma pasó de 184K a 6.8M tickets mensuales, requiriendo:
- ETL optimizado con particionado por mes
- DuckDB como motor de queries (evita OOM con Pandas)
- Pre-agregación de tablas fact para el dashboard

### 3. Multi-Currency con Tasas en Tiempo Real
Integración con API del BCV (Banco Central de Venezuela) y open.er-api.com para conversión cruzada de 5 monedas, con fallback a caché local cuando las APIs no responden.

### 4. Health Score como Métrica Compuesta
Diseño de fórmula de scoring (0-100) que pondera volumen, margen, actividad y anulaciones para ranquear 5,474 agencias en una sola métrica accionable.

---

## Resultados y Entregables

| Entregable | Estado | Detalle |
|---|---|---|
| Pipeline ETL automatizado | ✅ Completo | Extractores para facts, dimensions, providers, aggregated |
| Dashboard interactivo (6 páginas) | ✅ Completo | Streamlit con autenticación, filtros multi-moneda |
| Data Lake en Parquet | ✅ Completo | ~3GB de datos estructurados (vs ~15GB en CSV) |
| Docker deployment | ✅ Completo | Container con Nginx reverse proxy |
| Documentación técnica | ✅ Completo | README, propuesta, arquitectura |
| Detección de anomalías | ✅ Completo | Red flag de ratio 1.3x identificada |
| Health scoring de agencias | ✅ Completo | 5,474 agencias rankeadas |

---

## Competencias Demostradas

### Data Engineering
- Diseño de ETL pipeline con particionado temporal
- Optimización de queries analíticas (DuckDB + Parquet)
- Manejo de datasets de 100M+ registros
- Multi-currency conversion con APIs externas

### Data Analysis
- Detección de anomalías en datos transaccionales
- Diseño de métricas compuestas (health scoring)
- Análisis de crecimiento y tendencias
- Investigación de red flags operativas

### Full-Stack Development
- Dashboard interactivo con 6 módulos de análisis
- Autenticación segura (cookie-based, 30-day persistence)
- Visualizaciones interactivas con Plotly
- Responsive design con filtros dinámicos

### DevOps
- Docker multi-stage builds
- Nginx reverse proxy con WebSocket support
- Deployment automatizado en VPS
- Gestión de secrets y variables de entorno

### Business Intelligence
- Comprensión de modelo de negocio de loterías
- Análisis de riesgo financiero (payout ratios)
- Segmentación de red de agencias
- Monitoreo de SLA de proveedores

---

## Tecnologías y Herramientas

```
Python 3.12 · PostgreSQL · DuckDB · Parquet · Streamlit · Plotly
SQLAlchemy · Pandas · scikit-learn · Docker · Nginx · uv
Git · Linux · REST APIs · Data Modeling · ETL Design
```

---

## Contexto para el CV / LinkedIn

### Versión corta (1-2 líneas)
> Plataforma de análisis de datos para operaciones de loterías a escala nacional: ETL pipeline sobre 112M+ registros, dashboard interactivo con 6 módulos de análisis, detección de anomalías y scoring de 5,474 agencias.

### Versión media (párrafo)
> Diseñé e implementé una plataforma completa de data analytics para PremierPluss, operador de loterías con 5,474 agencias y 112 millones de apuestas procesadas. El sistema incluye un pipeline ETL (PostgreSQL → Parquet), motor de queries DuckDB, y dashboard Streamlit con 6 módulos: performance comercial, detección de anomalías, health scoring de agencias, análisis de productos, gestión de riesgo y monitoreo de proveedores. Descubrí una anomalía crítica (ratio de anulación 1.3x) que requirió investigación inmediata. La plataforma maneja multi-currency (5 monedas) con tasas de cambio en tiempo real.

### Versión extendida (bullet points)
- **Pipeline ETL:** Diseñé extractores Python que procesan 112M+ bets y 24M+ tickets desde PostgreSQL, almacenando en Parquet particionado por mes con compresión 6:1 vs CSV
- **Motor analítico:** Implementé DuckDB como query engine sobre Parquet, logrando tiempos de respuesta <500ms en datasets de 50M+ filas sin cargar en memoria
- **Dashboard interactivo:** Construí 6 páginas en Streamlit (Performance, Anomalías, Agencias, Productos, Riesgo, Proveedores) con autenticación segura y filtros multi-moneda
- **Detección de anomalías:** Identifiqué ratio de anulación anómalo de 1.3x (148M anuladas vs 112M activas), señal crítica de posible fraude o bug técnico
- **Health scoring:** Diseñé fórmula compuesta (0-100) para ranquear 5,474 agencias según ventas, margen, actividad y anulaciones
- **Multi-currency:** Integré APIs del BCV y forex para conversión en tiempo real de VES, USD, BRL, PEN, COP
- **DevOps:** Containericé con Docker + Nginx reverse proxy con WebSocket support para deployment en VPS
- **Crecimiento:** Soporté escalamiento de 37x en 5 meses (184K → 6.8M tickets/mes)
