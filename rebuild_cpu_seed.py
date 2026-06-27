# rebuild_cpu_seed.py — bangun ulang data/cpu_seed.csv dari dataset PassMark
# otoritatif (data/passmark_single_cpu_intel_amd.csv).
#
# Pemicu (docs/scoring-revisi-2026-06.md §C/§D.1): nilai "seed massal 2026-06" di
# cpu_seed.csv lama adalah tebakan yang menyimpang dari PassMark asli. File
# passmark_single_cpu_intel_amd.csv (4.550 baris Intel+AMD) adalah sumber resmi.
#
# CATATAN nama file menyesatkan: meski "…_single_…", kolom `CPU Mark` (kolom 3) =
# nilai MULTI-thread (persis yang dipakai cpu_benchmarks.passmark_multi & scoring).
# Kolom `Rank` = peringkat global, BUKAN single-thread. Maka passmark_single
# dikosongkan.
#
# MERGE, bukan timpa: pertahankan `cores`/`release_year` dari baris cpu_seed.csv
# lama bila cpu_key-nya cocok (CSV PassMark tak punya kedua kolom itu; cores
# dipakai fallback estimasi di docs/scoring.md §6).
#
# Jalankan: python rebuild_cpu_seed.py   (lalu: python seed_cpu.py)

import csv
import os

from scoring import normalize_cpu

_BASE = os.path.dirname(os.path.abspath(__file__))
OLD_SEED = os.path.join(_BASE, "data", "cpu_seed.csv")
PASSMARK_CSV = os.path.join(_BASE, "data", "passmark_single_cpu_intel_amd.csv")
OUT_SEED = OLD_SEED  # timpa di tempat

SOURCE = "PassMark (passmark_single_cpu_intel_amd.csv)"


def _to_int(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if s == "" or s.upper() == "NA":
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def load_old_meta(path):
    """{cpu_key: (cores, release_year)} dari cpu_seed.csv lama (yang sudah terisi)."""
    meta = {}
    if not os.path.exists(path):
        return meta
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            key = (r.get("cpu_key") or "").strip().lower()
            if not key:
                continue
            cores = _to_int(r.get("cores"))
            year = _to_int(r.get("release_year"))
            if cores is not None or year is not None:
                meta[key] = (cores, year)
    return meta


def build():
    old_meta = load_old_meta(OLD_SEED)

    # cpu_key -> dict baris terbaik (CPU Mark tertinggi pada tabrakan normalisasi).
    best = {}
    total_in = dup = 0
    with open(PASSMARK_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            name = (r.get("CPU Name") or "").strip()
            mark = _to_int(r.get("CPU Mark"))
            if not name or mark is None:
                continue
            total_in += 1
            key = normalize_cpu(name)
            if not key:
                continue
            if key in best:
                dup += 1
                if mark <= best[key]["passmark_multi"]:
                    continue
            cores, year = old_meta.get(key, (None, None))
            best[key] = {
                "cpu_key": key,
                "cpu_label": name,
                "passmark_multi": mark,
                "passmark_single": "",
                "cores": cores if cores is not None else "",
                "release_year": year if year is not None else "",
                "source": SOURCE,
            }

    rows = sorted(best.values(), key=lambda x: -x["passmark_multi"])
    cols = ["cpu_key", "cpu_label", "passmark_multi", "passmark_single",
            "cores", "release_year", "source"]
    with open(OUT_SEED, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    merged = sum(1 for v in best.values() if v["cores"] != "" or v["release_year"] != "")
    print(f"Rebuild cpu_seed.csv selesai.")
    print(f"  Sumber          : {PASSMARK_CSV}")
    print(f"  Baris masuk      : {total_in} (tabrakan normalisasi dilewati: {dup})")
    print(f"  Baris keluar     : {len(rows)} (unik cpu_key)")
    print(f"  Merge cores/year : {merged} baris mempertahankan metadata lama")
    print(f"  Output           : {OUT_SEED}")


if __name__ == "__main__":
    build()
