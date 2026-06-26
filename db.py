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
#   find_or_create_employee(full_name, company, position, work_group) -> int
#   insert_submission(data: dict) -> int
#   latest_per_device() -> list[dict]
#   latest_per_employee() -> list[dict]
#   device_with_history(device_id: int) -> dict     {device, submissions[]}
#   employee_with_history(employee_id: int) -> dict  {employee, submissions[]}

import os
import re
import shutil
import sqlite3

from flask import g

import scoring_config
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

-- EMPLOYEES: satu baris per KARYAWAN. Submission = ikatan karyawan + device.
-- Dipakai untuk menjejak resign/handover, ganti laptop, dan ganti jabatan.
CREATE TABLE IF NOT EXISTS employees (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name           TEXT NOT NULL,
    name_key            TEXT,        -- normalisasi pencocokan: lower, spasi tunggal, trim
    employee_code       TEXT,        -- opsional (NIK), bisa kosong
    company             TEXT,
    current_position    TEXT,        -- cache jabatan dari submission TERBARU
    current_work_group  TEXT,        -- cache kelompok dari submission TERBARU
    status              TEXT CHECK (status IN ('active','resigned')) DEFAULT 'active',
    notes               TEXT,        -- catatan admin
    first_seen_at       TIMESTAMP,
    last_seen_at        TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_employees_key
    ON employees (name_key, company);

-- SUBMISSIONS: riwayat. Tiap pengisian form = 1 baris.
CREATE TABLE IF NOT EXISTS submissions (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id          INTEGER NOT NULL REFERENCES devices(id),
    employee_id        INTEGER REFERENCES employees(id),
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
    cpu_usage_pct      REAL,         -- snapshot beban CPU saat dicek (rata-rata ~3s)

    -- Spesifikasi: GPU
    gpu                TEXT,

    -- Spesifikasi: Motherboard
    motherboard        TEXT,         -- vendor + produk motherboard

    -- Spesifikasi: RAM
    ram_gb             REAL,
    ram_type           TEXT,
    ram_speed_mhz      INTEGER,
    ram_usage_pct      REAL,
    ram_usage_gb       REAL,
    ram_slots_total    INTEGER,      -- jumlah slot RAM fisik (board)
    ram_slots_used     INTEGER,      -- slot terisi
    ram_max_gb         REAL,         -- kapasitas RAM maksimum board (GB)

    -- Spesifikasi: Storage
    ssd_gb             REAL,
    ssd_type           TEXT,
    hdd_gb             REAL,
    disk_raw           TEXT,
    os_total_gb        REAL,
    os_free_gb         REAL,
    disk_health_pct    REAL,         -- kesehatan disk 0-100 (100 - Wear; atau map HealthStatus)
    disk_health_raw    TEXT,         -- teks mentah (mis. "Healthy", "Wear 4%")

    -- Spesifikasi: Baterai
    battery_pct        REAL,
    battery_wh_full    REAL,
    battery_wh_design  REAL,
    battery_health_pct REAL,

    -- Spesifikasi: OS
    os_name            TEXT,

    -- Keamanan & kesiapan Windows 11
    tpm_version        TEXT,         -- mis. "2.0", "1.2", "Tidak ada"
    secure_boot        INTEGER,      -- 1=aktif/kapabel, 0=tidak, NULL=tak terdeteksi
    win11_ready        INTEGER,      -- 1=siap (indikasi), 0=tidak, NULL=tak terdeteksi/non-Windows
    win11_blockers     TEXT,         -- alasan tidak siap, mis. "TPM <2.0; Secure Boot mati"

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
    "device_id", "employee_id", "submitted_at", "source",
    "holder_name", "holder_position", "holder_company", "holder_location",
    "work_group", "work_group_other", "laptop_status",
    "hostname", "mac_address", "serial_number", "asset_no",
    "cpu_model", "cpu_cores", "cpu_threads", "cpu_arch", "cpu_speed_mhz", "cpu_passmark",
    "cpu_usage_pct",
    "gpu",
    "motherboard",
    "ram_gb", "ram_type", "ram_speed_mhz", "ram_usage_pct", "ram_usage_gb",
    "ram_slots_total", "ram_slots_used", "ram_max_gb",
    "ssd_gb", "ssd_type", "hdd_gb", "disk_raw", "os_total_gb", "os_free_gb",
    "disk_health_pct", "disk_health_raw",
    "battery_pct", "battery_wh_full", "battery_wh_design", "battery_health_pct",
    "os_name",
    "tpm_version", "secure_boot", "win11_ready", "win11_blockers",
    "physical_condition", "accessories", "purchase_year", "issues",
    "score_spec", "score_load", "score_total", "status", "status_reasons", "eol_year",
]

# Definisi submissions TANPA CHECK pada work_group (untuk rebuild migrasi —
# kelompok kerja kini DATA-DRIVEN di tabel work_groups, divalidasi di lapisan app).
# Hanya CHECK work_group yang dilepas; CHECK enum lain (source/status/dll) tetap.
# {T} = nama tabel (diisi saat rebuild). Daftar kolom WAJIB identik dgn SCHEMA.
_SUBMISSIONS_NO_WG_CHECK = """
CREATE TABLE {T} (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id          INTEGER NOT NULL REFERENCES devices(id),
    employee_id        INTEGER REFERENCES employees(id),
    submitted_at       TIMESTAMP NOT NULL,
    source             TEXT CHECK (source IN ('windows_script','mac_script','linux_script','manual')),
    holder_name        TEXT NOT NULL,
    holder_position    TEXT,
    holder_company     TEXT,
    holder_location    TEXT,
    work_group         TEXT NOT NULL,
    work_group_other   TEXT,
    laptop_status      TEXT CHECK (laptop_status IN ('office_inventory','personal')),
    hostname           TEXT,
    mac_address        TEXT,
    serial_number      TEXT,
    asset_no           TEXT,
    cpu_model          TEXT,
    cpu_cores          INTEGER,
    cpu_threads        INTEGER,
    cpu_arch           TEXT,
    cpu_speed_mhz      INTEGER,
    cpu_passmark       INTEGER,
    cpu_usage_pct      REAL,
    gpu                TEXT,
    motherboard        TEXT,
    ram_gb             REAL,
    ram_type           TEXT,
    ram_speed_mhz      INTEGER,
    ram_usage_pct      REAL,
    ram_usage_gb       REAL,
    ram_slots_total    INTEGER,
    ram_slots_used     INTEGER,
    ram_max_gb         REAL,
    ssd_gb             REAL,
    ssd_type           TEXT,
    hdd_gb             REAL,
    disk_raw           TEXT,
    os_total_gb        REAL,
    os_free_gb         REAL,
    disk_health_pct    REAL,
    disk_health_raw    TEXT,
    battery_pct        REAL,
    battery_wh_full    REAL,
    battery_wh_design  REAL,
    battery_health_pct REAL,
    os_name            TEXT,
    tpm_version        TEXT,
    secure_boot        INTEGER,
    win11_ready        INTEGER,
    win11_blockers     TEXT,
    physical_condition TEXT CHECK (physical_condition IN ('good','fair','poor')),
    accessories        TEXT,
    purchase_year      INTEGER,
    issues             TEXT,
    score_spec         INTEGER,
    score_load         INTEGER,
    score_total        INTEGER,
    status             TEXT CHECK (status IN ('eligible','upgrade','replace')),
    status_reasons     TEXT,
    eol_year           INTEGER
)
"""

# Kolom baru submissions yang ditambahkan via migrasi aditif (ALTER ADD COLUMN).
# Tiap entri: (nama_kolom, definisi_tipe SQL).
#
# CATATAN MAINTENANCE: daftar ini sekarang LEGACY/BEKU. Mulai sekarang perubahan
# skema BARU (tambah kolom/tabel) dibuat sebagai file migrasi yoyo di folder
# migrations/ (lihat migrations/README.md), bukan ditambah ke daftar ini.
# Daftar ini dipertahankan agar DB lama yang belum lewat baseline yoyo tetap
# tersinkron saat init_db().
_SUBMISSION_NEW_COLUMNS = [
    ("employee_id", "INTEGER REFERENCES employees(id)"),
    ("cpu_usage_pct", "REAL"),
    ("motherboard", "TEXT"),
    ("ram_slots_total", "INTEGER"),
    ("ram_slots_used", "INTEGER"),
    ("ram_max_gb", "REAL"),
    ("disk_health_pct", "REAL"),
    ("disk_health_raw", "TEXT"),
    ("tpm_version", "TEXT"),
    ("secure_boot", "INTEGER"),
    ("win11_ready", "INTEGER"),
    ("win11_blockers", "TEXT"),
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
    """Buat/sinkronkan skema secara ADITIF & idempoten (tanpa hapus data).

    Langkah:
      1. Backup file DB ke data/inventory.db.bak (bila DB sudah ada).
      2. CREATE TABLE IF NOT EXISTS (devices, employees, submissions, dst).
      3. Untuk tiap kolom baru submissions: cek PRAGMA table_info lalu
         ALTER TABLE ADD COLUMN bila belum ada.
      4. Pastikan index employees terbuat.
      5. Backfill employee_id untuk submission yang masih NULL.
    """
    db_path = config.DB_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # 1. Backup sebelum migrasi (hanya bila DB sudah ada isinya).
    if os.path.exists(db_path):
        try:
            shutil.copy2(db_path, db_path + ".bak")
        except OSError:
            # Backup gagal (mis. izin) — jangan hentikan init, tapi lanjut hati-hati.
            pass

    conn = _connect()
    try:
        # 2. Buat tabel + index dasar (IF NOT EXISTS, aman diulang).
        conn.executescript(SCHEMA)
        conn.commit()

        # 3. Migrasi aditif kolom submissions yang mungkin belum ada (DB lama).
        existing = {
            r["name"]
            for r in conn.execute("PRAGMA table_info(submissions)").fetchall()
        }
        for col_name, col_def in _SUBMISSION_NEW_COLUMNS:
            if col_name not in existing:
                conn.execute(
                    f"ALTER TABLE submissions ADD COLUMN {col_name} {col_def}"
                )
        conn.commit()

        # 4. Pastikan index employees ada (untuk DB yang baru di-migrasi).
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_employees_key "
            "ON employees (name_key, company)"
        )
        conn.commit()

        # 4b. Tabel parameter skoring data-driven (work_groups + scoring_settings)
        #     + seed DEFAULT (idempoten, tidak menimpa yang sudah diubah admin).
        scoring_config.ensure_tables(conn)

        # 4c. Lepas CHECK lama pada work_group agar kelompok kerja bisa dinamis.
        #     Rebuild aman: salin semua baris -> verifikasi jumlah -> swap.
        _rebuild_submissions_drop_wg_check(conn)

        # 5. Backfill employee_id dari holder_name + holder_company untuk
        #    submission lama yang belum punya ikatan karyawan.
        _backfill_employees(conn)
    finally:
        conn.close()


def _rebuild_submissions_drop_wg_check(conn):
    """Lepas CHECK (work_group IN ...) dari tabel submissions (SEKALI, idempoten).

    SQLite tak bisa DROP CHECK langsung -> rebuild tabel. Sangat berhati-hati
    karena DB produksi berisi data nyata:
      1. Deteksi: hanya jalan bila CHECK work_group masih ada (idempoten).
      2. Salin SEMUA kolom yang ada saat ini (interseksi old∩new) ke tabel baru.
      3. VERIFIKASI jumlah baris old == new sebelum menghapus tabel lama.
      4. Bila tidak cocok -> ROLLBACK & angkat error (file .bak dari init_db tetap aman).
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='submissions'"
    ).fetchone()
    if not row or not row[0]:
        return
    norm = re.sub(r"\s+", " ", row[0])
    if "CHECK (work_group IN" not in norm and "CHECK(work_group IN" not in norm:
        return  # CHECK sudah tidak ada -> tidak perlu rebuild.

    # Kolom yang akan disalin = kolom submissions saat ini ∩ kolom tabel baru.
    old_cols = [r["name"] for r in
                conn.execute("PRAGMA table_info(submissions)").fetchall()]
    # Buat tabel baru lebih dulu untuk tahu kolomnya.
    conn.execute("DROP TABLE IF EXISTS submissions_rebuild_tmp")
    conn.execute(_SUBMISSIONS_NO_WG_CHECK.format(T="submissions_rebuild_tmp"))
    new_cols = [r["name"] for r in
                conn.execute("PRAGMA table_info(submissions_rebuild_tmp)").fetchall()]
    cols = [c for c in old_cols if c in new_cols]
    collist = ", ".join(cols)

    old_count = conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]

    fk_was_on = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")
        conn.execute(
            f"INSERT INTO submissions_rebuild_tmp ({collist}) "
            f"SELECT {collist} FROM submissions"
        )
        new_count = conn.execute(
            "SELECT COUNT(*) FROM submissions_rebuild_tmp"
        ).fetchone()[0]
        if new_count != old_count:
            conn.execute("ROLLBACK")
            conn.execute("DROP TABLE IF EXISTS submissions_rebuild_tmp")
            raise RuntimeError(
                f"Rebuild submissions dibatalkan: jumlah baris tidak cocok "
                f"(lama={old_count}, baru={new_count}). Data lama tidak diubah."
            )
        conn.execute("DROP TABLE submissions")
        conn.execute("ALTER TABLE submissions_rebuild_tmp RENAME TO submissions")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_submissions_device_time "
            "ON submissions (device_id, submitted_at)"
        )
        conn.execute("COMMIT")
    except Exception:
        # Pastikan tidak meninggalkan transaksi/tabel sementara yang menggantung.
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        try:
            conn.execute("DROP TABLE IF EXISTS submissions_rebuild_tmp")
            conn.commit()
        except sqlite3.Error:
            pass
        raise
    finally:
        if fk_was_on:
            conn.execute("PRAGMA foreign_keys = ON")


def _backfill_employees(conn):
    """Isi employee_id submissions yang masih NULL (migrasi data lama).

    Bekerja pada koneksi `conn` (di luar konteks request). Untuk tiap submission
    tanpa employee_id, cocokkan/buat karyawan dari holder_name + holder_company
    + holder_position + work_group, lalu set employee_id-nya.
    """
    rows = conn.execute(
        """SELECT id, holder_name, holder_company, holder_position, work_group
           FROM submissions
           WHERE employee_id IS NULL"""
    ).fetchall()
    for r in rows:
        emp_id = _find_or_create_employee_conn(
            conn,
            r["holder_name"],
            r["holder_company"],
            r["holder_position"],
            r["work_group"],
        )
        if emp_id is not None:
            conn.execute(
                "UPDATE submissions SET employee_id = ? WHERE id = ?",
                (emp_id, r["id"]),
            )
    conn.commit()


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
# PENCOCOKAN / PEMBUATAN KARYAWAN
# ---------------------------------------------------------------------------
def _name_key(full_name):
    """Normalisasi nama untuk pencocokan: lower, spasi tunggal, trim.

    Mengembalikan string ternormalisasi, atau None bila nama kosong.
    """
    key = re.sub(r"\s+", " ", (full_name or "").strip().lower())
    return key or None


def _find_or_create_employee_conn(conn, full_name, company=None,
                                  position=None, work_group=None):
    """Inti logika find_or_create_employee pada koneksi mentah `conn`.

    Dipakai oleh find_or_create_employee() (request) maupun backfill (init_db).
    Cocokkan via name_key + company; bila ada, segarkan cache jabatan/kelompok +
    last_seen_at + status='active'. Bila tidak, INSERT karyawan baru.
    Mengembalikan id karyawan, atau None bila nama kosong.
    """
    name_key = _name_key(full_name)
    if name_key is None:
        # Tanpa nama valid tidak bisa membentuk identitas karyawan.
        return None

    def _norm(v):
        v = (v or "").strip()
        return v or None

    full_name = (full_name or "").strip()
    company = _norm(company)
    position = _norm(position)
    work_group = _norm(work_group)
    now = _now()

    # Cocokkan via name_key + company (NULL/'' diperlakukan setara).
    row = conn.execute(
        """SELECT * FROM employees
           WHERE name_key = ? AND IFNULL(company, '') = IFNULL(?, '')""",
        (name_key, company),
    ).fetchone()

    if row is not None:
        emp_id = row["id"]
        # Segarkan cache jabatan/kelompok terbaru + tandai aktif kembali.
        conn.execute(
            """UPDATE employees SET
                 full_name          = COALESCE(?, full_name),
                 current_position   = COALESCE(?, current_position),
                 current_work_group = COALESCE(?, current_work_group),
                 status             = 'active',
                 last_seen_at       = ?
               WHERE id = ?""",
            (full_name or None, position, work_group, now, emp_id),
        )
        conn.commit()
        return emp_id

    # Karyawan baru.
    cur = conn.execute(
        """INSERT INTO employees
             (full_name, name_key, company, current_position,
              current_work_group, status, first_seen_at, last_seen_at)
           VALUES (?, ?, ?, ?, ?, 'active', ?, ?)""",
        (full_name, name_key, company, position, work_group, now, now),
    )
    conn.commit()
    return cur.lastrowid


def find_or_create_employee(full_name, company=None, position=None,
                            work_group=None):
    """Cari karyawan via (name_key, company); bila tak ada, buat baru.

    name_key = normalisasi(full_name) (lower, \\s+ -> ' ', strip).
    Bila ditemukan: update last_seen_at + current_position + current_work_group
    + status='active'. Bila tidak: INSERT baru (first_seen_at=last_seen_at=now).
    Mengembalikan id karyawan.
    """
    db = get_db()
    return _find_or_create_employee_conn(
        db, full_name, company, position, work_group
    )


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


def get_submission(submission_id):
    """Ambil 1 baris submission (dict) by id, atau None."""
    db = get_db()
    row = db.execute(
        "SELECT * FROM submissions WHERE id = ?", (submission_id,)
    ).fetchone()
    return dict(row) if row else None


def update_submission(submission_id, data):
    """Perbarui kolom submission yang dikenal (dipakai fitur edit & recalc admin).

    Hanya kolom dalam _SUBMISSION_COLUMNS yang diproses. Kolom yang TIDAK ada di
    `data` tidak diubah. Mengembalikan jumlah baris tersentuh (0/1).
    """
    db = get_db()
    cols = [c for c in _SUBMISSION_COLUMNS if c in data]
    if not cols:
        return 0
    assignments = ", ".join(f"{c} = ?" for c in cols)
    params = [data[c] for c in cols]
    params.append(submission_id)
    cur = db.execute(
        f"UPDATE submissions SET {assignments} WHERE id = ?", params
    )
    db.commit()
    return cur.rowcount


def all_submissions():
    """Semua baris submission (dict) — untuk hitung ulang skor massal."""
    db = get_db()
    rows = db.execute("SELECT * FROM submissions ORDER BY id").fetchall()
    return [dict(r) for r in rows]


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

    Tiap submission menyertakan kolom `employee_id` (bagian dari SELECT *),
    agar template bisa menaut ke /admin/karyawan/<id>.
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
# KARYAWAN — agregat & riwayat
# ---------------------------------------------------------------------------
def latest_per_employee():
    """Submission TERBARU per karyawan (untuk tab "Karyawan" dashboard).

    Satu baris per employee = submission terbarunya, JOIN devices (alias
    device_brand/device_model/device_serial seperti latest_per_device) + kolom
    karyawan (emp_full_name, emp_company, emp_status, emp_current_position,
    emp_current_work_group). Urut by last_seen_at karyawan (desc).
    """
    db = get_db()
    rows = db.execute(
        """
        SELECT s.*,
               d.serial_number     AS device_serial,
               d.asset_no          AS device_asset_no,
               d.brand             AS device_brand,
               d.model             AS device_model,
               d.os_family         AS device_os_family,
               e.full_name          AS emp_full_name,
               e.company            AS emp_company,
               e.status             AS emp_status,
               e.current_position   AS emp_current_position,
               e.current_work_group AS emp_current_work_group,
               e.last_seen_at       AS emp_last_seen_at
        FROM employees e
        JOIN submissions s ON s.id = (
            SELECT s2.id FROM submissions s2
            WHERE s2.employee_id = e.id
            ORDER BY s2.submitted_at DESC, s2.id DESC
            LIMIT 1
        )
        JOIN devices d ON d.id = s.device_id
        ORDER BY e.last_seen_at DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def employee_with_history(employee_id):
    """Detail 1 karyawan + seluruh riwayat submission (terbaru dahulu).

    Tiap submission di-JOIN ke devices (alias device_brand/device_model/
    device_serial) agar bisa menaut ke laptop yang pernah dipegang.
    Mengembalikan {"employee": dict|None, "submissions": list[dict]}.
    """
    db = get_db()
    employee = db.execute(
        "SELECT * FROM employees WHERE id = ?", (employee_id,)
    ).fetchone()
    subs = db.execute(
        """
        SELECT s.*,
               d.serial_number AS device_serial,
               d.asset_no      AS device_asset_no,
               d.brand         AS device_brand,
               d.model         AS device_model,
               d.os_family     AS device_os_family
        FROM submissions s
        JOIN devices d ON d.id = s.device_id
        WHERE s.employee_id = ?
        ORDER BY s.submitted_at DESC, s.id DESC
        """,
        (employee_id,),
    ).fetchall()
    return {
        "employee": dict(employee) if employee else None,
        "submissions": [dict(s) for s in subs],
    }


# ---------------------------------------------------------------------------
# UTIL
# ---------------------------------------------------------------------------
def _now():
    """Waktu sekarang ISO-8601 (UTC lokal naive) untuk kolom timestamp."""
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")
