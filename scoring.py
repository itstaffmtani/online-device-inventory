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

import scoring_config

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
# §1/§2e/§4a/§5 — Parameter skoring kini DATA-DRIVEN (lihat scoring_config.py).
#   Profil per kelompok (cpu_floor/ideal, ram_min/ideal), bobot komponen, ambang
#   status, masa pakai EOL, dan blend total dibaca dari DB (work_groups +
#   scoring_settings) supaya admin bisa kalibrasi lewat UI /admin/skoring. Nilai
#   DEFAULT/seed (identik dgn konstanta lama) ada di scoring_config._DEFAULT_*.
#   Fungsi di bawah hanya delegasi agar pemanggil lama tetap bekerja.
# ---------------------------------------------------------------------------
# Profil cadangan bila work_group tak dikenal (pakai 'admin' sebagai netral).
DEFAULT_PROFILE = scoring_config.DEFAULT_PROFILE_KEY  # 'admin'

# §6 — Estimasi kasar PassMark dari jumlah thread bila CPU tak dikenal.
PASSMARK_PER_THREAD = 1800

LABEL = {"eligible": "Layak", "upgrade": "Upgrade", "replace": "Ganti"}


def get_profiles():
    """{key: {cpu_floor, cpu_ideal, ram_min, ram_ideal}} dari DB (fallback DEFAULT)."""
    return scoring_config.get_profiles()


def get_weights():
    """{key: {cpu, ram, storage, battery}} dari DB (fallback DEFAULT)."""
    return scoring_config.get_weights()


def get_settings():
    """Ambang global (status cutoff, EOL, blend) dari DB (fallback DEFAULT)."""
    return scoring_config.get_settings()


def __getattr__(name):
    """Jaring pengaman: `scoring.PROFILES` / `WEIGHTS_DEFAULT` tetap bisa diakses
    (dinamis dari DB) untuk pemanggil lama. Disarankan pakai get_profiles()."""
    if name == "PROFILES":
        return scoring_config.get_profiles()
    if name == "WEIGHTS_DEFAULT":
        return scoring_config.get_weights().get(DEFAULT_PROFILE, {})
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _is_windows11(os_name):
    """True bila OS yang dilaporkan SUDAH Windows 11 (maka flag kesiapan tak relevan)."""
    s = (os_name or "").lower()
    return "windows" in s and "11" in s


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


def os_supported(os_name) -> bool:
    """§9 (D2) — apakah OS masih didukung vendor?

    Mengembalikan:
      - False  -> Windows 10/8/7 (Windows 10 EOL Okt 2025).
      - True   -> Windows 11 atau macOS/Linux modern.
      - None   -> tidak jelas / tak terdeteksi.
    """
    s = (os_name or "").lower()
    if not s.strip():
        return None
    if "windows" in s:
        # Windows tak didukung lagi: 10, 8.1, 8, 7 (dan versi lebih lama).
        if re.search(r"\b(10|8\.1|8|7|xp|vista)\b", s):
            return False
        if "11" in s:
            return True
        # "Windows" tanpa versi jelas -> tak bisa dipastikan.
        return None
    # OS non-Windows modern (macOS/Linux/ChromeOS) dianggap masih didukung.
    if any(k in s for k in ("mac", "darwin", "linux", "ubuntu", "debian",
                            "fedora", "chrome", "bsd")):
        return True
    return None


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

    # §2c (D1) — kesehatan disk mengali poin storage. Netral (faktor 1.0) bila
    # disk_health_pct tak diketahui (None), sehingga contoh §7 tetap 100.
    disk_health = _num(sub.get("disk_health_pct"))
    if disk_health is not None:
        sto_pts = round(sto_pts * _clamp(disk_health / 100, 0.5, 1.0))

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


