# scoring.py — mesin penilaian kelayakan (implementasi docs/scoring.md).
#
# Sumber kebenaran angka = docs/scoring.md. Semua ambang ditaruh sebagai
# konstanta agar mudah dikalibrasi. JANGAN sebar magic number ke modul lain.
#
# Kontrak (docs/workflow-tasks.md):
#   score_submission(sub: dict, current_year: int) -> dict
#       -> {score_spec, score_load, score_total, status,
#           status_reasons: list[str], eol_year}
#   cpu_passmark(cpu_model: str) -> tuple[int, bool]  # (skor, diperkirakan?)
#
# Catatan: `status` dikembalikan dalam bentuk enum DB ('eligible'/'upgrade'/'replace').
#
# Mandiri sebelum Sesi 1 ada: cpu_passmark() membaca tabel cpu_benchmarks bila
# DB tersedia; bila DB/tabel belum ada, fallback baca data/cpu_seed.csv langsung
# (lihat seed_cpu.py untuk membuat & mengisi tabel).

import csv
import os
import re
import sqlite3

try:
    from config import config
    _DB_PATH = config.DB_PATH
except Exception:  # config belum ada (Sesi 1 belum jalan) -> default mandiri.
    _BASE = os.path.dirname(os.path.abspath(__file__))
    _DB_PATH = os.environ.get("DB_PATH", os.path.join(_BASE, "data", "inventory.db"))

# Lokasi CSV seed (fallback bila tabel cpu_benchmarks belum ada).
CPU_SEED_CSV = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "cpu_seed.csv"
)

# ---------------------------------------------------------------------------
# §1 — Profil kebutuhan per kelompok kerja (scoring.md §1).
#   cpu_floor / cpu_ideal = skor PassMark multi-thread. ram dalam GB.
# ---------------------------------------------------------------------------
PROFILES = {
    "field":           {"cpu_floor": 8000,  "cpu_ideal": 16000, "ram_min": 8,  "ram_ideal": 16},
    "admin":           {"cpu_floor": 12000, "cpu_ideal": 18000, "ram_min": 8,  "ram_ideal": 16},
    "finance":         {"cpu_floor": 17000, "cpu_ideal": 26000, "ram_min": 16, "ram_ideal": 32},
    "data_processing": {"cpu_floor": 17000, "cpu_ideal": 26000, "ram_min": 16, "ram_ideal": 32},
    "management":      {"cpu_floor": 15000, "cpu_ideal": 24000, "ram_min": 16, "ram_ideal": 16},
    "it":              {"cpu_floor": 17000, "cpu_ideal": 24000, "ram_min": 16, "ram_ideal": 32},
}
# Profil cadangan bila work_group tak dikenal (pakai 'admin' sebagai netral).
DEFAULT_PROFILE = "admin"

# §2e — Bobot komponen Skor Spek.
WEIGHTS_DEFAULT    = {"cpu": 0.35, "ram": 0.30, "storage": 0.20, "battery": 0.15}
WEIGHTS_MANAGEMENT = {"cpu": 0.30, "ram": 0.25, "storage": 0.20, "battery": 0.25}

# §5 — EOL
BASE_LIFESPAN_YEARS = 5

# §6 — Estimasi kasar PassMark dari jumlah thread bila CPU tak dikenal.
PASSMARK_PER_THREAD = 1800

LABEL = {"eligible": "Layak", "upgrade": "Upgrade", "replace": "Ganti"}

# Nama tampilan kelompok kerja (untuk teks insight). 'other' pakai work_group_other.
WORK_GROUP_DISPLAY = {
    "field": "Lapangan/Mobilitas", "admin": "Administrasi", "finance": "Keuangan",
    "data_processing": "Pengolahan Data", "management": "Manajemen",
    "it": "IT/Development", "other": "Lainnya",
}


