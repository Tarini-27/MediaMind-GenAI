"""Create (and optionally reset) the library database.
    python scripts/init_db.py            # create tables, seed demo data if empty
    python scripts/init_db.py --reset    # delete the DB file first, then recreate and seed
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mediamind import db  # noqa: E402

if "--reset" in sys.argv and db.db_path().exists():
    db.db_path().unlink()
    print(f"deleted {db.db_path()}")

db.init_db()
with db.connect() as c:
    counts = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("users", "items", "collections", "proposals")}
print(f"database ready at {db.db_path()}  {counts}")
