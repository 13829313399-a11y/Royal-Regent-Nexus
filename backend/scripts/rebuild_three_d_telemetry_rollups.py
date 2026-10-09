"""Initialize derived hourly analytics after migration and the new writer deploy.

Run from backend: python scripts/rebuild_three_d_telemetry_rollups.py --apply
Original device events and business records are never modified.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import engine
from app.services.three_d_telemetry_rollups import initialize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", required=True)
    parser.parse_args()
    count = initialize(engine, progress=lambda done, total: print(
        json.dumps({"completed_hours": done, "total_hours": total}), flush=True,
    ))
    print(json.dumps({"initialized": True, "rebuilt_hours": count}), flush=True)


if __name__ == "__main__":
    main()
