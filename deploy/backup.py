"""Sichert Datenbank (konsistent per SQLite-Backup-API) und Bilder nach DATA_DIR/backup/JJJJ-MM-TT.
Behält die letzten 14 Sicherungen."""
import datetime
import os
import pathlib
import shutil
import sqlite3

KEEP = 14
data = pathlib.Path(os.environ.get("DATA_DIR", "/var/lib/spendenlauf"))
root = data / "backup"
db_file = os.environ.get("DATABASE_FILE", "spendenlauf.db")
target = root / datetime.date.today().isoformat()
target.mkdir(parents=True, exist_ok=True)

src = sqlite3.connect(data / db_file)
dst = sqlite3.connect(target / db_file)
with dst:
    src.backup(dst)
dst.close()
src.close()

if (data / "uploads").exists():
    shutil.copytree(data / "uploads", target / "uploads", dirs_exist_ok=True)

for old in sorted(p for p in root.iterdir() if p.is_dir())[:-KEEP]:
    shutil.rmtree(old)
print(f"Sicherung erstellt: {target}")
