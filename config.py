# config.py — konfigurasi aplikasi dari environment variable.
# Semua punya default dev agar `python app.py` langsung jalan tanpa setup.
# Untuk produksi WAJIB set ulang via env (lihat docs/architecture.md).

import os

# Lokasi root proyek (folder file ini berada).
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    # Password halaman /admin (1 password bersama, belum ada tabel user).
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin-dev")

    # Token yang disisipkan ke /form dan divalidasi di POST /api/submit.
    SUBMIT_TOKEN = os.environ.get("SUBMIT_TOKEN", "dev-submit-token")

    # Lokasi file SQLite. Default: data/inventory.db di dalam proyek.
    DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "data", "inventory.db"))

    # Secret key untuk Flask session (login admin). WAJIB diganti di produksi.
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-ganti-di-produksi")

    # URL publik server (untuk link unduh collector & menyusun URL /form).
    SERVER_BASE_URL = os.environ.get("SERVER_BASE_URL", "http://127.0.0.1:8080")


config = Config()
