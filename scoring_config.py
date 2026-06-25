# scoring_config.py — parameter skoring & kelompok kerja yang DATA-DRIVEN (DB).
#
# Sebelumnya angka skoring di-hardcode di scoring.py (PROFILES/WEIGHTS) dan daftar
# kelompok kerja dikunci CHECK di submissions. Mulai sekarang keduanya disimpan di
# DB agar admin bisa mengubah lewat UI (/admin/skoring) tanpa sentuh kode.
#
# Sumber kebenaran ANGKA tetap docs/scoring.md; nilai DEFAULT di bawah = seed awal
# (sama persis dgn konstanta lama). Bila tabel/DB belum ada, loader otomatis
# fallback ke DEFAULT sehingga scoring tetap jalan (mis. saat self-test scoring.py).
#
# Tabel:
#   work_groups      — 1 baris per kelompok kerja (profil + bobot + label).
#   scoring_settings — key/value ambang global (status cutoff, EOL, blend).

import sqlite3

# ---------------------------------------------------------------------------
# DEFAULT — seed awal (identik dengan konstanta lama scoring.py) + 3 kelompok
# baru. Admin dapat mengubah semuanya lewat UI; nilai baru tersimpan di DB.
# Bobot: kelompok lama memakai bobot umum kecuali 'management'. Kelompok baru
# memakai placeholder yang masuk akal — WAJIB dikalibrasi admin (docs/scoring.md §8).
# ---------------------------------------------------------------------------
_W_DEFAULT = {"cpu": 0.35, "ram": 0.30, "storage": 0.20, "battery": 0.15}
_W_MANAGEMENT = {"cpu": 0.30, "ram": 0.25, "storage": 0.20, "battery": 0.25}

# Tiap entri: (key, label, cpu_floor, cpu_ideal, ram_min, ram_ideal, weights,
#              sort_order, is_builtin)
_DEFAULT_GROUPS = [
    ("field",           "Lapangan",        8000,  16000, 8,  16, _W_DEFAULT,    10,  1),
    ("admin",           "Administrasi",    12000, 18000, 8,  16, _W_DEFAULT,    20,  1),
    ("finance",         "Keuangan",        17000, 26000, 16, 32, _W_DEFAULT,    30,  1),
    ("data_processing", "Pengolahan Data", 17000, 26000, 16, 32, _W_DEFAULT,    40,  1),
    ("management",      "Manajemen",       15000, 24000, 16, 16, _W_MANAGEMENT, 50,  1),
    ("it",              "IT",              17000, 24000, 16, 32, _W_DEFAULT,    60,  1),
    # — Kelompok baru (placeholder; kalibrasi lewat UI) —
    ("marketing",       "Marketing/Sales", 12000, 18000, 8,  16, _W_DEFAULT,    70,  0),
    ("design",          "Design/Kreatif",  17000, 26000, 16, 32, _W_DEFAULT,    80,  0),
    ("hr",              "HR/GA",           10000, 16000, 8,  16, _W_DEFAULT,    90,  0),
    # — 'other' selalu terakhir: teks bebas (work_group_other), profil = admin —
    ("other",           "Lainnya",         12000, 18000, 8,  16, _W_DEFAULT,    999, 1),
]

# Ambang global default (scoring.md §4a, §5, §0).
_DEFAULT_SETTINGS = {
    "status_eligible_min": 70.0,   # skor >= ini -> Layak
    "status_upgrade_min":  45.0,   # skor >= ini -> Upgrade, di bawahnya -> Ganti
    "base_lifespan_years": 5.0,    # masa pakai dasar EOL
    "blend_spec":          0.7,    # bobot Skor Spek pada Skor Total
    "blend_load":          0.3,    # bobot Skor Beban pada Skor Total
}

# Kelompok cadangan bila work_group tak dikenal (profil netral).
DEFAULT_PROFILE_KEY = "admin"


# ---------------------------------------------------------------------------
# Skema + seed (idempoten)
# ---------------------------------------------------------------------------
_SCHEMA = """
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

CREATE TABLE IF NOT EXISTS scoring_settings (
    key   TEXT PRIMARY KEY,
    value REAL NOT NULL
);
"""


