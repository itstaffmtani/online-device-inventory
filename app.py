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

from datetime import datetime

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

import db
from config import config
from routes_admin import admin_bp
from routes_public import public_bp

_BULAN_ID = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
             "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def _fmt_dt(value, with_time=True):
    """Format timestamp ISO -> '24 Jun 2026, 17:14' (gaya Indonesia)."""
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return str(value)
    s = f"{dt.day} {_BULAN_ID[dt.month - 1]} {dt.year}"
    if with_time:
        s += f", {dt.hour:02d}:{dt.minute:02d}"
    return s


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

    # Filter Jinja: format timestamp gaya Indonesia.
    app.jinja_env.filters["fmt_dt"] = _fmt_dt

    # Global Jinja: icon('nama', 'kelas') -> markup <svg> Heroicons dari registry
    # tunggal (icons.py). Hentikan penyalinan SVG inline di banyak template.
    from icons import render_icon
    app.jinja_env.globals["icon"] = render_icon

    # Register blueprint.
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)

    # Hormati header dari reverse proxy (nginx): proto HTTPS + sub-path mount.
    # X-Forwarded-Prefix membuat url_for() & redirect ikut prefix (mis.
    # /laptop-inventory) saat app dipasang di sub-path. Tanpa proxy → no-op.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=True)
