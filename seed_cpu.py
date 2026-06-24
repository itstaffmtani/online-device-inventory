# seed_cpu.py — isi tabel cpu_benchmarks dari data/cpu_seed.csv.
#
# Mandiri: membuat tabel `cpu_benchmarks` sendiri (CREATE TABLE IF NOT EXISTS,
# kolom sesuai docs/schema.dbml) lalu UPSERT baris dari CSV. Idempoten — aman
# dijalankan berulang (ON CONFLICT(cpu_key) -> REPLACE).
#
# Jalankan: python seed_cpu.py
# DB target: DB_PATH (default data/inventory.db). Folder data/ dibuat bila perlu.

import csv
import os
import sqlite3

try:
    from config import config
    DEFAULT_DB_PATH = config.DB_PATH
except Exception:  # config belum ada (Sesi 1 belum jalan) -> default mandiri.
    _BASE = os.path.dirname(os.path.abspath(__file__))
    DEFAULT_DB_PATH = os.environ.get("DB_PATH", os.path.join(_BASE, "data", "inventory.db"))

CPU_SEED_CSV = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "cpu_seed.csv"
)

# Skema cpu_benchmarks sesuai docs/schema.dbml.
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS cpu_benchmarks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cpu_key         TEXT UNIQUE,
    cpu_label       TEXT,
    passmark_multi  INTEGER,
    passmark_single INTEGER,
    cores           INTEGER,
    release_year    INTEGER,
    source          TEXT
)
"""

_UPSERT_SQL = """
INSERT INTO cpu_benchmarks
    (cpu_key, cpu_label, passmark_multi, passmark_single, cores, release_year, source)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(cpu_key) DO UPDATE SET
    cpu_label       = excluded.cpu_label,
    passmark_multi  = excluded.passmark_multi,
    passmark_single = excluded.passmark_single,
    cores           = excluded.cores,
    release_year    = excluded.release_year,
    source          = excluded.source
"""


def _to_int(v):
    """'' / None -> None; angka -> int."""
    if v is None:
        return None
    s = str(v).strip()
    if s == "":
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _read_csv_rows(csv_path):
    """Baca cpu_seed.csv -> list tuple siap di-UPSERT."""
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            cpu_key = (r.get("cpu_key") or "").strip().lower()
            if not cpu_key:
                continue
            rows.append((
                cpu_key,
                (r.get("cpu_label") or "").strip(),
                _to_int(r.get("passmark_multi")),
                _to_int(r.get("passmark_single")),
                _to_int(r.get("cores")),
                _to_int(r.get("release_year")),
                (r.get("source") or "").strip(),
            ))
    return rows


def seed_from_csv(db_path=None, csv_path=None):
    """Buat tabel cpu_benchmarks lalu UPSERT semua baris dari CSV.

    Return jumlah total baris di tabel setelah seed.
    """
    db_path = db_path or DEFAULT_DB_PATH
    csv_path = csv_path or CPU_SEED_CSV

    # Pastikan folder data/ ada (belum tentu dibuat oleh Sesi 1).
    parent = os.path.dirname(os.path.abspath(db_path))
    os.makedirs(parent, exist_ok=True)

    rows = _read_csv_rows(csv_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(_CREATE_TABLE_SQL)
        conn.executemany(_UPSERT_SQL, rows)
        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM cpu_benchmarks").fetchone()[0]
        return total
    finally:
        conn.close()


if __name__ == "__main__":
    db = DEFAULT_DB_PATH
    total = seed_from_csv(db)
    print(f"Seed cpu_benchmarks selesai.")
    print(f"  DB   : {db}")
    print(f"  CSV  : {CPU_SEED_CSV}")
    print(f"  Total baris cpu_benchmarks: {total}")
