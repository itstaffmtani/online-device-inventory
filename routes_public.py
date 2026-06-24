# routes_public.py — blueprint publik (form pengisian + submit + unduh collector).
#
#   GET  /form           -> wizard pengisian (auto-prefill dari URL + inject token)
#   POST /api/submit     -> validasi token, cocokkan device, skor, simpan
#   GET  /dl/<os_name>   -> unduh file collector (windows/mac/linux)
#   GET  /terima-kasih   -> halaman konfirmasi
#
# ACUAN NAMA FIELD: docs/schema.dbml (kolom DB) & docs/architecture.md (param URL).
# Pemetaan param-URL/form -> kolom DB dipusatkan di SPEC_MAP agar 1 sumber kebenaran.

import json
import os
from datetime import datetime

from flask import (Blueprint, Response, current_app, jsonify, render_template,
                   request)

import db
from scoring import PASSMARK_PER_THREAD, cpu_passmark, score_submission

public_bp = Blueprint("public", __name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

WORK_GROUPS = ["field", "admin", "finance", "data_processing", "management", "it", "other"]

# Param URL/form (architecture.md)  ->  kolom DB submissions (schema.dbml).
SPEC_MAP = {
    "hostname": "hostname",
    "mac": "mac_address",
    "serial": "serial_number",
    "cpu": "cpu_model",
    "cpu_cores": "cpu_cores",
    "cpu_threads": "cpu_threads",
    "cpu_arch": "cpu_arch",
    "cpu_speed_mhz": "cpu_speed_mhz",
    "gpu": "gpu",
    "ram_gb": "ram_gb",
    "ram_type": "ram_type",
    "ram_speed_mhz": "ram_speed_mhz",
    "ram_usage_pct": "ram_usage_pct",
    "ram_usage_gb": "ram_usage_gb",
    "ssd_gb": "ssd_gb",
    "ssd_type": "ssd_type",
    "hdd_gb": "hdd_gb",
    "os": "os_name",
    "os_total_gb": "os_total_gb",
    "os_free_gb": "os_free_gb",
    "battery_pct": "battery_pct",
    "battery_wh_full": "battery_wh_full",
    "battery_wh_design": "battery_wh_design",
}

# Kolom yang dipaksa integer / float saat simpan. (cpu_arch tetap teks.)
_INT_COLS = {"cpu_cores", "cpu_threads", "cpu_speed_mhz", "ram_speed_mhz", "purchase_year"}
_FLOAT_COLS = {"ram_gb", "ram_usage_pct", "ram_usage_gb", "ssd_gb", "hdd_gb",
               "os_total_gb", "os_free_gb", "battery_pct", "battery_wh_full", "battery_wh_design"}

_OS_FAMILY_SOURCE = {"windows": "windows_script", "macos": "mac_script", "linux": "linux_script"}


def _to_int(v):
    try:
        return int(float(str(v).replace(",", ".")))
    except (TypeError, ValueError):
        return None


def _to_float(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _os_family(os_name):
    s = (os_name or "").lower()
    if "windows" in s:
        return "windows"
    if "mac" in s or "darwin" in s or "os x" in s:
        return "macos"
    if "linux" in s or "ubuntu" in s or "debian" in s or "fedora" in s:
        return "linux"
    return None


# ---------------------------------------------------------------------------
# GET /form  — render wizard dengan prefill dari query string.
# ---------------------------------------------------------------------------
@public_bp.route("/")
def index():
    # Halaman landing: konteks + unduh collector. Form pengisian ada di /form.
    return render_template("landing.html",
                           base_url=current_app.config.get("SERVER_BASE_URL", ""))


@public_bp.route("/form")
def form():
    # Ambil hanya param spek yang dikenal (architecture.md), abaikan sisanya.
    prefill = {k: request.args.get(k, "").strip()
               for k in SPEC_MAP if request.args.get(k, "").strip()}
    # brand/model juga boleh di-prefill (level device).
    for k in ("brand", "model"):
        val = request.args.get(k, "").strip()
        if val:
            prefill[k] = val
    return render_template("index.html", prefill=prefill,
                           submit_token=current_app.config["SUBMIT_TOKEN"],
                           work_groups=WORK_GROUPS)


@public_bp.route("/thank-you")
def thank_you():
    return render_template("thank_you.html")


# ---------------------------------------------------------------------------
# POST /api/submit
# ---------------------------------------------------------------------------
@public_bp.route("/api/submit", methods=["POST"])
def api_submit():
    payload = request.get_json(silent=True) or request.form.to_dict()

    # 1. Validasi token (header atau body).
    token = request.headers.get("X-Submit-Token") or payload.get("token")
    if token != current_app.config["SUBMIT_TOKEN"]:
        return jsonify(ok=False, error="Token tidak valid."), 403

    # 2. Field wajib.
    holder_name = (payload.get("holder_name") or "").strip()
    work_group = (payload.get("work_group") or "").strip()
    work_group_other = (payload.get("work_group_other") or "").strip()
    if not holder_name:
        return jsonify(ok=False, error="Nama wajib diisi."), 400
    if work_group not in WORK_GROUPS:
        return jsonify(ok=False, error="Kelompok kerja tidak valid."), 400
    if work_group == "other" and not work_group_other:
        return jsonify(ok=False, error="Tuliskan kelompok kerja pada pilihan Lainnya."), 400

    # 3. Bangun dict submission (kolom DB).
    sub = {}
    for param, col in SPEC_MAP.items():
        if param in payload and str(payload[param]).strip() != "":
            sub[col] = str(payload[param]).strip()

    # Field pemegang & kondisi (nama field = nama kolom).
    for col in ("holder_name", "holder_position", "holder_company", "holder_location",
                "laptop_status", "asset_no", "physical_condition", "accessories", "issues"):
        val = payload.get(col)
        if val is not None and str(val).strip() != "":
            sub[col] = str(val).strip()
    sub["work_group"] = work_group
    sub["work_group_other"] = work_group_other if work_group == "other" else None
    sub["purchase_year"] = _to_int(payload.get("purchase_year"))

    # Koersi numerik.
    for col in list(sub.keys()):
        if col in _INT_COLS:
            sub[col] = _to_int(sub[col])
        elif col in _FLOAT_COLS:
            sub[col] = _to_float(sub[col])

    # 4. Tentukan os_family + source.
    os_family = _os_family(sub.get("os_name"))
    source = (payload.get("source") or "").strip()
    if source not in ("windows_script", "mac_script", "linux_script", "manual"):
        # Bila ada spek otomatis terisi -> dianggap dari script OS terkait.
        has_auto = any(payload.get(p) for p in ("cpu", "serial", "ram_gb"))
        source = _OS_FAMILY_SOURCE.get(os_family, "manual") if has_auto else "manual"
    sub["source"] = source

    # 5. Cocokkan / buat device.
    device_id = db.find_or_create_device(
        serial=sub.get("serial_number"),
        asset_no=sub.get("asset_no"),
        mac=sub.get("mac_address"),
        brand=payload.get("brand"),
        model=payload.get("model"),
        os_family=os_family,
    )
    sub["device_id"] = device_id

    # 6. Skor kelayakan. Resolusi PassMark CPU dulu agar kolom cache cpu_passmark
    #    tersimpan; score_submission akan memakai nilai numerik ini apa adanya.
    passmark, estimated = cpu_passmark(sub.get("cpu_model"))
    if estimated:  # §6 fallback: estimasi kasar dari thread/core.
        threads = _to_int(sub.get("cpu_threads")) or _to_int(sub.get("cpu_cores"))
        passmark = int(round(threads * PASSMARK_PER_THREAD)) if threads else 0
    sub["cpu_passmark"] = passmark
    sub["cpu_estimated"] = estimated  # dibaca score_submission; bukan kolom DB (diabaikan saat insert)
    result = score_submission(sub, current_year=datetime.now().year)
    sub.update(result)
    sub["status_reasons"] = json.dumps(result["status_reasons"], ensure_ascii=False)

    # 7. Simpan submission.
    submission_id = db.insert_submission(sub)

    return jsonify(
        ok=True,
        device_id=device_id,
        submission_id=submission_id,
        score_total=result["score_total"],
        score_spec=result["score_spec"],
        score_load=result["score_load"],
        status=result["status"],
        status_reasons=result["status_reasons"],
        eol_year=result["eol_year"],
    )


# ---------------------------------------------------------------------------
# GET /dl/<os_name>  — unduh collector (1 file, alamat server otomatis dibaked).
# ---------------------------------------------------------------------------
def _collector_with_base_url(path):
    """Baca file collector & ganti URL default localhost dengan SERVER_BASE_URL
    yang aktif, supaya file yang diunduh karyawan menunjuk ke server produksi."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    base_url = (current_app.config.get("SERVER_BASE_URL") or "").rstrip("/")
    if base_url and "127.0.0.1:8080" not in base_url:
        text = text.replace("http://127.0.0.1:8080", base_url)
    return text.encode("utf-8")


@public_bp.route("/dl/<os_name>")
def download_collector(os_name):
    os_name = os_name.lower()
    if os_name in ("windows", "win"):
        # Satu file .bat self-contained (polyglot batch+PowerShell) — cukup klik 2x.
        fp = os.path.join(BASE_DIR, "windows", "Check-Laptop.bat")
        if os.path.exists(fp):
            return Response(
                _collector_with_base_url(fp),
                mimetype="application/octet-stream",
                headers={"Content-Disposition": "attachment; filename=Check-Laptop.bat"},
            )
    if os_name in ("mac", "macos", "linux", "mac-linux"):
        fp = os.path.join(BASE_DIR, "mac-linux", "check-laptop.sh")
        if os.path.exists(fp):
            return Response(
                _collector_with_base_url(fp),
                mimetype="text/x-shellscript",
                headers={"Content-Disposition": "attachment; filename=check-laptop.sh"},
            )
    return Response("Collector tidak ditemukan.", status=404)
