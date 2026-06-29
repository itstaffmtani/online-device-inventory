# scoring_config.py — parameter skoring & kelompok kerja DATA-DRIVEN (DB).
#
# MODEL PROFIL BERSAMA (2026-06). Sebelumnya tiap kelompok kerja menyimpan angka
# kebutuhannya sendiri (CPU/RAM/bobot) inline di work_groups — banyak kelompok
# punya angka identik, jadi melelahkan diedit. Kini angka kebutuhan hidup di tabel
# `scoring_profiles`; tiap kelompok hanya MENUNJUK ke satu profil via kolom
# `profile_key`. Banyak kelompok boleh berbagi profil → admin cukup mengedit profil
# SEKALI dan semua anggotanya ikut berubah. Label kelompok tetap utuh sehingga
# laporan masih bisa membedakan (mis. Keuangan vs Pengolahan Data).
#
#   scoring_profiles — 1 baris per profil kebutuhan (CPU floor/ideal, RAM min/ideal,
#                      bobot komponen). INI yang diedit admin.
#   work_groups      — 1 baris per kelompok kerja (label + profile_key + urutan +
#                      aktif). Numeriknya diambil dari profil yang ditunjuk.
#   scoring_settings — key/value ambang global (status cutoff, EOL, blend).
#
# Sumber kebenaran ANGKA tetap docs/scoring.md; nilai DEFAULT di bawah = seed awal.
# Bila tabel/DB belum ada, loader otomatis fallback ke DEFAULT sehingga scoring
# tetap jalan (mis. saat self-test scoring.py).

import sqlite3

# ---------------------------------------------------------------------------
# DEFAULT — seed awal (Standar Frugal 2026-06 + perapian profil bersama).
# Perapian: HR ideal RAM 16 -> 8 (HR klerikal, sekelas Administrasi) sehingga HR
# ikut profil "Kantor Umum"; Lapangan RAM min 4 -> 8 (selaras lantai produktivitas
# korporat). Tiap baris bobot W_* WAJIB berjumlah 1.0.
# ---------------------------------------------------------------------------
# Bobot per profil (jumlah tiap baris = 1.0).
_W_GENERAL = {"cpu": 0.25, "ram": 0.30, "storage": 0.25, "battery": 0.20}  # kantor umum
_W_FIELD = {"cpu": 0.20, "ram": 0.20, "storage": 0.20, "battery": 0.40}    # Lapangan: baterai dominan
_W_MANAGEMENT = {"cpu": 0.30, "ram": 0.25, "storage": 0.20, "battery": 0.25}
_W_FINANCE = {"cpu": 0.25, "ram": 0.40, "storage": 0.15, "battery": 0.20}  # keuangan + data
_W_DESIGN = {"cpu": 0.35, "ram": 0.35, "storage": 0.15, "battery": 0.15}
_W_IT = {"cpu": 0.40, "ram": 0.35, "storage": 0.15, "battery": 0.10}

# Profil kebutuhan. Tiap entri:
#   (key, label, cpu_floor, cpu_ideal, ram_min, ram_ideal, weights, sort_order)
_DEFAULT_PROFILES = [
    ("kantor",      "Kantor Umum",     4000,  8000,  8,  8,  _W_GENERAL,    10),
    ("lapangan",    "Lapangan (mobile)", 3500, 7000, 8,  8,  _W_FIELD,      20),
    ("manajemen",   "Manajemen",       5000,  10000, 8,  16, _W_MANAGEMENT, 30),
    ("keuangan",    "Keuangan & Data", 5500,  11000, 8,  16, _W_FINANCE,    40),
    ("kreatif",     "Kreatif",         7000,  14000, 8,  16, _W_DESIGN,     60),
    ("workstation", "Workstation IT",  8000,  16000, 16, 32, _W_IT,         70),
]

# Kelompok kerja -> profil. Tiap entri:
#   (key, label, profile_key, sort_order, is_builtin)
_DEFAULT_GROUPS = [
    ("field",           "Lapangan",        "lapangan",    10,  1),
    ("admin",           "Administrasi",    "kantor",      20,  1),
    ("finance",         "Keuangan",        "keuangan",    30,  1),
    ("data_processing", "Pengolahan Data", "keuangan",    40,  1),
    ("management",      "Manajemen",       "manajemen",   50,  1),
    ("it",              "IT",              "workstation", 60,  1),
    ("rpo",             "RPO",             "lapangan",    70,  1),
    ("mandor",          "Mandor",          "lapangan",    75,  1),
    ("design",          "Design/Kreatif",  "kreatif",     80,  1),
    ("hr",              "HR/GA",           "kantor",      90,  1),
    # — 'other' selalu terakhir: teks bebas (work_group_other), profil = kantor —
    ("other",           "Lainnya",         "kantor",      999, 1),
]

