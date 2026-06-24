# routes_admin.py — blueprint admin (dashboard, detail+riwayat, export XLSX).
#
#   GET  /admin                 -> dashboard: ringkasan + list laptop (cari/sortir)
#   GET  /admin/device/<id>     -> detail + riwayat 1 laptop
#   GET  /admin/export.xlsx     -> export data terbaru per laptop ke Excel
#   GET/POST /admin/login       -> login 1 password bersama (ADMIN_PASSWORD)
#   GET  /admin/logout          -> keluar
#
# Auth: 1 password bersama (env ADMIN_PASSWORD) + Flask session. Tanpa tabel user.

import io
import json
from datetime import datetime
from functools import wraps

from flask import (Blueprint, Response, current_app, redirect, render_template,
                   request, session, url_for)

import db

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

WORK_GROUP_LABEL = {
    "field": "Lapangan", "admin": "Administrasi", "finance": "Keuangan",
    "data_processing": "Pengolahan Data", "management": "Manajemen", "it": "IT",
    "other": "Lainnya",
}


def group_label(row):
    """Label kelompok kerja untuk tampilan; pakai teks bebas bila 'Lainnya'."""
    wg = row.get("work_group")
    if wg == "other" and (row.get("work_group_other") or "").strip():
        return row["work_group_other"].strip()
    return WORK_GROUP_LABEL.get(wg, wg or "-")
STATUS_LABEL = {"eligible": "Layak", "upgrade": "Upgrade", "replace": "Ganti"}
_STATUS_RANK = {"replace": 0, "upgrade": 1, "eligible": 2}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def _parse_reasons(raw):
    if not raw:
        return []
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else [str(val)]
    except (ValueError, TypeError):
        return [raw]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == current_app.config["ADMIN_PASSWORD"]:
            session["admin"] = True
            nxt = request.args.get("next") or url_for("admin.dashboard")
            return redirect(nxt)
        error = "Password salah."
    return render_template("admin/login.html", error=error)


@admin_bp.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("admin.login"))


# ---------------------------------------------------------------------------
# Dashboard + list
# ---------------------------------------------------------------------------
@admin_bp.route("/")
@login_required
def dashboard():
    rows = db.latest_per_device()
    for r in rows:
        r["_reasons"] = _parse_reasons(r.get("status_reasons"))

    # Ringkasan.
    summary = {
        "total": len(rows),
        "per_status": {"eligible": 0, "upgrade": 0, "replace": 0},
        "per_group": {},
        "per_company": {},
    }
    for r in rows:
        st = r.get("status")
        if st in summary["per_status"]:
            summary["per_status"][st] += 1
        grp = r.get("work_group") or "-"
        summary["per_group"][grp] = summary["per_group"].get(grp, 0) + 1
        comp = r.get("holder_company") or "-"
        summary["per_company"][comp] = summary["per_company"].get(comp, 0) + 1

    # Cari.
    q = (request.args.get("q") or "").strip().lower()
    if q:
        def match(r):
            hay = " ".join(str(r.get(k) or "") for k in (
                "holder_name", "serial_number", "device_serial", "device_brand",
                "device_model", "work_group", "holder_company", "asset_no"))
            return q in hay.lower()
        rows = [r for r in rows if match(r)]

    # Sortir.
    sort = request.args.get("sort", "last_seen")
    direction = request.args.get("dir", "desc")
    keyfuncs = {
        "name": lambda r: (r.get("holder_name") or "").lower(),
        "serial": lambda r: (r.get("serial_number") or r.get("device_serial") or "").lower(),
        "brand": lambda r: (r.get("device_brand") or "").lower(),
        "status": lambda r: _STATUS_RANK.get(r.get("status"), -1),
        "score": lambda r: r.get("score_total") if r.get("score_total") is not None else -1,
        "group": lambda r: r.get("work_group") or "",
        "last_seen": lambda r: r.get("submitted_at") or "",
    }
    keyf = keyfuncs.get(sort, keyfuncs["last_seen"])
    rows.sort(key=keyf, reverse=(direction == "desc"))

    return render_template("admin/dashboard.html", rows=rows, summary=summary,
                           q=request.args.get("q", ""), sort=sort, dir=direction,
                           wg_label=WORK_GROUP_LABEL, group_label=group_label,
                           status_label=STATUS_LABEL)