def _cpu_pressure(pct):
    """§3a — poin tekanan dari snapshot cpu_usage_pct (rata-rata ~3s).

    CPU wajar melonjak sesaat, jadi ambangnya sedikit lebih longgar dari RAM.
    Tinggi-berkelanjutan = laptop ngos-ngosan untuk beban kerjanya.
    """
    if pct is None:
        return 100.0  # netral
    if pct <= 60:
        return 100.0
    if pct <= 80:
        return 100 - (pct - 60) / 20 * 30          # 100 -> 70
    if pct <= 92:
        return 70 - (pct - 80) / 12 * 30           # 70 -> 40
    return _clamp(40 - (pct - 92) / 8 * 40, 0, 40)   # 40 -> 0


def score_load(sub, profile):
    """§3 — Skor Beban 0-100.

    Tekanan = rata-rata sinyal beban NYATA yang tersedia (RAM terpakai + CPU
    terpakai). Hanya sinyal yang ada datanya yang dirata-rata, sehingga submission
    lama (tanpa cpu_usage_pct) tetap memakai tekanan RAM saja — angka tidak
    berubah. Kecukupan = RAM fisik vs kebutuhan minimum peran.
    """
    ram_pct = _num(sub.get("ram_usage_pct"))
    cpu_pct = _num(sub.get("cpu_usage_pct"))
    ram_gb = _num(sub.get("ram_gb")) or 0

    parts = []
    if ram_pct is not None:
        parts.append(_ram_pressure(ram_pct))
    if cpu_pct is not None:
        parts.append(_cpu_pressure(cpu_pct))
    pressure = sum(parts) / len(parts) if parts else 100.0

    adequacy = _clamp(round(100 * ram_gb / profile["ram_min"]), 0, 100)
    return round(0.5 * pressure + 0.5 * adequacy)


# ---------------------------------------------------------------------------
# §4 + §5 — Status, override, EOL
# ---------------------------------------------------------------------------
_RANK = {"eligible": 2, "upgrade": 1, "replace": 0}


def _lower_to(current, target):
    """Turunkan status ke `target` bila lebih rendah; tak pernah menaikkan."""
    return target if _RANK[target] < _RANK[current] else current


def status_from_total(total, settings=None):
    """Status dari Skor Total memakai ambang dari DB (scoring_settings)."""
    s = settings or scoring_config.get_settings()
    if total >= s["status_eligible_min"]:
        return "eligible"
    if total >= s["status_upgrade_min"]:
        return "upgrade"
    return "replace"


# ---------------------------------------------------------------------------
# VONIS 2 SUMBU — Skor Spek (kapasitas optimal) × Skor Beban (kenyataan lapangan)
#   Memisahkan "secara hardware layak?" dari "nyatanya kewalahan?". Berguna untuk
#   membongkar perkiraan peran yang meleset:
#     - spek layak TAPI beban berat  -> kerjaan lebih berat dari dugaan (upgrade)
#     - spek kurang TAPI beban ringan -> masih nyaman dipakai (jangan buru ganti)
#   Ambang biner pakai status_eligible_min (sama dgn "Layak") untuk kedua sumbu.
#   Tidak menghitung ulang skor; murni interpretasi dari score_spec & score_load.
# ---------------------------------------------------------------------------
def two_axis_verdict(score_spec, score_load, settings=None):
    """Kembalikan vonis gabungan 2 sumbu (dict siap-tampil) atau None.

    Return {
      spec_ok, load_ok: bool,
      quadrant: 'fit'|'overloaded'|'oversized'|'poor',
      tone: 'good'|'warn'|'bad',
      headline: str,         # kalimat vonis gabungan
    }
    None bila salah satu skor belum tersedia.
    """
    if score_spec is None or score_load is None:
        return None
    s = settings or scoring_config.get_settings()
    ok = s["status_eligible_min"]
    spec_ok = score_spec >= ok
    load_ok = score_load >= ok

    if spec_ok and load_ok:
        quadrant, tone = "fit", "good"
        headline = ("Layak — spek memadai untuk perannya dan beban kerja nyata "
                    "masih ringan.")
    elif spec_ok and not load_ok:
        quadrant, tone = "overloaded", "warn"
        headline = ("Secara spek layak, tetapi beban kerja nyata BERAT — kemungkinan "
                    "tugasnya lebih berat dari perkiraan peran. Pertimbangkan upgrade.")
    elif not spec_ok and load_ok:
        quadrant, tone = "oversized", "warn"
        headline = ("Secara spek di bawah standar peran, tetapi nyatanya beban "
                    "ringan — masih nyaman dipakai, penggantian tidak mendesak.")
    else:
        quadrant, tone = "poor", "bad"
        headline = ("Spek di bawah standar peran DAN beban nyata berat — "
                    "prioritas upgrade/penggantian.")

    return {
        "spec_ok": spec_ok, "load_ok": load_ok,
        "quadrant": quadrant, "tone": tone, "headline": headline,
    }


