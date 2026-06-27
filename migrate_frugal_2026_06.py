# migrate_frugal_2026_06.py — eksekusi revisi "Standar Frugal" (sekali jalan).
#
# Menerapkan docs/scoring-revisi-2026-06.md §D ke DB yang sudah ada:
#   1) cpu_benchmarks  : bersihkan baris lama (termasuk "seed massal" tertebak)
#                        lalu reseed dari data/cpu_seed.csv yang sudah dibangun
#                        ulang dari PassMark resmi (lihat rebuild_cpu_seed.py).
#   2) work_groups +
#      scoring_settings: tulis-paksa DEFAULT frugal baru (profil/bobot per
#                        kelompok + status_upgrade_min 35). MENIMPA baris lama
#                        (scoring_config.reseed_defaults).
#   3) submissions     : "Hitung ulang semua" — re-score tiap submission dengan
#                        parameter + data CPU baru (identik tombol admin).
#
# Idempoten & aman diulang. Cadangkan DB dulu (data/inventory.db.pre-frugal-bak
# sudah dibuat). Jalankan: python migrate_frugal_2026_06.py

import sqlite3

import db
import scoring_config
from config import config
from routes_admin import _rescore_fields
from seed_cpu import _CREATE_TABLE_SQL, seed_from_csv


def reseed_cpu(db_path):
    """Kosongkan cpu_benchmarks lalu isi ulang dari cpu_seed.csv (buang stale)."""
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(_CREATE_TABLE_SQL)
        before = conn.execute("SELECT COUNT(*) FROM cpu_benchmarks").fetchone()[0]
        conn.execute("DELETE FROM cpu_benchmarks")
        conn.commit()
    finally:
        conn.close()
    after = seed_from_csv(db_path)
    return before, after


def reseed_params(db_path):
    """Tulis-paksa work_groups + scoring_settings ke DEFAULT frugal."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        scoring_config.reseed_defaults(conn)
    finally:
        conn.close()


def recalc_all():
    """Re-score seluruh submission (identik tombol 'Hitung ulang semua')."""
    n = 0
    for s in db.all_submissions():
        db.update_submission(s["id"], _rescore_fields(s))
        n += 1
    return n


def main():
    path = config.DB_PATH
    print(f"DB target: {path}\n")

    before, after = reseed_cpu(path)
    print(f"[1/3] cpu_benchmarks: {before} baris lama -> {after} baris (PassMark resmi).")

    reseed_params(path)
    print(f"[2/3] work_groups + scoring_settings: DEFAULT frugal ditulis-paksa.")

    n = recalc_all()
    print(f"[3/3] submissions: {n} baris dihitung ulang sesuai parameter baru.")
    print("\nSelesai. Revisi Standar Frugal 2026-06 diterapkan.")


if __name__ == "__main__":
    main()