def ensure_tables(conn):
    """Buat tabel work_groups & scoring_settings lalu seed DEFAULT (idempoten).

    Seed memakai INSERT OR IGNORE sehingga baris yang sudah diubah admin TIDAK
    ditimpa. Aman dijalankan tiap start.
    """
    conn.executescript(_SCHEMA)
    for (key, label, cf, ci, rm, ri, w, order, builtin) in _DEFAULT_GROUPS:
        conn.execute(
            """INSERT OR IGNORE INTO work_groups
                 (key, label, cpu_floor, cpu_ideal, ram_min, ram_ideal,
                  w_cpu, w_ram, w_storage, w_battery, sort_order, is_active, is_builtin)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (key, label, cf, ci, rm, ri,
             w["cpu"], w["ram"], w["storage"], w["battery"], order, builtin),
        )
    for k, v in _DEFAULT_SETTINGS.items():
        conn.execute(
            "INSERT OR IGNORE INTO scoring_settings (key, value) VALUES (?, ?)",
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
def _rows():
    try:
        cur = _conn().execute(
            "SELECT * FROM work_groups ORDER BY sort_order, key"
        )
        return [dict(r) for r in cur.fetchall()]
    except sqlite3.Error:
        return None  # tabel belum ada -> sinyal pakai DEFAULT


def _default_rows():
    out = []
    for (key, label, cf, ci, rm, ri, w, order, builtin) in _DEFAULT_GROUPS:
        out.append({
            "key": key, "label": label, "cpu_floor": cf, "cpu_ideal": ci,
            "ram_min": rm, "ram_ideal": ri, "w_cpu": w["cpu"], "w_ram": w["ram"],
            "w_storage": w["storage"], "w_battery": w["battery"],
            "sort_order": order, "is_active": 1, "is_builtin": builtin,
        })
    return out


def all_groups(active_only=False):
    """Daftar kelompok (list dict) urut sort_order. Fallback DEFAULT bila perlu."""
    rows = _rows()
    if rows is None:
        rows = _default_rows()
    if active_only:
        rows = [r for r in rows if r.get("is_active")]
    return rows


def get_profiles():
    """{key: {cpu_floor, cpu_ideal, ram_min, ram_ideal}} — kompatibel PROFILES lama."""
    return {
        r["key"]: {
            "cpu_floor": int(r["cpu_floor"]), "cpu_ideal": int(r["cpu_ideal"]),
            "ram_min": int(r["ram_min"]), "ram_ideal": int(r["ram_ideal"]),
        }
        for r in all_groups()
    }


def get_weights():
    """{key: {cpu, ram, storage, battery}}."""
    return {
        r["key"]: {
            "cpu": float(r["w_cpu"]), "ram": float(r["w_ram"]),
            "storage": float(r["w_storage"]), "battery": float(r["w_battery"]),
        }
        for r in all_groups()
    }


def get_labels():
    """{key: label} untuk seluruh kelompok (untuk tampilan)."""
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
_NUM_FIELDS = ("cpu_floor", "cpu_ideal", "ram_min", "ram_ideal",
               "w_cpu", "w_ram", "w_storage", "w_battery", "sort_order")


def update_group(key, fields):
    """Perbarui profil/bobot/label 1 kelompok. `fields` dict sebagian kolom.

    Hanya kolom yang dikenal yang diperbarui. Mengembalikan True bila ada baris
    tersentuh.
    """
    conn = _conn()
    sets, params = [], []
    if "label" in fields and str(fields["label"]).strip():
        sets.append("label = ?"); params.append(str(fields["label"]).strip())
    for col in _NUM_FIELDS:
        if col in fields and fields[col] is not None:
            sets.append(f"{col} = ?"); params.append(fields[col])
    if "is_active" in fields:
        sets.append("is_active = ?"); params.append(1 if fields["is_active"] else 0)
    if not sets:
        return False
    params.append(key)
    cur = conn.execute(f"UPDATE work_groups SET {', '.join(sets)} WHERE key = ?", params)
    conn.commit()
    return cur.rowcount > 0


def create_group(key, label, profile):
    """Tambah kelompok baru. `profile` dict (cpu_floor..w_battery, sort_order opsional).

    Mengembalikan (ok, error). key dinormalisasi: lower, spasi->underscore.
    """
    import re
    key = re.sub(r"[^a-z0-9_]+", "_", (key or "").strip().lower()).strip("_")
    if not key:
        return False, "Kunci kelompok tidak valid."
    if not (label or "").strip():
        return False, "Nama kelompok wajib diisi."
    conn = _conn()
    exists = conn.execute("SELECT 1 FROM work_groups WHERE key = ?", (key,)).fetchone()
    if exists:
        return False, f"Kelompok '{key}' sudah ada."
    p = dict(profile or {})
    conn.execute(
        """INSERT INTO work_groups
             (key, label, cpu_floor, cpu_ideal, ram_min, ram_ideal,
              w_cpu, w_ram, w_storage, w_battery, sort_order, is_active, is_builtin)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0)""",
        (key, label.strip(),
         int(p.get("cpu_floor", 12000)), int(p.get("cpu_ideal", 18000)),
         int(p.get("ram_min", 8)), int(p.get("ram_ideal", 16)),
         float(p.get("w_cpu", 0.35)), float(p.get("w_ram", 0.30)),
         float(p.get("w_storage", 0.20)), float(p.get("w_battery", 0.15)),
         int(p.get("sort_order", 500))),
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
