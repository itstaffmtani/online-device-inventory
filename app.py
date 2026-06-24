# app.py — entry point Flask (app-factory).
#
# Tanggung jawab Sesi 1:
#   - create_app() factory: muat config, init DB, register blueprint.
#   - init_db() saat start agar file SQLite + tabel siap.
#   - Register public_bp (form/submit/unduh) & admin_bp (dashboard/export).
#
# Catatan: endpoint lama /api/diagnostik dan semua kode Google Apps Script /
# ekspor PDF-CSV berbasis spek server SUDAH DIHAPUS. Deteksi spek kini dilakukan
# collector di laptop karyawan (lihat docs/architecture.md).

from flask import Flask

import db
from config import config
from routes_admin import admin_bp
from routes_public import public_bp


def create_app():
    """Buat & konfigurasi instance Flask."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["SERVER_BASE_URL"] = config.SERVER_BASE_URL
    app.config["SUBMIT_TOKEN"] = config.SUBMIT_TOKEN
    app.config["ADMIN_PASSWORD"] = config.ADMIN_PASSWORD
    app.config["DB_PATH"] = config.DB_PATH

    # Daftarkan teardown koneksi DB per-request + buat tabel bila belum ada.
    db.init_app(app)
    db.init_db()

    # Seed tabel cpu_benchmarks (idempoten) agar scoring punya acuan PassMark.
    # Defensif: bila modul/seed belum lengkap, scoring tetap jalan via fallback CSV.
    try:
        from scoring import seed_cpu_benchmarks
        seed_cpu_benchmarks()
    except Exception as exc:  # noqa: BLE001
        app.logger.warning("Lewati seed cpu_benchmarks: %s", exc)

    # Register blueprint.
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=True)
