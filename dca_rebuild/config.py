import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

LOCAL_DATABASE_PATH = DATA_DIR / "dca_local.db"

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{LOCAL_DATABASE_PATH}",
)

# SQLAlchemy requires postgresql:// rather than
# Render's occasional legacy postgres:// prefix.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://",
        "postgresql://",
        1,
    )