# Ambang global default (scoring.md §4a, §5, §0).
_DEFAULT_SETTINGS = {
    "status_eligible_min": 70.0,   # skor >= ini -> Layak
    "status_upgrade_min":  50.0,   # skor >= ini -> Upgrade, di bawahnya -> Ganti
    "base_lifespan_years": 5.0,    # masa pakai dasar EOL
    "blend_spec":          0.7,    # bobot Skor Spek pada Skor Total
    "blend_load":          0.3,    # bobot Skor Beban pada Skor Total
}

# Kelompok cadangan bila work_group tak dikenal (profil netral).
DEFAULT_PROFILE_KEY = "admin"
# Profil cadangan bila kelompok menunjuk profil yang tak ada.
_FALLBACK_PROFILE_KEY = "kantor"

_NUM_PROFILE_FIELDS = ("cpu_floor", "cpu_ideal", "ram_min", "ram_ideal",
                       "w_cpu", "w_ram", "w_storage", "w_battery", "sort_order")


# ---------------------------------------------------------------------------
# Skema + seed (idempoten)
# ---------------------------------------------------------------------------
_SCHEMA = """
CREATE TABLE IF NOT EXISTS scoring_profiles (
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
    sort_order  INTEGER NOT NULL DEFAULT 100
);

CREATE TABLE IF NOT EXISTS work_groups (
    key         TEXT PRIMARY KEY,
    label       TEXT NOT NULL,
    profile_key TEXT,
    sort_order  INTEGER NOT NULL DEFAULT 100,
    is_active   INTEGER NOT NULL DEFAULT 1,
    is_builtin  INTEGER NOT NULL DEFAULT 0,
    -- kolom numerik lama (kompat DB lama; TIDAK dipakai scoring lagi -> nullable) --
    cpu_floor   INTEGER,
    cpu_ideal   INTEGER,
    ram_min     INTEGER,
    ram_ideal   INTEGER,
    w_cpu       REAL,
    w_ram       REAL,
    w_storage   REAL,
    w_battery   REAL
);

CREATE TABLE IF NOT EXISTS scoring_settings (
    key   TEXT PRIMARY KEY,
    value REAL NOT NULL
);
"""


def _default_profiles_map():
    """{pkey: {key,label,cpu_floor,...,w_battery,sort_order}}."""
    out = {}
    for (pk, label, cf, ci, rm, ri, w, order) in _DEFAULT_PROFILES:
        out[pk] = {
            "key": pk, "label": label, "cpu_floor": cf, "cpu_ideal": ci,
            "ram_min": rm, "ram_ideal": ri, "w_cpu": w["cpu"], "w_ram": w["ram"],
            "w_storage": w["storage"], "w_battery": w["battery"], "sort_order": order,
        }
    return out


_DEFAULT_PROFILES_MAP = _default_profiles_map()


def ensure_tables(conn):
    """Buat tabel + seed DEFAULT (idempoten). Aman dijalankan tiap start.

    Seed memakai INSERT OR IGNORE sehingga baris yang sudah diubah admin TIDAK
    ditimpa. Untuk DB lama (work_groups tanpa kolom profile_key), kolom ditambah
    via ALTER lalu profile_key kelompok bawaan di-backfill dari DEFAULT.
    """
    conn.executescript(_SCHEMA)

    # Migrasi DB lama: tambah kolom profile_key bila belum ada (idempoten).
    try:
        conn.execute("ALTER TABLE work_groups ADD COLUMN profile_key TEXT")
    except sqlite3.OperationalError:
        pass  # kolom sudah ada

    # Seed profil.
    for (pk, label, cf, ci, rm, ri, w, order) in _DEFAULT_PROFILES:
        conn.execute(
            """INSERT OR IGNORE INTO scoring_profiles
                 (key, label, cpu_floor, cpu_ideal, ram_min, ram_ideal,
                  w_cpu, w_ram, w_storage, w_battery, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (pk, label, cf, ci, rm, ri,
             w["cpu"], w["ram"], w["storage"], w["battery"], order),
        )

    # Seed kelompok (numerik inline diisi mirror dari profil agar kompat DB lama
    # yang kolomnya NOT NULL; scoring tetap baca via profile_key).
    for (key, label, pkey, order, builtin) in _DEFAULT_GROUPS:
        p = _DEFAULT_PROFILES_MAP[pkey]
        conn.execute(
            """INSERT OR IGNORE INTO work_groups
                 (key, label, profile_key, sort_order, is_active, is_builtin,
                  cpu_floor, cpu_ideal, ram_min, ram_ideal,
                  w_cpu, w_ram, w_storage, w_battery)
               VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (key, label, pkey, order, builtin,
             p["cpu_floor"], p["cpu_ideal"], p["ram_min"], p["ram_ideal"],
             p["w_cpu"], p["w_ram"], p["w_storage"], p["w_battery"]),
        )

    # Backfill: kelompok bawaan yang ada lebih dulu (DB lama) tapi profile_key
    # masih kosong -> isi dari DEFAULT. Tak menyentuh penugasan profil kustom admin.
    for (key, label, pkey, order, builtin) in _DEFAULT_GROUPS:
        conn.execute(
            "UPDATE work_groups SET profile_key = ? "
            "WHERE key = ? AND (profile_key IS NULL OR profile_key = '')",
            (pkey, key),
        )

    for k, v in _DEFAULT_SETTINGS.items():
        conn.execute(
            "INSERT OR IGNORE INTO scoring_settings (key, value) VALUES (?, ?)",
            (k, v),
        )
    conn.commit()