def score_submission(sub: dict, current_year: int) -> dict:
    """Hitung skor lengkap 1 submission. Return dict siap simpan ke DB."""
    profiles = scoring_config.get_profiles()
    weights_map = scoring_config.get_weights()
    settings = scoring_config.get_settings()
    group = sub.get("work_group") if sub.get("work_group") in profiles else DEFAULT_PROFILE
    profile = profiles.get(group) or profiles[DEFAULT_PROFILE]
    weights = (weights_map.get(group) or weights_map.get(DEFAULT_PROFILE)
               or {"cpu": 0.35, "ram": 0.30, "storage": 0.20, "battery": 0.15})

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
    total = round(settings["blend_spec"] * spec + settings["blend_load"] * load)

    status = status_from_total(total, settings)
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
            f"Kesehatan baterai {round(comp['battery_health'])}% — pertimbangkan ganti baterai"
        )

    # §9 (D1) — kesehatan disk rendah: flag perawatan, tidak memaksa status.
    disk_health = _num(sub.get("disk_health_pct"))
    if disk_health is not None and disk_health < 50:
        reasons.append(
            f"Kesehatan disk {round(disk_health)}% — cadangkan data & "
            f"pertimbangkan ganti disk"
        )

    # §9 (D2) — dukungan OS: Windows 10 habis dukungan (Okt 2025).
    if os_supported(sub.get("os_name")) is False:
        reasons.append(
            "Windows 10 sudah habis dukungan (Okt 2025) — rencanakan "
            "migrasi/ganti ke Windows 11"
        )

    # §9 (D3) — kesiapan Windows 11 (indikasi): flag + rekomendasi.
    # Disembunyikan bila OS SUDAH Windows 11 (flag tak relevan; mencegah false
    # negative dari collector tanpa hak admin yang gagal baca TPM/Secure Boot).
    win11_ready = sub.get("win11_ready")
    if (win11_ready is not None and str(win11_ready) == "0"
            and not _is_windows11(sub.get("os_name"))):
        blockers = (sub.get("win11_blockers") or "").strip() or "syarat tidak terpenuhi"
        reasons.append(
            f"Belum memenuhi syarat Windows 11 (indikasi): {blockers}"
        )

    # §3c — vonis 2 sumbu (spek vs beban nyata): bila spek & beban tidak sejalan,
    # tambahkan alasan yang membongkar perkiraan peran. Tidak memaksa status —
    # beban nyata sudah ikut menarik Skor Total lewat score_load (blend §0).
    verdict = two_axis_verdict(spec, load, settings)
    if verdict and verdict["quadrant"] in ("overloaded", "oversized"):
        cpu_use = _num(sub.get("cpu_usage_pct"))
        ram_use = _num(sub.get("ram_usage_pct"))
        bits = []
        if cpu_use is not None:
            bits.append(f"CPU {round(cpu_use)}%")
        if ram_use is not None:
            bits.append(f"RAM {round(ram_use)}%")
        snap = f" ({', '.join(bits)} saat dicek)" if bits else ""
        if verdict["quadrant"] == "overloaded":
            reasons.append(
                f"Secara spek memadai, tetapi beban kerja nyata berat{snap} — "
                f"kemungkinan lebih berat dari perkiraan peran {group}; "
                f"pertimbangkan upgrade"
            )
        else:  # oversized
            reasons.append(
                f"Spek di bawah standar peran {group}, namun beban nyata ringan{snap} "
                f"— penggantian tidak mendesak"
            )

    # §5 — EOL.
    eol_year = None
    purchase_year = _num(sub.get("purchase_year"))
    if purchase_year:
        lifespan = int(round(settings["base_lifespan_years"]))
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
    return scoring_config.get_labels().get(wg, wg or "-")