@admin_bp.route("/device/<int:device_id>")
@login_required
def device_detail(device_id):
    data = db.device_with_history(device_id)
    if not data.get("device"):
        return Response("Device tidak ditemukan.", status=404)
    for s in data["submissions"]:
        s["_reasons"] = _parse_reasons(s.get("status_reasons"))
    return render_template("admin/detail.html", device=data["device"],
                           submissions=data["submissions"], latest=data["submissions"][0] if data["submissions"] else None,
                           wg_label=WORK_GROUP_LABEL, group_label=group_label,
                           status_label=STATUS_LABEL)


# ---------------------------------------------------------------------------
# Export XLSX (data terbaru per laptop) — anti formula injection.
# ---------------------------------------------------------------------------
_EXPORT_COLUMNS = [
    ("submitted_at", "Waktu"),
    ("holder_name", "Nama"),
    ("work_group", "Kelompok"),
    ("holder_position", "Jabatan"),
    ("holder_company", "Perusahaan"),
    ("holder_location", "Penempatan"),
    ("laptop_status", "Status Laptop"),
    ("serial_number", "Serial"),
    ("asset_no", "No Asset"),
    ("device_brand", "Merk"),
    ("device_model", "Model"),
    ("cpu_model", "CPU"),
    ("cpu_passmark", "PassMark"),
    ("ram_gb", "RAM (GB)"),
    ("ssd_gb", "SSD (GB)"),
    ("ssd_type", "Tipe SSD"),
    ("hdd_gb", "HDD (GB)"),
    ("os_name", "OS"),
    ("battery_health_pct", "Baterai Sehat (%)"),
    ("physical_condition", "Kondisi Fisik"),
    ("accessories", "Kelengkapan"),
    ("purchase_year", "Tahun Beli"),
    ("issues", "Kerusakan"),
    ("score_spec", "Skor Spek"),
    ("score_load", "Skor Beban"),
    ("score_total", "Skor Total"),
    ("status", "Status"),
    ("eol_year", "Estimasi Pensiun"),
    ("status_reasons", "Alasan"),
]


def _sanitize(val):
    """Cegah CSV/Excel formula injection: prefix ' bila diawali = + - @."""
    if val is None:
        return ""
    s = str(val)
    if s and s[0] in ("=", "+", "-", "@"):
        return "'" + s
    return s


@admin_bp.route("/export.xlsx")
@login_required
def export_xlsx():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    rows = db.latest_per_device()
    wb = Workbook()
    ws = wb.active
    ws.title = "Inventaris Laptop"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="4F46E5")
    for col, (_key, label) in enumerate(_EXPORT_COLUMNS, 1):
        c = ws.cell(row=1, column=col, value=label)
        c.font = header_font
        c.fill = header_fill

    for ri, r in enumerate(rows, 2):
        for ci, (key, _label) in enumerate(_EXPORT_COLUMNS, 1):
            if key == "status_reasons":
                value = "; ".join(_parse_reasons(r.get("status_reasons")))
            elif key == "work_group":
                value = group_label(r)
            elif key == "status":
                value = STATUS_LABEL.get(r.get("status"), r.get("status"))
            else:
                value = r.get(key)
            ws.cell(row=ri, column=ci, value=_sanitize(value))

    # Lebar kolom sederhana.
    for col, (_k, label) in enumerate(_EXPORT_COLUMNS, 1):
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = max(12, len(label) + 2)
    ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"inventaris-laptop-{datetime.now().strftime('%Y%m%d')}.xlsx"
    return Response(
        buf.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )
