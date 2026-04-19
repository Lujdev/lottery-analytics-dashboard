# PremierPluss Analytics

Full-stack data platform for lottery operations: ETL pipeline (PostgreSQL → Parquet), DuckDB query engine, and Streamlit dashboard with multi-currency support, agency health scoring, and anomaly detection.

## Features

- **6 analysis pages**: Performance, Anomalies, Agencies, Products, Providers, Risk metrics
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

# Run dashboard
uv run streamlit run dashboard/app.py
```

Navigate to `http://localhost:8501`. Login with password: `***REMOVED***`

## Pages

1. **📈 Performance** — KPIs, monthly trends, top products/agencies
2. **🔍 Anomalies** — Annulment patterns, suspicious agencies (>30%)
3. **🏪 Agencies** — Health scores, scatter (sales vs margin), searchable table
4. **🎰 Products** — Type participation, product evolution, draw details
5. **🌐 Providers** — Volume, failure rates, monthly evolution
6. **⚠️ Risk** — Payout ratios, most-bet numbers

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
│   ├── pages/           # 6 Streamlit pages
│   ├── auth.py          # Shared auth module
│   ├── data.py          # DuckDB queries (unified + per-currency)
│   ├── rates.py         # BCV API + forex caching
│   ├── utils.py         # fmt_money(), fmt_table()
│   ├── app.py           # Entry point
│   └── .streamlit/       # Secrets + config
├── etl/
│   ├── config.py        # DB connection + paths
│   ├── logger.py        # Structured logging
│   └── extractors/
│       ├── facts.py     # Tickets + bets (monthly Parquet)
│       ├── dimensions.py # Agencies, products, lotteries
│       └── providers.py  # External provider data
├── data/
│   ├── facts/           # Fact tables (bets_*.parquet, tickets_*.parquet)
│   ├── dimensions/      # Dimension tables (agencys, products, lotteries)
│   └── aggregated/      # Pre-aggregated (sales_by_agency, sales_by_loteries)
├── Dockerfile           # Python 3.12-slim, uv-based build
├── docker-compose.yml   # Dashboard + Nginx services
├── nginx.conf           # WebSocket-aware reverse proxy
├── pyproject.toml       # Dependencies
└── README.md
```

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

- Auth password: `***REMOVED***` (configured in `.streamlit/secrets.toml`)
- Dashboard caches Streamlit functions (KPIs, rates) with configurable TTL
- ETL uses fresh DB connection per daily partition (avoids timeout on large months)
- Parquet queries scale: 5M+ agency rows, 50M+ bet rows, <500ms response times

