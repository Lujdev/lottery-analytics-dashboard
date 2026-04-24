# Guía de Operaciones — PremierPluss Analytics

> Documento vivo para equipos de ops, data y dev que operan el sistema.

## Dependencias opcionales

El core del dashboard funciona sin ML ni LLM. Los extras son opcionales:

```bash
# Solo dashboard + ETL
uv sync

# + Machine Learning (scikit-learn, Prophet, mlxtend)
uv sync --extra ml

# + LLM / OpenRouter (httpx, openai)
uv sync --extra llm

# Todo
uv sync --extra ml --extra llm
```

## Correr el pipeline predictivo

```bash
uv run python -m ml.run_all
```

Salida:
- `data/predictions/*.parquet` — datasets de cada modelo
- `logs/ml_run_*.log` — log de ejecución con resumen por etapa

El orquestador ejecuta 5 pipelines independientes. Si uno falla, los demás continúan.
El exit code es `0` solo si **todos** pasan.

### Variables de entorno útiles

```bash
ML_RUN_ID=manual-2026-04          # identificador personalizado de corrida
OPENROUTER_API_KEY=sk-or-v1-...   # requerido solo para LLM
OPENROUTER_MODEL=google/gemini-flash-1.5
LLM_ENABLED=true
```

## Archivos generados por el sistema

### Datos base (ETL)
| Ruta | Origen | Descripción |
|------|--------|-------------|
| `data/facts/tickets_YYYY-MM.parquet` | ETL | Tickets mensuales |
| `data/facts/bets_YYYY-MM.parquet` | ETL | Apuestas mensuales |
| `data/dimensions/*.parquet` | ETL | Agencias, productos, loterías |
| `data/aggregated/sales_by_agency.parquet` | ETL | Ventas agregadas por agencia-día |
| `data/aggregated/sales_by_loteries.parquet` | ETL | Ventas agregadas por sorteo-día |

### Predicciones (ML)
| Ruta | Pipeline | Contenido |
|------|----------|-----------|
| `data/predictions/agency_clusters.parquet` | Clustering | Segmentos KMeans + proyección PCA |
| `data/predictions/anomaly_scores.parquet` | Anomaly | Score IsolationForest + severidad |
| `data/predictions/forecast_sales.parquet` | Forecast | Pronóstico mensual (nacional + top agencias) |
| `data/predictions/agency_churn_risk.parquet` | Churn | Probabilidad de abandono + banda |
| `data/predictions/basket_rules.parquet` | Basket | Reglas de asociación antecedente → consecuente |

### Reportes y caché
| Ruta | Origen | Descripción |
|------|--------|-------------|
| `data/reports/executive_YYYY-MM.md` | Reporte Ejecutivo | Markdown mensual CEO-friendly |
| `data/cache/llm_cache.pkl` | Chat / Narrativa | Cache local de respuestas LLM |
| `logs/llm_YYYY-MM-DD.jsonl` | Auditoría LLM | Trazabilidad de cada llamada (hash de prompt/respuesta, tokens, latencia) |

## Configurar OpenRouter

1. Crear cuenta en https://openrouter.ai y generar API key.
2. Agregar a `.env`:
   ```bash
   OPENROUTER_API_KEY=sk-or-v1-...
   OPENROUTER_MODEL=google/gemini-flash-1.5
   LLM_ENABLED=true
   ```
3. Reiniciar Streamlit.

Sin API key, el dashboard opera en **modo offline**:
- Chat usa catálogo cerrado de funciones Python (sin SQL generado por LLM).
- Narrativa y reporte ejecutivo muestran resúmenes estructurados de datos crudos.

## Troubleshooting

### El dashboard no muestra predicciones
- Verificar que existan archivos en `data/predictions/`.
- Correr `uv run python -m ml.run_all`.
- Revisar `logs/ml_run_*.log` para ver qué etapa falló.

### Accuracy de churn = 1.0
- Esto es **esperado** con la configuración por defecto (`churn_days=30`).
- La feature `monetary_30d` comparte ventana con el label, produciendo leakage.
- No indica un bug de código; es una limitación documentada del dataset.
- Para entrenamiento riguroso, excluir `monetary_30d` o cambiar `churn_days`.

### Chat devuelve "Modo offline"
- `OPENROUTER_API_KEY` no está configurada o `LLM_ENABLED=false`.
- O la validación de seguridad bloqueó la pregunta (prompt injection / SQL prohibido).

### SQL sandboxed falla
- El chat solo permite `SELECT` sin DDL/DML.
- Funciones como `read_parquet`, `read_csv`, `COPY`, etc. están bloqueadas.
- Consultas > 2000 caracteres o con `;` son rechazadas.

### Prophet imprime mucho log
- Es verbosity de `cmdstanpy` al compilar modelos. Es inofensivo.
- Para silenciar, setear `CMDSTANPY_LOG_LEVEL=WARNING`.

## Límites operativos conocidos

- **Forecast**: requiere al menos 3 meses de historia (`MIN_MONTHS_FOR_FORECAST`).
- **Clustering**: requiere al menos `DEFAULT_K_CLUSTERS + 1` agencias.
- **Basket**: requiere al menos 100 tickets con 2+ productos distintos.
- **Anomalía**: entrena un modelo global transversal; no detecta drift temporal progresivo.
- **LLM**: sin rate limiting propio; OpenRouter puede devolver 429 en picos de uso.