def build_insights(sub: dict, current_year: int = None) -> dict:
    """Kembalikan dict insight siap-tampil:
        {verdict, tone, components:[{label,tone,text}], recommendations:[str],
         eol_text}
    tone ∈ {'good','warn','bad','neutral'}.
    """
    profiles = scoring_config.get_profiles()
    group = sub.get("work_group") if sub.get("work_group") in profiles else DEFAULT_PROFILE
    profile = profiles.get(group) or profiles[DEFAULT_PROFILE]
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

    # — Kesehatan Disk (D4) —
    disk_health = _num(sub.get("disk_health_pct"))
    disk_raw = (sub.get("disk_health_raw") or "").strip()
    if disk_health is None:
        components.append({"label": "Kesehatan Disk", "tone": "neutral",
            "text": "Data kesehatan disk tidak tersedia."})
    else:
        dh = round(disk_health)
        suffix = f" ({disk_raw})" if disk_raw else ""
        if disk_health >= 70:
            components.append({"label": "Kesehatan Disk", "tone": "good",
                "text": f"Disk sehat ({dh}%){suffix}."})
        elif disk_health >= 40:
            components.append({"label": "Kesehatan Disk", "tone": "warn",
                "text": f"Kesehatan disk menurun ({dh}%){suffix} — pantau berkala."})
        else:
            components.append({"label": "Kesehatan Disk", "tone": "bad",
                "text": f"Kesehatan disk lemah ({dh}%){suffix}."})
            recommendations.append(
                f"Kesehatan disk {dh}% — cadangkan data & pertimbangkan ganti disk.")

    # — Dukungan OS (D4) —
    os_ok = os_supported(sub.get("os_name"))
    if os_ok is True:
        components.append({"label": "Dukungan OS", "tone": "good",
            "text": "Sistem operasi masih didukung vendor."})
    elif os_ok is False:
        components.append({"label": "Dukungan OS", "tone": "bad",
            "text": "Windows 10 habis dukungan (Okt 2025) — rencanakan migrasi ke Windows 11."})
        recommendations.append(
            "Windows 10 sudah habis dukungan — rencanakan migrasi/ganti ke Windows 11.")
    else:
        components.append({"label": "Dukungan OS", "tone": "neutral",
            "text": "Status dukungan sistem operasi belum dapat dipastikan."})

    # — Windows 11 (D4) — sembunyikan untuk non-Windows yang OS-nya jelas bukan Windows.
    os_is_windows = "windows" in (sub.get("os_name") or "").lower()
    win11_ready = sub.get("win11_ready")
    win11_blockers = (sub.get("win11_blockers") or "").strip()
    if _is_windows11(sub.get("os_name")):
        # OS sudah Windows 11 -> flag kesiapan tak relevan (cegah false negative
        # dari collector tanpa hak admin yang gagal baca TPM/Secure Boot).
        components.append({"label": "Windows 11", "tone": "good",
            "text": "Sudah menjalankan Windows 11."})
    elif win11_ready is None:
        # Tampilkan netral hanya bila memang Windows atau OS tak jelas;
        # untuk OS jelas non-Windows, lewati komponen ini.
        if os_is_windows or not (sub.get("os_name") or "").strip():
            components.append({"label": "Windows 11", "tone": "neutral",
                "text": "Kesiapan Windows 11 belum terdeteksi."})
    elif str(win11_ready) == "1":
        components.append({"label": "Windows 11", "tone": "good",
            "text": "Memenuhi syarat (indikasi) untuk Windows 11."})
    else:
        blk = f": {win11_blockers}" if win11_blockers else ""
        components.append({"label": "Windows 11", "tone": "warn",
            "text": f"Belum memenuhi syarat Windows 11 (indikasi){blk}."})
        recommendations.append(
            f"Belum siap Windows 11 (indikasi){blk} — periksa TPM/Secure Boot/RAM.")

    # — Headroom RAM (D4) — peluang upgrade RAM bila masih ada slot kosong.
    slots_total = _num(sub.get("ram_slots_total"))
    slots_used = _num(sub.get("ram_slots_used"))
    ram_max_gb = _num(sub.get("ram_max_gb"))
    if slots_total or slots_used or ram_max_gb:
        st = int(slots_total) if slots_total else None
        su = int(slots_used) if slots_used else None
        has_free_slot = (st is not None and su is not None and su < st)
        below_max = (ram_max_gb is not None and ram_gb > 0 and ram_gb < ram_max_gb)
        slot_txt = (f"{su}/{st} slot" if (st is not None and su is not None)
                    else (f"{su} slot terpakai" if su is not None else f"{st} slot"))
        max_txt = f", maks {_fmt_gb(ram_max_gb)}GB" if ram_max_gb else ""
        if has_free_slot and below_max:
            components.append({"label": "Headroom RAM", "tone": "good",
                "text": f"Masih bisa tambah RAM: {slot_txt}{max_txt}."})
            # Rekomendasi actionable bila RAM di bawah ideal & ada headroom.
            if ram_gb and ram_gb < profile["ram_ideal"]:
                recommendations.append(
                    f"Tambah RAM hingga {profile['ram_ideal']}GB — tersedia slot kosong.")
        else:
            components.append({"label": "Headroom RAM", "tone": "neutral",
                "text": f"RAM {_fmt_gb(ram_gb)}GB di {slot_txt}{max_txt}."})

    # — Beban RAM saat pengecekan —
    pct = _num(sub.get("ram_usage_pct"))
    if pct is None:
        components.append({"label": "Beban RAM", "tone": "neutral", "text": "Beban RAM saat pengecekan tidak tercatat."})
    elif pct <= 60:
        components.append({"label": "Beban RAM", "tone": "good", "text": f"Beban RAM saat dicek ringan ({round(pct)}%)."})
    elif pct <= 80:
        components.append({"label": "Beban RAM", "tone": "warn", "text": f"Beban RAM saat dicek sedang ({round(pct)}%)."})
    else:
        components.append({"label": "Beban RAM", "tone": "bad",
            "text": f"Beban RAM saat dicek tinggi ({round(pct)}%) — multitasking terasa berat."})

    # — Beban CPU saat pengecekan (rata-rata ~3s) —
    cpu_pct = _num(sub.get("cpu_usage_pct"))
    if cpu_pct is None:
        components.append({"label": "Beban CPU", "tone": "neutral",
            "text": "Beban CPU saat pengecekan tidak tercatat."})
    elif cpu_pct <= 60:
        components.append({"label": "Beban CPU", "tone": "good",
            "text": f"Beban CPU saat dicek ringan ({round(cpu_pct)}%)."})
    elif cpu_pct <= 80:
        components.append({"label": "Beban CPU", "tone": "warn",
            "text": f"Beban CPU saat dicek sedang ({round(cpu_pct)}%)."})
    else:
        components.append({"label": "Beban CPU", "tone": "bad",
            "text": f"Beban CPU saat dicek tinggi ({round(cpu_pct)}%) — prosesor sering mentok."})

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

    # — Vonis 2 sumbu (spek vs beban nyata) untuk ditampilkan menonjol —
    two_axis = two_axis_verdict(sub.get("score_spec"), sub.get("score_load"))

    return {
        "verdict": verdict,
        "tone": tone,
        "components": components,
        "recommendations": recommendations,
        "eol_text": eol_text,
        "two_axis": two_axis,
    }


