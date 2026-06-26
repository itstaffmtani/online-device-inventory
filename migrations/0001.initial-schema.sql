-- 0001 — Baseline skema (snapshot skema produksi saat migrasi yoyo diadopsi).
--
-- IDEMPOTEN: semua pakai "IF NOT EXISTS". Pada DB produksi yang sudah berisi
-- tabel-tabel ini (dibuat init_db() lama), migrasi ini menjadi no-op aman —
-- yoyo hanya mencatatnya sebagai "applied" di tabel _yoyo_migration.
--
-- Skema diambil langsung dari sqlite_master DB hasil init_db(), jadi 100%
-- cocok dengan produksi. JANGAN ubah file ini. Perubahan skema BARU = file
-- migrasi baru bernomor (0002_*.sql, dst). Lihat migrations/README.md.

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

CREATE TABLE IF NOT EXISTS employees (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name           TEXT NOT NULL,
    name_key            TEXT,
    employee_code       TEXT,
    company             TEXT,
    current_position    TEXT,
    current_work_group  TEXT,
    status              TEXT CHECK (status IN ('active','resigned')) DEFAULT 'active',
    notes               TEXT,
    first_seen_at       TIMESTAMP,
    last_seen_at        TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scoring_settings (
    key   TEXT PRIMARY KEY,
    value REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS submissions (
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
);

CREATE TABLE IF NOT EXISTS work_groups (
    key         TEXT PRIMARY KEY,
    label       TEXT NOT NULL,
    cpu_floor   INTEGER NOT NULL,
    cpu_ideal   INTEGER NOT NULL,
    ram_min     INTEGER NOT NULL,
    ram_ideal   INTEGER NOT NULL,
    w_cpu       REAL NOT NULL,
    w_ram       REAL NOT NULL,
    w_storage   REAL NOT NULL,
    w_battery   REAL NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 100,
    is_active   INTEGER NOT NULL DEFAULT 1,
    is_builtin  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_employees_key ON employees (name_key, company);
CREATE INDEX IF NOT EXISTS idx_submissions_device_time ON submissions (device_id, submitted_at);