def reseed_defaults(conn):
    """Tulis-paksa seluruh DEFAULT (profil + kelompok + settings) — MENIMPA baris
    yang sudah ada (kebalikan ensure_tables yang INSERT OR IGNORE).

    PERINGATAN: menimpa kustomisasi admin. Setelah ini jalankan "Hitung ulang
    semua" agar skor lama ikut diperbarui.
    """
    conn.executescript(_SCHEMA)
    try:
        conn.execute("ALTER TABLE work_groups ADD COLUMN profile_key TEXT")
    except sqlite3.OperationalError:
        pass

    for (pk, label, cf, ci, rm, ri, w, order) in _DEFAULT_PROFILES:
        conn.execute(
            """INSERT INTO scoring_profiles
                 (key, label, cpu_floor, cpu_ideal, ram_min, ram_ideal,
                  w_cpu, w_ram, w_storage, w_battery, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET
                 label=excluded.label, cpu_floor=excluded.cpu_floor,
                 cpu_ideal=excluded.cpu_ideal, ram_min=excluded.ram_min,
                 ram_ideal=excluded.ram_ideal, w_cpu=excluded.w_cpu,
                 w_ram=excluded.w_ram, w_storage=excluded.w_storage,
                 w_battery=excluded.w_battery, sort_order=excluded.sort_order""",
            (pk, label, cf, ci, rm, ri,
             w["cpu"], w["ram"], w["storage"], w["battery"], order),
        )

    for (key, label, pkey, order, builtin) in _DEFAULT_GROUPS:
        p = _DEFAULT_PROFILES_MAP[pkey]
        conn.execute(
            """INSERT INTO work_groups
                 (key, label, profile_key, sort_order, is_active, is_builtin,
                  cpu_floor, cpu_ideal, ram_min, ram_ideal,
                  w_cpu, w_ram, w_storage, w_battery)
               VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET
                 label=excluded.label, profile_key=excluded.profile_key,
                 sort_order=excluded.sort_order, is_active=excluded.is_active,
                 is_builtin=excluded.is_builtin""",
            (key, label, pkey, order, builtin,
             p["cpu_floor"], p["cpu_ideal"], p["ram_min"], p["ram_ideal"],
             p["w_cpu"], p["w_ram"], p["w_storage"], p["w_battery"]),
        )

    for k, v in _DEFAULT_SETTINGS.items():
        conn.execute(
            "INSERT INTO scoring_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (k, v),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Koneksi — pakai koneksi per-request db.get_db() bila ada; else standalone.
# ---------------------------------------------------------------------------
def _conn():
    from db import get_db
    return get_db()


# ---------------------------------------------------------------------------
# LOADER — defensif: bila tabel/DB belum ada, fallback ke DEFAULT.
# ---------------------------------------------------------------------------
def _profiles_map():
    """{pkey: {label, cpu_floor, ...}} dari DB; fallback DEFAULT."""
    try:
        cur = _conn().execute(
            "SELECT * FROM scoring_profiles ORDER BY sort_order, key"
        )
        rows = {r["key"]: dict(r) for r in cur.fetchall()}
        if rows:
            return rows
    except sqlite3.Error:
        pass
    return {k: dict(v) for k, v in _DEFAULT_PROFILES_MAP.items()}


def _group_rows():
    """Baris kelompok (key,label,profile_key,sort_order,is_active,is_builtin)."""
    try:
        cur = _conn().execute(
            "SELECT key, label, profile_key, sort_order, is_active, is_builtin "
            "FROM work_groups ORDER BY sort_order, key"
        )
        rows = [dict(r) for r in cur.fetchall()]
        if rows:
            return rows
    except sqlite3.Error:
        pass
    return [
        {"key": key, "label": label, "profile_key": pkey,
         "sort_order": order, "is_active": 1, "is_builtin": builtin}
        for (key, label, pkey, order, builtin) in _DEFAULT_GROUPS
    ]


def _resolve_profile(group_row, pmap):
    """Profil efektif untuk 1 kelompok (fallback ke profil 'kantor' lalu apa pun)."""
    pk = group_row.get("profile_key")
    return (pmap.get(pk) or pmap.get(_FALLBACK_PROFILE_KEY)
            or next(iter(pmap.values())))


def all_profiles():
    """Daftar profil (list dict) urut sort_order. Fallback DEFAULT bila perlu."""
    pmap = _profiles_map()
    return sorted(pmap.values(),
                  key=lambda p: (p.get("sort_order", 100), p["key"]))


def all_groups(active_only=False):
    """Daftar kelompok (list dict) urut sort_order, DENGAN angka profil ter-resolve
    (cpu_floor/ideal, ram_min/ideal, w_* + profile_key + profile_label). Fallback
    DEFAULT bila perlu."""
    pmap = _profiles_map()
    out = []
    for r in _group_rows():
        prof = _resolve_profile(r, pmap)
        merged = dict(r)
        merged["profile_key"] = r.get("profile_key") or prof["key"]
        merged["profile_label"] = prof["label"]
        for f in ("cpu_floor", "cpu_ideal", "ram_min", "ram_ideal",
                  "w_cpu", "w_ram", "w_storage", "w_battery"):
            merged[f] = prof[f]
        out.append(merged)
    if active_only:
        out = [r for r in out if r.get("is_active")]
    return out


def profile_members():
    """{profile_key: [ {key,label} kelompok ]} untuk tampilan 'anggota profil'."""
    out = {}
    for g in all_groups():
        out.setdefault(g["profile_key"], []).append(
            {"key": g["key"], "label": g["label"]})
    return out


def get_profiles():
    """{group_key: {cpu_floor, cpu_ideal, ram_min, ram_ideal}} — kompatibel lama."""
    return {
        r["key"]: {
            "cpu_floor": int(r["cpu_floor"]), "cpu_ideal": int(r["cpu_ideal"]),
            "ram_min": int(r["ram_min"]), "ram_ideal": int(r["ram_ideal"]),
        }
        for r in all_groups()
    }


def get_weights():
    """{group_key: {cpu, ram, storage, battery}}."""
    return {
        r["key"]: {
            "cpu": float(r["w_cpu"]), "ram": float(r["w_ram"]),
            "storage": float(r["w_storage"]), "battery": float(r["w_battery"]),
        }
        for r in all_groups()
    }


def get_labels():
    """{group_key: label} untuk seluruh kelompok (untuk tampilan)."""
    return {r["key"]: r["label"] for r in all_groups()}


def get_settings():
    """Ambang global (dict float). Fallback DEFAULT bila tabel belum ada."""
    out = dict(_DEFAULT_SETTINGS)
    try:
        cur = _conn().execute("SELECT key, value FROM scoring_settings")
        for r in cur.fetchall():
            out[r["key"]] = float(r["value"])
    except sqlite3.Error:
        pass
    return out


# ---------------------------------------------------------------------------
# CRUD (dipakai halaman admin /admin/skoring)
# ---------------------------------------------------------------------------
def update_profile(key, fields):
    """Perbarui angka/label 1 profil. `fields` dict sebagian kolom. True bila
    ada baris tersentuh. Inilah edit yang memengaruhi SEMUA kelompok anggota."""
    conn = _conn()
    sets, params = [], []
    if "label" in fields and str(fields["label"]).strip():
        sets.append("label = ?"); params.append(str(fields["label"]).strip())
    for col in _NUM_PROFILE_FIELDS:
        if col in fields and fields[col] is not None:
            sets.append(f"{col} = ?"); params.append(fields[col])
    if not sets:
        return False
    params.append(key)
    cur = conn.execute(
        f"UPDATE scoring_profiles SET {', '.join(sets)} WHERE key = ?", params)
    conn.commit()
    return cur.rowcount > 0


def create_profile(key, label, profile):
    """Tambah profil baru. `profile` dict (cpu_floor..w_battery, sort_order opsional).

    Mengembalikan (ok, error). key dinormalisasi: lower, spasi->underscore.
    """
    import re
    key = re.sub(r"[^a-z0-9_]+", "_", (key or "").strip().lower()).strip("_")
    if not key:
        return False, "Kunci profil tidak valid."
    if not (label or "").strip():
        return False, "Nama profil wajib diisi."
    conn = _conn()
    if conn.execute("SELECT 1 FROM scoring_profiles WHERE key = ?", (key,)).fetchone():
        return False, f"Profil '{key}' sudah ada."
    p = dict(profile or {})
    conn.execute(
        """INSERT INTO scoring_profiles
             (key, label, cpu_floor, cpu_ideal, ram_min, ram_ideal,
              w_cpu, w_ram, w_storage, w_battery, sort_order)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (key, label.strip(),
         int(p.get("cpu_floor", 8000)), int(p.get("cpu_ideal", 16000)),
         int(p.get("ram_min", 8)), int(p.get("ram_ideal", 16)),
         float(p.get("w_cpu", 0.35)), float(p.get("w_ram", 0.30)),
         float(p.get("w_storage", 0.20)), float(p.get("w_battery", 0.15)),
         int(p.get("sort_order", 500))),
    )
    conn.commit()
    return True, key


def update_group(key, fields):
    """Perbarui label / profil yang ditunjuk / aktif / urutan 1 kelompok.
    Angka kebutuhan TIDAK lagi diedit di sini (ada di profil). True bila tersentuh.
    """
    conn = _conn()
    sets, params = [], []
    if "label" in fields and str(fields["label"]).strip():
        sets.append("label = ?"); params.append(str(fields["label"]).strip())
    if fields.get("profile_key"):
        # Validasi: profil harus ada.
        exists = conn.execute(
            "SELECT 1 FROM scoring_profiles WHERE key = ?",
            (fields["profile_key"],)).fetchone()
        if exists:
            sets.append("profile_key = ?"); params.append(fields["profile_key"])
    if "sort_order" in fields and fields["sort_order"] is not None:
        sets.append("sort_order = ?"); params.append(fields["sort_order"])
    if "is_active" in fields:
        sets.append("is_active = ?"); params.append(1 if fields["is_active"] else 0)
    if not sets:
        return False
    params.append(key)
    cur = conn.execute(
        f"UPDATE work_groups SET {', '.join(sets)} WHERE key = ?", params)
    conn.commit()
    return cur.rowcount > 0


def create_group(key, label, profile_key, sort_order=None):
    """Tambah kelompok baru yang menunjuk ke `profile_key` (profil harus ada).

    Mengembalikan (ok, error). key dinormalisasi: lower, spasi->underscore.
    """
    import re
    key = re.sub(r"[^a-z0-9_]+", "_", (key or "").strip().lower()).strip("_")
    if not key:
        return False, "Kunci kelompok tidak valid."
    if not (label or "").strip():
        return False, "Nama kelompok wajib diisi."
    conn = _conn()
    if conn.execute("SELECT 1 FROM work_groups WHERE key = ?", (key,)).fetchone():
        return False, f"Kelompok '{key}' sudah ada."
    prof = conn.execute(
        "SELECT * FROM scoring_profiles WHERE key = ?", (profile_key,)).fetchone()
    if not prof:
        return False, "Profil yang dipilih tidak ada."
    prof = dict(prof)
    conn.execute(
        """INSERT INTO work_groups
             (key, label, profile_key, sort_order, is_active, is_builtin,
              cpu_floor, cpu_ideal, ram_min, ram_ideal,
              w_cpu, w_ram, w_storage, w_battery)
           VALUES (?, ?, ?, ?, 1, 0, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (key, label.strip(), profile_key,
         int(sort_order) if sort_order is not None else 500,
         prof["cpu_floor"], prof["cpu_ideal"], prof["ram_min"], prof["ram_ideal"],
         prof["w_cpu"], prof["w_ram"], prof["w_storage"], prof["w_battery"]),
    )
    conn.commit()
    return True, key


def update_settings(fields):
    """Perbarui ambang global. Hanya key yang dikenal di _DEFAULT_SETTINGS."""
    conn = _conn()
    for k in _DEFAULT_SETTINGS:
        if k in fields and fields[k] is not None:
            conn.execute(
                "INSERT INTO scoring_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (k, float(fields[k])),
            )
    conn.commit()
