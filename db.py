# db.py — skema SQLite + akses data (KONTRAK Sesi 1, dipakai semua sesi).
#
# Skema mengikuti docs/schema.dbml persis. Enum DBML diwujudkan sebagai kolom
# TEXT + CHECK. Pencocokan device saat submission masuk:
#   serial_number -> asset_no -> primary_mac -> (tak ketemu) buat device baru.
#
# Fungsi publik (tanda tangan dikunci di docs/workflow-tasks.md):
#   init_db() -> None
#   get_db() -> sqlite3.Connection          (koneksi per-request)
#   find_or_create_device(serial, asset_no, mac, brand, model, os_family) -> int
#   insert_submission(data: dict) -> int
#   latest_per_device() -> list[dict]
#   device_with_history(device_id: int) -> dict   {device, submissions[]}

import os
import sqlite3

from flask import g

from config import config

# ---------------------------------------------------------------------------
# SKEMA
# ---------------------------------------------------------------------------
SCHEMA = """
PRAGMA foreign_keys = ON;

-- DEVICES: satu baris per laptop fisik (identitas hardware stabil).
CREATE TABLE IF NOT EXISTS devices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    serial_number   TEXT UNIQUE,
    asset_no        TEXT,
    primary_mac     TEXT,
    brand           TEXT,
    model           TEXT,
    os_family       TEXT CHECK (os_family IN ('windows','macos','linux')),
    first_seen_at   TIMESTAMP,
    last_seen_at    TIMESTAMP,
    admin_notes     TEXT
);

-- SUBMISSIONS: riwayat. Tiap pengisian form = 1 baris.
CREATE TABLE IF NOT EXISTS submissions (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id          INTEGER NOT NULL REFERENCES devices(id),
    submitted_at       TIMESTAMP NOT NULL,
    source             TEXT CHECK (source IN ('windows_script','mac_script','linux_script','manual')),

    -- Pemegang (menempel ke submission, BUKAN device)
    holder_name        TEXT NOT NULL,
    holder_position    TEXT,
    holder_company     TEXT,
    holder_location    TEXT,
    work_group         TEXT NOT NULL CHECK (work_group IN
                         ('field','admin','finance','data_processing','management','it','other')),
    work_group_other   TEXT,
    laptop_status      TEXT CHECK (laptop_status IN ('office_inventory','personal')),

    -- Identitas aset (disalin ke device saat pencocokan)
    hostname           TEXT,
    mac_address        TEXT,
    serial_number      TEXT,
    asset_no           TEXT,

    -- Spesifikasi: CPU
    cpu_model          TEXT,
    cpu_cores          INTEGER,
    cpu_threads        INTEGER,
    cpu_arch           TEXT,
    cpu_speed_mhz      INTEGER,
    cpu_passmark       INTEGER,

    -- Spesifikasi: GPU
    gpu                TEXT,

    -- Spesifikasi: RAM
    ram_gb             REAL,
    ram_type           TEXT,
    ram_speed_mhz      INTEGER,
    ram_usage_pct      REAL,
    ram_usage_gb       REAL,

    -- Spesifikasi: Storage
    ssd_gb             REAL,
    ssd_type           TEXT,
    hdd_gb             REAL,
    disk_raw           TEXT,
    os_total_gb        REAL,
    os_free_gb         REAL,

    -- Spesifikasi: Baterai
    battery_pct        REAL,
    battery_wh_full    REAL,
    battery_wh_design  REAL,
    battery_health_pct REAL,

    -- Spesifikasi: OS
    os_name            TEXT,

    -- Kondisi & kelengkapan (isian manusia)
    physical_condition TEXT CHECK (physical_condition IN ('good','fair','poor')),
    accessories        TEXT,
    purchase_year      INTEGER,
    issues             TEXT,

    -- Hasil penilaian kelayakan (snapshot, lihat docs/scoring.md)
    score_spec         INTEGER,
    score_load         INTEGER,
    score_total        INTEGER,
    status             TEXT CHECK (status IN ('eligible','upgrade','replace')),
    status_reasons     TEXT,
    eol_year           INTEGER
);

CREATE INDEX IF NOT EXISTS idx_submissions_device_time
    ON submissions (device_id, submitted_at);

-- CPU_BENCHMARKS: tabel referensi offline (di-seed Sesi 2).
CREATE TABLE IF NOT EXISTS cpu_benchmarks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cpu_key         TEXT UNIQUE,
    cpu_label       TEXT,
    passmark_multi  INTEGER,
    passmark_single INTEGER,
    cores           INTEGER,
    release_year    INTEGER,
    source          TEXT
);
"""

# Daftar kolom submissions yang boleh diisi lewat insert_submission().
# (id auto, sisanya dipetakan dari dict data.)
_SUBMISSION_COLUMNS = [
    "device_id", "submitted_at", "source",
    "holder_name", "holder_position", "holder_company", "holder_location",
    "work_group", "work_group_other", "laptop_status",
    "hostname", "mac_address", "serial_number", "asset_no",
    "cpu_model", "cpu_cores", "cpu_threads", "cpu_arch", "cpu_speed_mhz", "cpu_passmark",
    "gpu",
    "ram_gb", "ram_type", "ram_speed_mhz", "ram_usage_pct", "ram_usage_gb",
    "ssd_gb", "ssd_type", "hdd_gb", "disk_raw", "os_total_gb", "os_free_gb",
    "battery_pct", "battery_wh_full", "battery_wh_design", "battery_health_pct",
    "os_name",
    "physical_condition", "accessories", "purchase_year", "issues",
    "score_spec", "score_load", "score_total", "status", "status_reasons", "eol_year",
]


