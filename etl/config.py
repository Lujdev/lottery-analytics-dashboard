from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

DB_URL = (
    f"postgresql+psycopg2://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}"
    f"@{os.environ['DB_HOST']}:{os.environ.get('DB_PORT', '5432')}/{os.environ['DB_NAME']}"
)

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
(DATA_DIR / "dimensions").mkdir(exist_ok=True)
(DATA_DIR / "aggregated").mkdir(exist_ok=True)
(DATA_DIR / "facts").mkdir(exist_ok=True)
