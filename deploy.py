# deploy.py - skrip migrasi & deploy SATU LANGKAH (aman untuk produksi).
#
# Jalankan SEKALI setiap kali deploy versi baru. Aman & idempoten:
#   1. Backup DB ke data/inventory.db.deploy-YYYYMMDD-HHMMSS.bak (timestamp).
#   2. Catat jumlah baris SEBELUM (submissions/devices/employees).
#   3. Jalankan db.init_db():
#        - buat/seed tabel work_groups + scoring_settings (nilai default),
#        - rebuild aman submissions untuk melepas CHECK work_group lama
#          (kelompok kerja kini data-driven) - salin semua baris + verifikasi.
#   4. Catat jumlah baris SESUDAH lalu VERIFIKASI sama. Bila beda -> GAGAL keras
#      (data lama tetap utuh; pulihkan dari backup).
#   5. (opsional --recalc) Hitung ulang skor SEMUA submission sesuai parameter
#      terbaru - pakai bila kamu sudah mengubah angka di /admin/skoring.
#
# Pemakaian:
#   python deploy.py            # migrasi + verifikasi (TIDAK menyentuh skor)
#   python deploy.py --recalc   # migrasi + hitung ulang semua skor
#
# Catatan: tidak interaktif (cocok untuk server). Tidak melakukan git pull /
# restart gunicorn - itu langkah di luar (lihat akhir output).

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime

# Konsol Windows kadang cp1252 -> paksa UTF-8 bila bisa (output ASCII saja juga aman).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from config import config
import db


def _counts(path):
    """Jumlah baris tabel inti; {} bila DB belum ada."""
    if not os.path.exists(path):
        return {}
    conn = sqlite3.connect(path)
    try:
        out = {}
        for t in ("submissions", "devices", "employees"):
            try:
                out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except sqlite3.Error:
                out[t] = None  # tabel belum ada (DB fresh)
        return out
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(description="Migrasi & deploy online-device-inventory")
    ap.add_argument("--recalc", action="store_true",
                    help="Hitung ulang skor SEMUA submission setelah migrasi")
    args = ap.parse_args()

    db_path = config.DB_PATH
    print("=" * 64)
    print(" DEPLOY / MIGRASI - online-device-inventory")
    print("=" * 64)
    print(f" DB target : {db_path}")

    # 1. Backup manual bertstempel waktu (selain .bak otomatis dari init_db).
    if os.path.exists(db_path):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = f"{db_path}.deploy-{stamp}.bak"
        shutil.copy2(db_path, backup)
        print(f" Backup    : {backup}")
    else:
        print(" Backup    : (DB belum ada - akan dibuat baru)")

    # 2. Hitung baris SEBELUM.
    before = _counts(db_path)
    print(f" Sebelum   : {before or '(DB baru)'}")

    # 3. Migrasi (buat/seed tabel + rebuild aman lepas CHECK work_group).
    print(" Menjalankan migrasi (init_db)...")
    try:
        db.init_db()
    except Exception as exc:  # noqa: BLE001
        print(f"\n GAGAL migrasi: {exc}", file=sys.stderr)
        print(" Data lama TIDAK diubah. Pulihkan dari backup bila perlu.", file=sys.stderr)
        sys.exit(1)

    # 4. Verifikasi jumlah baris submissions tidak berubah.
    after = _counts(db_path)
    print(f" Sesudah   : {after}")
    if before.get("submissions") not in (None,) and before:
        if after.get("submissions") != before.get("submissions"):
            print("\n [GAGAL] VERIFIKASI GAGAL: jumlah submission berubah! "
                  f"({before.get('submissions')} -> {after.get('submissions')}). "
                  "Pulihkan dari backup.", file=sys.stderr)
            sys.exit(2)
    print(" [OK] Verifikasi baris: jumlah submission utuh.")

    # Ringkas kelompok & ambang hasil seed.
    import scoring_config
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        grp = [r["key"] for r in conn.execute(
            "SELECT key FROM work_groups ORDER BY sort_order").fetchall()]
        elig = conn.execute(
            "SELECT value FROM scoring_settings WHERE key='status_eligible_min'"
        ).fetchone()
    finally:
        conn.close()
    print(f" Kelompok  : {', '.join(grp)}")
    print(f" Ambang Layak >= {elig[0] if elig else '?'}")

    # 5. Opsional: hitung ulang skor semua submission (parameter terbaru).
    if args.recalc:
        print(" Menghitung ulang skor semua submission...")
        from flask import Flask
        fa = Flask(__name__)
        with fa.app_context():
            from routes_admin import _rescore_fields
            n = 0
            for s in db.all_submissions():
                db.update_submission(s["id"], _rescore_fields(s))
                n += 1
            db.get_db().close()
        print(f" [OK] {n} skor diperbarui.")
    else:
        print(" (Skor tidak disentuh. Jalankan ulang dgn --recalc bila perlu,")
        print("  atau klik 'Hitung ulang semua' di /admin/skoring.)")

    print("-" * 64)
    print(" [SELESAI] SELESAI. Langkah berikutnya:")
    print("   1) Restart WSGI (mis. systemctl restart <service-gunicorn>)")
    print("   2) Login /admin -> kalibrasi kelompok baru di /admin/skoring")
    print("   3) Bila ubah parameter -> 'Hitung ulang semua'")
    print("=" * 64)


if __name__ == "__main__":
    main()