# ---------------------------------------------------------------------------
# KONEKSI
# ---------------------------------------------------------------------------
def _connect():
    """Buka koneksi SQLite baru dengan row_factory dict-like + FK aktif."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    """Koneksi SQLite per-request (di-cache di flask.g).

    Bila dipanggil di luar konteks aplikasi (mis. skrip), kembalikan koneksi
    lepas yang harus ditutup pemanggil.
    """
    try:
        if "db" not in g:
            g.db = _connect()
        return g.db
    except RuntimeError:
        # Di luar application context — koneksi sekali pakai.
        return _connect()


def close_db(e=None):
    """Tutup koneksi per-request (dipanggil teardown_appcontext)."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_app(app):
    """Daftarkan teardown agar koneksi per-request ditutup otomatis."""
    app.teardown_appcontext(close_db)


def init_db():
    """Buat folder data/ (bila perlu) + seluruh tabel skema."""
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = _connect()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# PENCOCOKAN / PEMBUATAN DEVICE
# ---------------------------------------------------------------------------
def find_or_create_device(serial, asset_no, mac, brand, model, os_family):
    """Cari device by serial -> asset_no -> mac; bila tak ada, buat baru.

    Mengembalikan device_id. Field identitas/brand/model diperbarui bila kosong,
    dan last_seen_at selalu diperbarui ke waktu sekarang.
    """
    db = get_db()
    now = _now()

    def _norm(v):
        v = (v or "").strip()
        return v or None

    serial = _norm(serial)
    asset_no = _norm(asset_no)
    mac = _norm(mac)

    row = None
    if serial:
        row = db.execute(
            "SELECT * FROM devices WHERE serial_number = ?", (serial,)
        ).fetchone()
    if row is None and asset_no:
        row = db.execute(
            "SELECT * FROM devices WHERE asset_no = ?", (asset_no,)
        ).fetchone()
    if row is None and mac:
        row = db.execute(
            "SELECT * FROM devices WHERE primary_mac = ?", (mac,)
        ).fetchone()

    if row is not None:
        device_id = row["id"]
        # Lengkapi field yang masih kosong + segarkan last_seen_at.
        db.execute(
            """UPDATE devices SET
                 serial_number = COALESCE(serial_number, ?),
                 asset_no      = COALESCE(asset_no, ?),
                 primary_mac   = COALESCE(primary_mac, ?),
                 brand         = COALESCE(brand, ?),
                 model         = COALESCE(model, ?),
                 os_family     = COALESCE(os_family, ?),
                 last_seen_at  = ?
               WHERE id = ?""",
            (serial, asset_no, mac, _norm(brand), _norm(model),
             _norm(os_family), now, device_id),
        )
        db.commit()
        return device_id

    # Buat device baru.
    cur = db.execute(
        """INSERT INTO devices
             (serial_number, asset_no, primary_mac, brand, model, os_family,
              first_seen_at, last_seen_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (serial, asset_no, mac, _norm(brand), _norm(model), _norm(os_family),
         now, now),
    )
    db.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# SUBMISSIONS
# ---------------------------------------------------------------------------
def insert_submission(data):
    """Sisipkan 1 baris submissions dari dict `data` (kolom = nama field schema).

    Kolom yang tidak ada di `data` diisi NULL. `submitted_at` diisi otomatis
    bila kosong. Mengembalikan id submission baru.
    """
    db = get_db()
    values = dict(data)
    values.setdefault("submitted_at", _now())

    cols = [c for c in _SUBMISSION_COLUMNS]
    placeholders = ", ".join("?" for _ in cols)
    params = [values.get(c) for c in cols]

    cur = db.execute(
        f"INSERT INTO submissions ({', '.join(cols)}) VALUES ({placeholders})",
        params,
    )
    db.commit()
    return cur.lastrowid


def latest_per_device():
    """Submission TERBARU per device (untuk list dashboard).

    Mengembalikan list dict gabungan kolom submission + beberapa kolom device.
    """
    db = get_db()
    rows = db.execute(
        """
        SELECT s.*,
               d.serial_number AS device_serial,
               d.asset_no      AS device_asset_no,
               d.brand         AS device_brand,
               d.model         AS device_model,
               d.os_family     AS device_os_family,
               d.admin_notes   AS device_admin_notes,
               d.first_seen_at AS device_first_seen_at,
               d.last_seen_at  AS device_last_seen_at
        FROM submissions s
        JOIN devices d ON d.id = s.device_id
        WHERE s.id = (
            SELECT s2.id FROM submissions s2
            WHERE s2.device_id = s.device_id
            ORDER BY s2.submitted_at DESC, s2.id DESC
            LIMIT 1
        )
        ORDER BY d.last_seen_at DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def device_with_history(device_id):
    """Detail 1 device + seluruh riwayat submission (terbaru dahulu).

    Mengembalikan {"device": dict|None, "submissions": list[dict]}.
    """
    db = get_db()
    device = db.execute(
        "SELECT * FROM devices WHERE id = ?", (device_id,)
    ).fetchone()
    subs = db.execute(
        """SELECT * FROM submissions
           WHERE device_id = ?
           ORDER BY submitted_at DESC, id DESC""",
        (device_id,),
    ).fetchall()
    return {
        "device": dict(device) if device else None,
        "submissions": [dict(s) for s in subs],
    }


# ---------------------------------------------------------------------------
# UTIL
# ---------------------------------------------------------------------------
def _now():
    """Waktu sekarang ISO-8601 (UTC lokal naive) untuk kolom timestamp."""
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")
