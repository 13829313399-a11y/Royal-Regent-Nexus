"""Idempotently remove expired private uploads, never attached message files."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db import SessionLocal
from app.services.collaboration.assets import cleanup

if __name__ == "__main__":
    with SessionLocal() as db:
        print(cleanup(db))