# ---------------------------------------------------------------------------
# Util numerik
# ---------------------------------------------------------------------------
def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _num(v):
    """Ambil angka dari nilai apa pun (string '16 GB', None, dst). None bila gagal."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(v))
    if not m:
        return None
    return float(m.group(0).replace(",", "."))


# ---------------------------------------------------------------------------
# §6 — Normalisasi & lookup CPU -> PassMark
# ---------------------------------------------------------------------------
def normalize_cpu(cpu_model: str) -> str:
    """Lowercase, buang penanda merek dagang & embel-embel, rapikan spasi."""
    s = (cpu_model or "").lower()
    s = s.replace("(r)", " ").replace("(tm)", " ").replace("(c)", " ")
    s = re.sub(r"\bcpu\b", " ", s)
    s = re.sub(r"@.*$", " ", s)            # buang "@ 2.00ghz" dst
    s = re.sub(r"\d+-?core", " ", s)        # buang "6-core"
    s = re.sub(r"\bprocessor\b", " ", s)
    s = re.sub(r"\bwith radeon graphics\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _load_cpu_table():
    """Ambil tabel benchmark sebagai dict {cpu_key: passmark_multi}.

    DB cpu_benchmarks diutamakan; bila DB/tabel tak ada -> fallback CSV seed.
    Hasil di-cache supaya tidak baca berulang. Set _CPU_TABLE_CACHE=None untuk
    memaksa muat ulang (mis. di tes).
    """
    global _CPU_TABLE_CACHE
    if _CPU_TABLE_CACHE is not None:
        return _CPU_TABLE_CACHE

    tabel = {}
    if os.path.exists(_DB_PATH):
        try:
            conn = sqlite3.connect(_DB_PATH)
            try:
                for key, pm in conn.execute(
                    "SELECT cpu_key, passmark_multi FROM cpu_benchmarks"
                ).fetchall():
                    if key and pm is not None:
                        tabel[key] = int(pm)
            finally:
                conn.close()
        except sqlite3.Error:
            tabel = {}

    if not tabel and os.path.exists(CPU_SEED_CSV):
        # Fallback mandiri: baca CSV langsung (sebelum Sesi 1 / DB ada).
        with open(CPU_SEED_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                key = (row.get("cpu_key") or "").strip().lower()
                pm = row.get("passmark_multi")
                if key and pm not in (None, ""):
                    try:
                        tabel[key] = int(pm)
                    except ValueError:
                        continue

    _CPU_TABLE_CACHE = tabel
    return tabel


_CPU_TABLE_CACHE = None


def cpu_passmark(cpu_model: str):
    """Lookup PassMark multi-thread untuk `cpu_model`.

    Mengembalikan (passmark:int, diperkirakan:bool).
      - Cocok tabel cpu_benchmarks/CSV (exact lalu fuzzy) -> (skor, False).
      - Tak ketemu -> (0, True). Estimasi berbasis jumlah thread (§6) dilakukan
        di score_submission() yang punya cpu_threads/cpu_cores.
    """
    key = normalize_cpu(cpu_model)
    if not key:
        return 0, True
    tabel = _load_cpu_table()

    # 1) exact
    if key in tabel:
        return int(tabel[key]), False
    # 2) fuzzy: salah satu mengandung yang lain.
    for tk, pm in tabel.items():
        if tk and (tk in key or key in tk):
            return int(pm), False
    # 3) cocokkan via token nomor model (mis. '7530u', '1335u', '155h').
    model_tokens = set(re.findall(r"\b\d{3,5}[a-z]{1,3}\b", key))
    if model_tokens:
        for tk, pm in tabel.items():
            if model_tokens & set(re.findall(r"\b\d{3,5}[a-z]{1,3}\b", tk)):
                return int(pm), False
    return 0, True


# ---------------------------------------------------------------------------
# §2 — Komponen Skor Spek
# ---------------------------------------------------------------------------
def _storage_points(sub):
    """§2c — ambil storage terbaik terpasang. Return (poin, has_ssd, has_hdd)."""
    ssd_gb = _num(sub.get("ssd_gb")) or 0
    hdd_gb = _num(sub.get("hdd_gb")) or 0
    ssd_type = (sub.get("ssd_type") or "").lower()
    has_ssd = ssd_gb > 0 or bool(ssd_type.strip())
    has_hdd = hdd_gb > 0
    if has_ssd:
        return (100 if "nvme" in ssd_type else 85), True, has_hdd
    if has_hdd:
        return 25, False, True
    return 50, False, False  # tak terdeteksi -> netral


def _battery_health(sub):
    """Return health 0-100 atau None bila data baterai tak ada."""
    health = _num(sub.get("battery_health_pct"))
    if health is not None:
        return health
    full = _num(sub.get("battery_wh_full"))
    design = _num(sub.get("battery_wh_design"))
    if full and design and design > 0:
        return full / design * 100
    return None


def score_spec(sub, profile, weights):
    """§2 — Skor Spek 0-100 + komponen mentah (untuk alasan)."""
    passmark = _num(sub.get("cpu_passmark")) or 0
    ram_gb = _num(sub.get("ram_gb")) or 0

    cpu_pts = _clamp(round(100 * passmark / profile["cpu_ideal"]), 0, 100)
    ram_pts = _clamp(round(100 * ram_gb / profile["ram_ideal"]), 0, 100)
    sto_pts, has_ssd, has_hdd = _storage_points(sub)

    pts = {"cpu": cpu_pts, "ram": ram_pts, "storage": sto_pts}
    used = dict(weights)

    health = _battery_health(sub)
    if health is None:
        # §2d — baterai netral: keluarkan dari rata-rata berbobot.
        used.pop("battery", None)
        bat_pts = None
    else:
        bat_pts = _clamp(round(health), 0, 100)
        pts["battery"] = bat_pts

    total_w = sum(used.values())
    spec = sum(pts[k] * used[k] for k in used) / total_w if total_w else 0
    return round(spec), {
        "cpu_pts": cpu_pts, "ram_pts": ram_pts, "storage_pts": sto_pts,
        "battery_pts": bat_pts, "battery_health": health,
        "has_ssd": has_ssd, "has_hdd": has_hdd,
    }


# ---------------------------------------------------------------------------
# §3 — Skor Beban
# ---------------------------------------------------------------------------
def _ram_pressure(pct):
    """§3a — poin tekanan dari snapshot ram_usage_pct (float, tidak dibulatkan)."""
    if pct is None:
        return 100.0  # netral
    if pct <= 60:
        return 100.0
    if pct <= 80:
        return 100 - (pct - 60) / 20 * 30          # 100 -> 70
    if pct <= 90:
        return 70 - (pct - 80) / 10 * 30           # 70 -> 40
    return _clamp(40 - (pct - 90) / 10 * 40, 0, 40)  # 40 -> 0


def score_load(sub, profile):
    """§3 — Skor Beban 0-100."""
    pct = _num(sub.get("ram_usage_pct"))
    ram_gb = _num(sub.get("ram_gb")) or 0
    pressure = _ram_pressure(pct)
    adequacy = _clamp(round(100 * ram_gb / profile["ram_min"]), 0, 100)
    return round(0.5 * pressure + 0.5 * adequacy)


# ---------------------------------------------------------------------------
# §4 + §5 — Status, override, EOL
# ---------------------------------------------------------------------------
_RANK = {"eligible": 2, "upgrade": 1, "replace": 0}


def _lower_to(current, target):
    """Turunkan status ke `target` bila lebih rendah; tak pernah menaikkan."""
    return target if _RANK[target] < _RANK[current] else current


def status_from_total(total):
    if total >= 70:
        return "eligible"
    if total >= 45:
        return "upgrade"
    return "replace"


def score_submission(sub: dict, current_year: int) -> dict:
    """Hitung skor lengkap 1 submission. Return dict siap simpan ke DB."""
    group = sub.get("work_group") if sub.get("work_group") in PROFILES else DEFAULT_PROFILE
    profile = PROFILES[group]
    weights = WEIGHTS_MANAGEMENT if group == "management" else WEIGHTS_DEFAULT

    # Resolusi PassMark CPU: pakai nilai numerik bila sudah ada di submission;
    # bila tidak, lookup dari tabel cpu_benchmarks via cpu_passmark(). Bila tetap
    # tak dikenal -> estimasi kasar dari thread/core (§6) + tandai diperkirakan.
    sub = dict(sub)  # salinan dangkal; jangan mutasi dict pemanggil.
    cpu_estimated = bool(sub.get("cpu_estimated"))
    if _num(sub.get("cpu_passmark")) is None:
        pm, est = cpu_passmark(sub.get("cpu_model"))
        if est:
            threads = _num(sub.get("cpu_threads")) or _num(sub.get("cpu_cores"))
            pm = int(round(threads * PASSMARK_PER_THREAD)) if threads else 0
            cpu_estimated = True
        sub["cpu_passmark"] = pm
    sub["cpu_estimated"] = cpu_estimated

    spec, comp = score_spec(sub, profile, weights)
    load = score_load(sub, profile)
    total = round(0.7 * spec + 0.3 * load)

    status = status_from_total(total)
    reasons = []

    ram_gb = _num(sub.get("ram_gb")) or 0
    passmark = _num(sub.get("cpu_passmark")) or 0

    # §4b — aturan paksa.
    if ram_gb and ram_gb < profile["ram_min"]:
        status = _lower_to(status, "upgrade")
        reasons.append(
            f"RAM {int(ram_gb) if ram_gb == int(ram_gb) else ram_gb}GB di bawah minimum "
            f"{profile['ram_min']}GB untuk kelompok {group} — tambah RAM"
        )
    if comp["has_hdd"] and not comp["has_ssd"]:
        status = _lower_to(status, "upgrade")
        reasons.append("Belum SSD — ganti ke SSD")
    if passmark and passmark < profile["cpu_floor"]:
        if passmark < 0.6 * profile["cpu_floor"]:
            status = _lower_to(status, "replace")
        else:
            status = _lower_to(status, "upgrade")
        reasons.append("CPU di bawah batas bawah kelompok")
    os_free = _num(sub.get("os_free_gb"))
    if os_free is not None and os_free < 20:
        reasons.append("Penyimpanan OS hampir penuh")

    # §6 — penanda CPU diperkirakan.
    if sub.get("cpu_estimated"):
        reasons.append("Skor CPU diperkirakan (model tak dikenali) — verifikasi manual")

    # §4c — catatan komponen (flag terpisah, tidak mengubah status).
    if comp["battery_health"] is not None and comp["battery_health"] < 60:
        reasons.append(
            f"Baterai sehat {round(comp['battery_health'])}% — pertimbangkan ganti baterai"
        )

    # §5 — EOL.
    eol_year = None
    purchase_year = _num(sub.get("purchase_year"))
    if purchase_year:
        lifespan = BASE_LIFESPAN_YEARS
        if spec >= 80:
            lifespan += 1
        if spec < 55:
            lifespan -= 1
        eol_year = int(purchase_year) + lifespan

    return {
        "score_spec": spec,
        "score_load": load,
        "score_total": total,
        "status": status,
        "status_reasons": reasons,
        "eol_year": eol_year,
    }


# ---------------------------------------------------------------------------
# INSIGHT — interpretasi manusiawi dari skor & spek (untuk UI & ringkasan).
# Tidak menghitung ulang skor; membaca hasil score_submission yang sudah ada di
# `sub` (score_*, status, eol_year) + spek mentah. Aman pada baris DB mana pun.
# ---------------------------------------------------------------------------
def _fmt_int(n):
    """Format angka ribuan gaya Indonesia (titik). Mis. 16000 -> '16.000'."""
    try:
        return f"{int(round(float(n))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(n)


def _fmt_gb(n):
    """RAM/penyimpanan: buang desimal bila bulat. Mis. 16.0 -> '16'."""
    v = _num(n)
    if v is None:
        return "?"
    return str(int(v)) if v == int(v) else str(v)


def _group_display(sub):
    wg = sub.get("work_group")
    if wg == "other" and (sub.get("work_group_other") or "").strip():
        return sub["work_group_other"].strip()
    return WORK_GROUP_DISPLAY.get(wg, wg or "-")


def build_insights(sub: dict, current_year: int = None) -> dict:
    """Kembalikan dict insight siap-tampil:
        {verdict, tone, components:[{label,tone,text}], recommendations:[str],
         eol_text}
    tone ∈ {'good','warn','bad','neutral'}.
    """
    group = sub.get("work_group") if sub.get("work_group") in PROFILES else DEFAULT_PROFILE
    profile = PROFILES[group]
    grp = _group_display(sub)
    status = sub.get("status")

    components = []
    recommendations = []

    # — CPU —
    passmark = _num(sub.get("cpu_passmark")) or 0
    if passmark <= 0:
        components.append({"label": "CPU", "tone": "neutral", "text": "Skor CPU belum tersedia."})
    elif passmark >= profile["cpu_ideal"]:
        components.append({"label": "CPU", "tone": "good",
            "text": f"CPU bertenaga — di atas standar ideal kelompok {grp} "
                    f"({_fmt_int(passmark)} vs ideal {_fmt_int(profile['cpu_ideal'])} PassMark)."})
    elif passmark >= profile["cpu_floor"]:
        components.append({"label": "CPU", "tone": "good",
            "text": f"CPU memadai untuk {grp} "
                    f"({_fmt_int(passmark)} PassMark, ideal {_fmt_int(profile['cpu_ideal'])})."})
    else:
        components.append({"label": "CPU", "tone": "bad",
            "text": f"CPU di bawah batas minimum {grp} "
                    f"({_fmt_int(passmark)} vs minimum {_fmt_int(profile['cpu_floor'])} PassMark)."})
        recommendations.append("CPU di bawah kebutuhan peran — pertimbangkan ganti unit.")

    # — RAM —
    ram_gb = _num(sub.get("ram_gb")) or 0
    if ram_gb <= 0:
        components.append({"label": "RAM", "tone": "neutral", "text": "Kapasitas RAM belum tersedia."})
    elif ram_gb >= profile["ram_ideal"]:
        components.append({"label": "RAM", "tone": "good",
            "text": f"RAM {_fmt_gb(ram_gb)}GB sesuai ideal ({profile['ram_ideal']}GB) untuk {grp}."})
    elif ram_gb >= profile["ram_min"]:
        components.append({"label": "RAM", "tone": "warn",
            "text": f"RAM {_fmt_gb(ram_gb)}GB memenuhi minimum, namun di bawah ideal {profile['ram_ideal']}GB."})
        recommendations.append(f"Tambah RAM hingga {profile['ram_ideal']}GB untuk performa ideal.")
    else:
        components.append({"label": "RAM", "tone": "bad",
            "text": f"RAM {_fmt_gb(ram_gb)}GB di bawah minimum {profile['ram_min']}GB untuk {grp}."})
        recommendations.append(f"Tambah RAM minimal {profile['ram_min']}GB.")

    # — Penyimpanan —
    sto_pts, has_ssd, has_hdd = _storage_points(sub)
    ssd_type = (sub.get("ssd_type") or "").lower()
    if has_ssd and "nvme" in ssd_type:
        components.append({"label": "Penyimpanan", "tone": "good", "text": "Penyimpanan SSD NVMe (sangat cepat)."})
    elif has_ssd:
        components.append({"label": "Penyimpanan", "tone": "good", "text": "Sudah menggunakan SSD."})
    elif has_hdd:
        components.append({"label": "Penyimpanan", "tone": "bad",
            "text": "Masih memakai HDD — jauh lebih lambat dari SSD."})
        recommendations.append("Ganti penyimpanan ke SSD untuk lonjakan kecepatan terbesar.")
    else:
        components.append({"label": "Penyimpanan", "tone": "neutral", "text": "Tipe penyimpanan belum terdeteksi."})

    # — Baterai —
    health = _battery_health(sub)
    if health is None:
        # Bedakan: ada kapasitas penuh tapi desain tak terdeteksi (sehingga
        # kesehatan tak bisa dihitung) vs benar-benar tak ada data baterai.
        if _num(sub.get("battery_wh_full")) and not _num(sub.get("battery_wh_design")):
            text = "Kapasitas desain baterai tidak terdeteksi, sehingga kesehatan baterai belum dapat dihitung."
        else:
            text = "Data kesehatan baterai tidak tersedia."
        components.append({"label": "Baterai", "tone": "neutral", "text": text})
    elif health >= 80:
        components.append({"label": "Baterai", "tone": "good", "text": f"Baterai sehat ({round(health)}%)."})
    elif health >= 60:
        components.append({"label": "Baterai", "tone": "warn", "text": f"Baterai mulai menurun ({round(health)}%)."})
    else:
        components.append({"label": "Baterai", "tone": "bad", "text": f"Baterai lemah ({round(health)}%)."})
        recommendations.append("Pertimbangkan ganti baterai.")

    # — Beban RAM saat pengecekan —
    pct = _num(sub.get("ram_usage_pct"))
    if pct is None:
        components.append({"label": "Beban", "tone": "neutral", "text": "Beban RAM saat pengecekan tidak tercatat."})
    elif pct <= 60:
        components.append({"label": "Beban", "tone": "good", "text": f"Beban RAM saat dicek ringan ({round(pct)}%)."})
    elif pct <= 80:
        components.append({"label": "Beban", "tone": "warn", "text": f"Beban RAM saat dicek sedang ({round(pct)}%)."})
    else:
        components.append({"label": "Beban", "tone": "bad",
            "text": f"Beban RAM saat dicek tinggi ({round(pct)}%) — multitasking terasa berat."})

    # — Penyimpanan OS hampir penuh —
    os_free = _num(sub.get("os_free_gb"))
    if os_free is not None and os_free < 20:
        recommendations.append("Penyimpanan sistem hampir penuh — bersihkan atau tambah kapasitas.")

    # — Kondisi fisik & keluhan (catatan perawatan) —
    if sub.get("physical_condition") == "poor":
        recommendations.append("Kondisi fisik dilaporkan kurang — perlu pemeriksaan.")
    issues = (sub.get("issues") or "").strip()
    if issues and issues.lower() != "tidak ada":
        recommendations.append(f"Keluhan dilaporkan: {issues}")

    # — Verdict + tone headline —
    if status == "eligible":
        verdict = f"Laptop ini layak digunakan untuk kelompok {grp}."
        tone = "good"
    elif status == "upgrade":
        verdict = f"Laptop ini masih dapat digunakan untuk {grp}, tetapi perlu peningkatan."
        tone = "warn"
    elif status == "replace":
        verdict = f"Laptop ini kurang layak untuk {grp} dan sebaiknya diganti."
        tone = "bad"
    else:
        verdict = "Penilaian belum tersedia."
        tone = "neutral"

    if not recommendations and status == "eligible":
        recommendations.append("Tidak ada tindakan mendesak — laptop dalam kondisi baik untuk perannya.")

    # — EOL —
    eol_year = sub.get("eol_year")
    eol_text = None
    if status == "replace" or (eol_year and current_year and eol_year <= current_year):
        eol_text = "Sudah melewati estimasi masa pakai — prioritaskan penggantian."
    elif eol_year:
        eol_text = f"Estimasi layak dipakai hingga sekitar {eol_year}."

    return {
        "verdict": verdict,
        "tone": tone,
        "components": components,
        "recommendations": recommendations,
        "eol_text": eol_text,
    }


# ---------------------------------------------------------------------------
# SEED cpu_benchmarks — sumber data = data/cpu_seed.csv (angka PassMark asli
# dari cpubenchmark.net, lihat kolom `source`). Implementasi pengisian ada di
# seed_cpu.py; fungsi tipis di sini hanya delegasi agar pemanggil lama
# (mis. app.py memanggil seed_cpu_benchmarks() saat init) tetap bekerja.
# ---------------------------------------------------------------------------
def seed_cpu_benchmarks(db_path=None):
    """Buat tabel cpu_benchmarks (bila perlu) lalu isi dari data/cpu_seed.csv.

    Idempoten (aman dijalankan ulang). Mengembalikan jumlah baris di tabel.
    """
    from seed_cpu import seed_from_csv  # impor lokal: hindari siklus saat import.
    return seed_from_csv(db_path or _DB_PATH)


# ---------------------------------------------------------------------------
# Tes mandiri — cocokkan contoh §7 scoring.md (skor 81 / Layak / 2027).
# Jalankan: python scoring.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    example = {
        "work_group": "admin",
        "cpu_passmark": 16000,      # Ryzen 5 7530U
        "ram_gb": 8,
        "ssd_gb": 512, "ssd_type": "NVMe",
        "battery_wh_full": 70, "battery_wh_design": 100,  # health 70%
        "ram_usage_pct": 75,
        "purchase_year": 2022,
    }
    result = score_submission(example, current_year=2026)
    print("Hasil contoh §7:", result)
    assert result["score_spec"] == 77, result["score_spec"]
    assert result["score_load"] == 89, result["score_load"]
    assert result["score_total"] == 81, result["score_total"]
    assert result["status"] == "eligible", result["status"]
    assert result["eol_year"] == 2027, result["eol_year"]
    print("OK — semua angka cocok dengan contoh §7 scoring.md.")

    # Lookup dari tabel/CSV: Ryzen 5 7530U harus ketemu (diperkirakan=False).
    pm, est = cpu_passmark("AMD Ryzen 5 7530U with Radeon Graphics")
    print(f"cpu_passmark('AMD Ryzen 5 7530U ...') = ({pm}, diperkirakan={est})")
    assert pm > 0 and est is False, (pm, est)

    # CPU tak dikenal -> estimasi via thread, alasan ditambahkan (§6).
    result2 = score_submission({
        "work_group": "field", "cpu_model": "SuperChip XYZ 9999",
        "cpu_threads": 8, "ram_gb": 16, "ssd_type": "NVMe",
        "ram_usage_pct": 50, "purchase_year": 2024,
    }, current_year=2026)
    assert any("diperkirakan" in r for r in result2["status_reasons"]), result2
    print("OK — fallback CSV & estimasi CPU tak dikenal jalan.")
