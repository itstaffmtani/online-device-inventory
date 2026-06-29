# migrate_kelompok_2026_06.py — revisi kelompok kerja & profil pada DB yang ADA.
#
# ensure_tables() (INSERT OR IGNORE) hanya bisa MENAMBAH, tak bisa menghapus/mengubah
# baris lama. Perubahan kategori berikut karena itu dilakukan di sini. Idempoten —
# aman dijalankan berulang & di tiap environment (dev/prod).
#
# Perubahan:
#   1. 'marketing' (Marketing/Sales) -> 'rpo' (RPO), profil 'lapangan'.
#   2. tambah 'mandor' (Mandor) -> profil 'lapangan'.
#   3. gabung profil: 'data_processing' pindah ke profil 'keuangan' (angka Keuangan),
#      profil 'keuangan' di-relabel "Keuangan & Data", profil 'olah_data' dihapus.
#      (Excel banyak baris = RAM-bound; CPU modest karena tanpa Power Query.)
#      Label departemen Keuangan & Pengolahan Data tetap utuh untuk laporan.
#
# Jalankan:  python migrate_kelompok_2026_06.py [path/ke/inventory.db]
# Lalu buka /admin/skoring -> "Hitung ulang semua".

import os
import sqlite3
import sys

import scoring_config


def migrate(conn):
    conn.row_factory = sqlite3.Row
    scoring_config.ensure_tables(conn)  # pastikan tabel + profil terbaru ada
    cur = conn.cursor()

    # 1) marketing -> rpo (work_group BUKAN FK, hanya TEXT; submission ikut dipindah).
    has_marketing = cur.execute("SELECT 1 FROM work_groups WHERE key='marketing'").fetchone()
    has_rpo = cur.execute("SELECT 1 FROM work_groups WHERE key='rpo'").fetchone()
    if has_marketing:
        cur.execute("UPDATE submissions SET work_group='rpo' WHERE work_group='marketing'")
        if has_rpo:
            cur.execute("DELETE FROM work_groups WHERE key='marketing'")
            print("• 'marketing' dihapus (rpo sudah ada).")
        else:
            cur.execute("UPDATE work_groups SET key='rpo', label='RPO', "
                        "profile_key='lapangan', sort_order=70 WHERE key='marketing'")
            print("• 'marketing' -> 'rpo' (profil lapangan).")
    else:
        print("• 'marketing' tidak ada (mungkin sudah dimigrasi).")

    # 2) mandor -> lapangan (mirror angka inline; kompat kolom NOT NULL DB lama).
    lap = dict(cur.execute("SELECT * FROM scoring_profiles WHERE key='lapangan'").fetchone())
    cur.execute(
        """INSERT OR IGNORE INTO work_groups
             (key, label, profile_key, sort_order, is_active, is_builtin,
              cpu_floor, cpu_ideal, ram_min, ram_ideal, w_cpu, w_ram, w_storage, w_battery)
           VALUES ('mandor','Mandor','lapangan',75,1,1, ?,?,?,?,?,?,?,?)""",
        (lap["cpu_floor"], lap["cpu_ideal"], lap["ram_min"], lap["ram_ideal"],
         lap["w_cpu"], lap["w_ram"], lap["w_storage"], lap["w_battery"]),
    )
    print("• 'mandor' dipastikan ada (profil lapangan).")

    # 3) gabung keuangan + pengolahan data ke profil 'keuangan'.
    cur.execute("UPDATE work_groups SET profile_key='keuangan' WHERE key='data_processing'")
    cur.execute("UPDATE scoring_profiles SET label='Keuangan & Data' WHERE key='keuangan'")
    cur.execute("DELETE FROM scoring_profiles WHERE key='olah_data'")
    print("• 'data_processing' -> profil 'keuangan'; profil 'olah_data' dihapus.")

    conn.commit()


if __name__ == "__main__":
    # Prioritas path DB: argumen CLI > env DB_PATH (sama dengan app) > default lokal.
    db_path = (sys.argv[1] if len(sys.argv) > 1
               else os.environ.get("DB_PATH") or os.path.join("data", "inventory.db"))
    print(f"DB: {db_path}")
    if not os.path.exists(db_path):
        sys.exit(f"DB tidak ditemukan: {db_path} "
                 "(beri path sebagai argumen, atau set env DB_PATH).")
    conn = sqlite3.connect(db_path)
    scoring_config._conn = lambda: conn
    migrate(conn)
    print("\nSelesai. Buka /admin/skoring lalu klik 'Hitung ulang semua'.")
