# PremierPluss Analytics

Full-stack data platform for lottery operations: ETL pipeline (PostgreSQL → Parquet), DuckDB query engine, and Streamlit dashboard with multi-currency support, agency health scoring, and anomaly detection.

## Features

- **8 analysis pages**: Performance, Anomalies, Agencies, Products, Providers, Risk metrics, Chat, Executive Report
- **Predictive ML pipeline**: Clustering, anomaly detection, forecasting, churn risk, market basket (optional)
- **Hybrid business chat**: Curated DuckDB views + safe read-only PostgreSQL access for complex questions
- **Multi-currency support**: VES, USD, BRL, PEN, COP with real-time BCV exchange rates
- **Health scoring**: Composite metric (sales + margin + activity + annulment) for agency ranking
- **Dynamic filtering**: Per-currency or unified "Todas (en Bs.)" conversion
- **Real-time data**: DuckDB queries over Parquet files (no pandas loading overhead)
- **Secure auth**: Cookie-based login (streamlit-authenticator, 30-day persistence)
- **Docker-ready**: Production deployment on VPS with Nginx reverse proxy

## Stack

- **Backend**: Python 3.12, FastAPI-free (SQLAlchemy for ETL)
- **Data**: PostgreSQL (source) → Parquet (facts/dimensions) → DuckDB (queries)
- **Frontend**: Streamlit (pages), Plotly (charts)
- **DevOps**: Docker, Nginx, uv (package manager)

## Local Setup

```bash
# Clone + install
git clone <repo>
cd lottery-analytics-dashboard
uv sync

# Create .env
cat > .env <<EOF
DATABASE_URL=postgresql://user:pass@host:5432/dbname
DATA_DIR=./data
EOF

# Extract data (if credentials available)
uv run python -m etl.extractors.facts
uv run python -m etl.extractors.dimensions
uv run python -m etl.extractors.providers

# Optional: install ML + LLM extras
uv sync --extra ml --extra llm

# Run predictive pipeline (generates data/predictions/*.parquet)
uv run python -m ml.run_all

# Run dashboard
uv run streamlit run dashboard/app.py
```

Navigate to `http://localhost:8501`. Login with password configured in `.streamlit/secrets.toml`.

## Pages

1. **📈 Performance** — KPIs, monthly trends, top products/agencies, forecast overlay
2. **🔍 Anomalies** — Annulment patterns, suspicious agencies (>30%), ML outlier detection + LLM narrative
3. **🏪 Agencies** — Health scores, scatter (sales vs margin), searchable table, clustering + churn risk
4. **🎰 Products** — Type participation, product evolution, draw details
5. **🌐 Providers** — Volume, failure rates, monthly evolution
6. **⚠️ Risk** — Payout ratios, most-bet numbers
7. **💬 Chat** — Conversational analytics with SQL guardrails or offline catalog
8. **📊 Reporte Ejecutivo** — Monthly CEO report (LLM-enhanced or offline)

## Docker Deployment

```bash
# Build + run on VPS
docker compose up -d --build

# Access via nginx
curl http://<vps-ip>
```

Nginx proxy handles WebSocket upgrades (required by Streamlit). For SSL, mount certificates to `./ssl/`.

## Project Structure

```
.
├── dashboard/
│   ├── pages/           # 8 Streamlit pages
│   ├── llm/             # OpenRouter client, chat, narrative, audit
│   ├── auth.py          # Shared auth module
│   ├── data.py          # DuckDB queries (unified + per-currency) + prediction loaders
│   ├── rates.py         # BCV API + forex caching
│   ├── utils.py         # fmt_money(), fmt_table()
│   ├── app.py           # Entry point
│   └── .streamlit/      # Secrets + config
├── etl/
│   ├── config.py        # DB connection + paths
│   ├── logger.py        # Structured logging
│   └── extractors/
│       ├── facts.py     # Tickets + bets (monthly Parquet)
│       ├── dimensions.py # Agencies, products, lotteries
│       └── providers.py  # External provider data
├── ml/
│   ├── run_all.py       # Batch orchestrator (5 pipelines)
│   ├── features.py      # Feature engineering for each model
│   ├── train_*.py       # Individual pipelines: clustering, anomaly, forecast, churn, basket
│   ├── schemas.py       # Output schemas + validation
│   └── config.py        # Paths, thresholds, OpenRouter settings
├── data/
│   ├── facts/           # Fact tables (bets_*.parquet, tickets_*.parquet)
│   ├── dimensions/      # Dimension tables (agencys, products, lotteries)
│   ├── aggregated/      # Pre-aggregated (sales_by_agency, sales_by_loteries)
│   ├── predictions/     # ML outputs (*.parquet)
│   ├── reports/         # Generated markdown reports
│   └── cache/           # LLM disk cache
├── Dockerfile           # Python 3.12-slim, uv-based build
├── docker-compose.yml   # Dashboard + Nginx services
├── nginx.conf           # WebSocket-aware reverse proxy
├── pyproject.toml       # Dependencies (optional extras: ml, llm)
└── README.md
```