# ---------------------------------------------------------------------------
# SARAN PENEMPATAN ULANG (rightsizing) — "laptop ini kurang untuk Keuangan,
# tapi cocok untuk Administrasi". Menilai spek laptop terhadap SEMUA kelompok
# kerja, lalu menyarankan kelompok yang paling pas. Tidak mengubah data; hanya
# membaca spek + cpu_passmark yang sudah tersimpan pada submission.
# ---------------------------------------------------------------------------
def _total_for_profile(sub, profile, weights, settings):
    spec, _ = score_spec(sub, profile, weights)
    load = score_load(sub, profile)
    total = round(settings["blend_spec"] * spec + settings["blend_load"] * load)
    return total


def suggest_placement(sub, current_year=None):
    """Saran penempatan ulang berbasis spek vs kebutuhan tiap kelompok.

    Kembalikan dict:
      {
        current:  {"key", "label", "status", "total"},
        eligible: [ {"key","label","total","cpu_ideal"} ... ]  # kelompok yg 'Layak'
        suggestion: {"key","label","total"} | None  # best-fit selain kelompok kini
        text: str | None  # kalimat siap-tampil
      }
    `eligible` diurut dari kebutuhan TERBERAT yang masih layak (utilisasi terbaik).
    """
    profiles = get_profiles()
    weights_map = get_weights()
    settings = get_settings()
    labels = scoring_config.get_labels()

    cur_key = sub.get("work_group") if sub.get("work_group") in profiles else DEFAULT_PROFILE
    cur_profile = profiles.get(cur_key) or profiles[DEFAULT_PROFILE]
    cur_weights = (weights_map.get(cur_key) or weights_map.get(DEFAULT_PROFILE)
                   or {"cpu": 0.35, "ram": 0.30, "storage": 0.20, "battery": 0.15})
    cur_total = _total_for_profile(sub, cur_profile, cur_weights, settings)
    cur_status = status_from_total(cur_total, settings)

    # Nilai laptop terhadap tiap kelompok (kecuali 'other' = teks bebas).
    eligible = []
    for key, prof in profiles.items():
        if key == "other":
            continue
        w = weights_map.get(key) or cur_weights
        total = _total_for_profile(sub, prof, w, settings)
        if status_from_total(total, settings) == "eligible":
            eligible.append({
                "key": key, "label": labels.get(key, key), "total": total,
                "cpu_ideal": prof.get("cpu_ideal", 0),
            })
    # Urut: kebutuhan terberat (cpu_ideal) lebih dulu -> utilisasi maksimal.
    eligible.sort(key=lambda e: (e["cpu_ideal"], e["total"]), reverse=True)

    # Best-fit = kelompok layak yang BUKAN kelompok sekarang.
    suggestion = next((e for e in eligible if e["key"] != cur_key), None)

    cur_label = labels.get(cur_key, cur_key)
    text = None
    if cur_status == "eligible":
        # Sudah pas untuk perannya. Bila ada kelompok lebih berat yang juga layak,
        # tak perlu disarankan pindah (sudah cukup); biarkan text None.
        text = None
    elif suggestion:
        text = (f"Spek kurang untuk {cur_label}, tetapi cocok untuk "
                f"{suggestion['label']} — pertimbangkan pindah tangan.")
    else:
        text = (f"Spek di bawah kebutuhan {cur_label} dan kelompok lain — "
                f"kandidat peremajaan/penggantian.")

    return {
        "current": {"key": cur_key, "label": cur_label,
                    "status": cur_status, "total": cur_total},
        "eligible": eligible,
        "suggestion": suggestion,
        "text": text,
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

    # --- Self-test BARU (D1-D4) — tidak mengganggu assert lama ---

    # D1 — disk_health=None tidak mengubah skor contoh §7 (storage tetap 100).
    base = dict(example)
    base["disk_health_pct"] = None
    r_none = score_submission(base, current_year=2026)
    assert r_none["score_spec"] == 77, r_none["score_spec"]

    # D1 — disk_health rendah: faktor mengali storage + reason perawatan muncul,
    # tetapi status tidak dipaksa ke replace (tetap flag).
    low_disk = dict(example)
    low_disk["disk_health_pct"] = 30
    r_disk = score_submission(low_disk, current_year=2026)
    assert any("Kesehatan disk" in r for r in r_disk["status_reasons"]), r_disk
    assert r_disk["score_spec"] < 77, r_disk["score_spec"]  # storage 100->50 turun
    print("OK — D1 kesehatan disk: netral bila None, flag & turunkan storage bila rendah.")

    # D2 — Windows 10 EOL: os_supported False + reason.
    assert os_supported("Windows 10 Pro") is False
    assert os_supported("Windows 11 Home") is True
    assert os_supported("Ubuntu 22.04") is True
    assert os_supported("") is None
    win10 = dict(example)
    win10["os_name"] = "Windows 10 Pro"
    r_os = score_submission(win10, current_year=2026)
    assert any("Windows 10" in r for r in r_os["status_reasons"]), r_os
    print("OK — D2 dukungan OS: Windows 10 EOL terdeteksi + reason.")

    # D3 — win11_ready=0 -> reason indikasi muncul (tanpa memaksa status).
    nowin11 = dict(example)
    nowin11["win11_ready"] = 0
    nowin11["win11_blockers"] = "TPM bukan 2.0; Secure Boot tidak aktif"
    r_w11 = score_submission(nowin11, current_year=2026)
    assert any("Windows 11" in r for r in r_w11["status_reasons"]), r_w11
    assert r_w11["status"] == "eligible", r_w11["status"]  # tetap layak, hanya flag
    print("OK — D3 kesiapan Windows 11: reason muncul, status tidak dipaksa.")

    # D4 — komponen insight baru hadir + headroom RAM actionable.
    ins = build_insights({
        "work_group": "admin", "status": "eligible",
        "cpu_passmark": 16000, "ram_gb": 8,
        "ssd_type": "NVMe", "ssd_gb": 512,
        "disk_health_pct": 95, "disk_health_raw": "Healthy",
        "os_name": "Windows 11 Home",
        "win11_ready": 1,
        "ram_slots_total": 2, "ram_slots_used": 1, "ram_max_gb": 32,
    }, current_year=2026)
    labels = {c["label"] for c in ins["components"]}
    for need in ("Kesehatan Disk", "Dukungan OS", "Windows 11", "Headroom RAM"):
        assert need in labels, (need, labels)
    assert any("Tambah RAM hingga 16GB" in r for r in ins["recommendations"]), ins["recommendations"]
    print("OK — D4 build_insights: komponen disk/OS/Win11/headroom & rekomendasi RAM hadir.")

    # --- Self-test BARU (2 sumbu: spek vs beban nyata) ---

    # L1 — cpu_usage_pct kosong tidak mengubah Skor Beban contoh §7 (tetap 89).
    base_cpu = dict(example)
    assert "cpu_usage_pct" not in base_cpu
    r_nocpu = score_submission(base_cpu, current_year=2026)
    assert r_nocpu["score_load"] == 89, r_nocpu["score_load"]

    # L2 — CPU terpakai tinggi MENURUNKAN Skor Beban (ikut tekanan, §3a).
    hi_cpu = dict(example); hi_cpu["cpu_usage_pct"] = 95
    r_hicpu = score_submission(hi_cpu, current_year=2026)
    assert r_hicpu["score_load"] < 89, r_hicpu["score_load"]
    print("OK — L1/L2 beban CPU: netral bila kosong, turunkan Skor Beban bila tinggi.")

    # L3 — vonis 2 sumbu: spek layak + beban berat -> 'overloaded' + reason upgrade.
    overload = dict(example)
    overload["ram_usage_pct"] = 95; overload["cpu_usage_pct"] = 96
    r_over = score_submission(overload, current_year=2026)
    v_over = two_axis_verdict(r_over["score_spec"], r_over["score_load"])
    assert v_over and v_over["quadrant"] == "overloaded", v_over
    assert any("beban kerja nyata berat" in r.lower() for r in r_over["status_reasons"]), r_over
    print("OK — L3 vonis: spek layak tapi beban berat -> overloaded + alasan upgrade.")

    # L4 — vonis 2 sumbu: spek kurang + beban ringan -> 'oversized'.
    v_under = two_axis_verdict(40, 90)
    assert v_under["quadrant"] == "oversized", v_under
    v_fit = two_axis_verdict(85, 90); assert v_fit["quadrant"] == "fit", v_fit
    v_poor = two_axis_verdict(40, 30); assert v_poor["quadrant"] == "poor", v_poor
    assert two_axis_verdict(None, 90) is None
    print("OK — L4 vonis: keempat kuadran (fit/overloaded/oversized/poor) benar.")