## ML / Predictive Pipeline

Optional batch pipeline (`uv sync --extra ml`) that generates 5 prediction datasets:

| Pipeline | Model | Output | Description |
|----------|-------|--------|-------------|
| Clustering | KMeans + PCA | `agency_clusters.parquet` | Segments agencies by behavior |
| Anomaly Detection | IsolationForest | `anomaly_scores.parquet` | Flags multivariate outliers |
| Forecasting | Prophet / SARIMAX | `forecast_sales.parquet` | 3-month sales projection |
| Churn Risk | RandomForest | `agency_churn_risk.parquet` | Probability of 30-day inactivity |
| Market Basket | FP-Growth | `basket_rules.parquet` | Product association rules |

Run the full pipeline:
```bash
uv run python -m ml.run_all
```

Logs are written to `logs/ml_run_*.log`. Each stage is independent; partial failures do not block the rest.

### Known Limitations
- **Churn leakage**: when `churn_days=30`, the feature `monetary_30d` overlaps with the label window, inflating holdout accuracy. This is documented as a known artifact; for rigorous training, exclude `monetary_30d` or increase `churn_days`.
- **Monthly forecasts require complete months**: the forecasting pipeline now excludes incomplete trailing months before training. If your latest month is partial, the next-month forecast will anchor on the last complete month instead.

## LLM / Chat & Reports

Optional OpenRouter integration (`uv sync --extra llm`) powers:
- **Chat Assistant** (page 7): SQL-validated queries or offline catalog fallback
- **Anomaly Narrative**: Per-agency executive explanation
- **Executive Report** (page 8): Monthly CEO markdown report

### Chat capabilities

The chat now uses a **hybrid retrieval model**:

1. **Curated DuckDB views over Parquet** for fast, safe dashboard-style questions.
2. **Read-only PostgreSQL local access** (encapsulated in safe functions) for deeper business questions.

Examples it can answer:

- "¿Qué producto vendió más?"
- "¿A qué grupo pertenece esta agencia?"
- "¿Cuáles números han salido más en La Granjita 07:00 PM?"
- "¿Cuáles números apuestan más los usuarios en La Granjita 07:00 PM?"
- "¿Cuál fue la diferencia de ventas de febrero y marzo de GANALOTERIAS INT?"
- "¿Cuánto vendió La Granjita en marzo?"

### Conversational memory

The chat keeps **structured conversational memory** during the session so follow-up questions do not need to restate the full subject every time.

It can preserve, when confidently inferred:

- active entity (`agency`, `product`, `lottery`, etc.)
- lottery hour / draw slot
- referenced months
- metric or intent (`sales`, `difference`, `forecast`, `most-bet numbers`, etc.)

This enables follow-ups like:

- "¿Cuál es la agencia que lidera las ventas?" → "¿cuánto vende?" → "¿y en febrero vs marzo?"
- "La Granjita 07:00 PM" → "¿y ese horario cuánto mueve?"

### Read-only PostgreSQL business layer

For complex queries, the chat does **not** expose free SQL over PostgreSQL to the LLM. Instead, it uses safe query helpers and controlled matching logic.

See:

- `dashboard/db_local.py`
- `docs/DB_LOCAL_READONLY_GUIDE.md`

Configure in `.env`:
```bash
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=google/gemini-flash-1.5
LLM_ENABLED=true
```

If the key is missing, the dashboard degrades gracefully to offline mode with structured data summaries.

## Key Concepts

### Health Score
Agencies ranked 0–100 by weighted formula:
- **40pts** — Sales volume (relative to max)
- **30pts** — Margin % (clamped [0, 30])
- **20pts** — Days active (divided by 180)
- **10pts** — Annulment penalty

### Currency Conversion
- VES (moneda_id=1, currency_id=1): 1.0x
- USD (2): BCV API real-time rate
- BRL, PEN, COP (3-5): Cross rates via open.er-api.com

"Todas (en Bs.)" converts all currencies to VES using `CASE WHEN moneda_id/currency_id = X THEN amount * rate`.

### Data Pipeline
1. **Extract**: Daily partitions (`bets_YYYYMMDD`, `tickets_YYYYMMDD`) → monthly Parquet
2. **Aggregate**: Pre-computed fact tables (`sales_by_agency`, `sales_by_loteries`) for dashboard speed
3. **Query**: DuckDB over Parquet, no pandas loading (billions of rows → milliseconds)

## License

MIT — code is open source. **Data (`data/`) is NOT included** — it's proprietary PremierPluss data. See `.gitignore`.

## Notes

- Auth password: configured in `.streamlit/secrets.toml` (not committed)
- Dashboard caches Streamlit functions (KPIs, rates) with configurable TTL
- ETL uses fresh DB connection per daily partition (avoids timeout on large months)
- Parquet queries scale: 5M+ agency rows, 50M+ bet rows, <500ms response times
