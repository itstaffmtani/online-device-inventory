# xlsx_export.py — Export XLSX 4 sheet (Parameter · Data & Perhitungan · Ringkasan
# · Per Karyawan). NILAI dihitung di Python (mesin scoring yang sama dengan aplikasi),
# bukan rumus Excel.
#
# Kenapa nilai, bukan rumus? openpyxl menulis sel rumus TANPA hasil tersimpan
# (cache kosong). File yang diunduh dibuka Excel dalam "Protected View" yang TIDAK
# menghitung rumus -> semua sel hasil tampak KOSONG ("rumus ilang"). Hal sama
# terjadi di Excel HP, panel pratinjau, dan impor Google Sheets. Maka nilai ditulis
# langsung agar selalu tampil di aplikasi apa pun, tanpa perlu "Enable Editing".
#
# Transparansi tetap terjaga: sheet "Parameter" mendokumentasikan angka acuan, dan
# sheet "Data & Perhitungan" menampilkan SELURUH masukan mentah + parameter yang
# dipakai + poin tiap komponen + skor akhir — jadi dasar perhitungan tetap terlihat.

import scoring
import scoring_config
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

_HEADER_FONT = Font(bold=True, color="FFFFFF")
_HEADER_FILL = PatternFill("solid", fgColor="4F46E5")
_SCORE_FILL = PatternFill("solid", fgColor="FEF3C7")
_TITLE_FONT = Font(bold=True, size=12, color="3730A3")
_LABEL_FONT = Font(bold=True, color="334155")

_STATUS_LABEL = {"eligible": "Layak", "upgrade": "Upgrade", "replace": "Ganti"}
_OWNERSHIP_LABEL = {"office_inventory": "Inventaris Kantor", "personal": "Milik Pribadi"}
_CONDITION_LABEL = {"good": "Baik", "fair": "Cukup", "poor": "Kurang"}
_SOURCE_LABEL = {"windows_script": "Script Windows", "mac_script": "Script Mac",
                 "linux_script": "Script Linux", "manual": "Manual"}


def _sanitize(val):
    """Cegah CSV/Excel formula injection: prefiks ' bila teks diawali = + - @."""
    if val is None:
        return None
    s = str(val)
    if s and s[0] in ("=", "+", "-", "@"):
        return "'" + s
    return s


def _num(v):
    """Angka -> int/float; None bila kosong/tak terbaca."""
    if v is None or v == "":
        return None
    try:
        f = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return int(f) if f == int(f) else f


def _yes_no(v):
    if v in (1, "1"):
        return "Ya"
    if v in (0, "0"):
        return "Tidak"
    return None


def _laptop_text(row):
    return ((row.get("device_brand") or "") + " " + (row.get("device_model") or "")).strip() or None


def _storage_text(row):
    ssd, hdd = _num(row.get("ssd_gb")), _num(row.get("hdd_gb"))
    typ = (row.get("ssd_type") or "").strip()
    parts = []
    if ssd:
        parts.append(f"{ssd} GB SSD" + (f" ({typ})" if typ else ""))
    if hdd:
        parts.append(f"{hdd} GB HDD")
    return " + ".join(parts) or "—"


def _battery_health(row):
    h = _num(row.get("battery_health_pct"))
    if h is not None:
        return round(h)
    full, design = _num(row.get("battery_wh_full")), _num(row.get("battery_wh_design"))
    if full and design and design > 0:
        return round(full / design * 100)
    return None


# ---------------------------------------------------------------------------
# Resolusi parameter & poin komponen per baris (pakai mesin scoring yang sama)
# ---------------------------------------------------------------------------
def _params_by_group(groups):
    """{group_key: {cpu_floor,cpu_ideal,ram_min,ram_ideal,w_*}} dari daftar kelompok."""
    out = {}
    for g in groups:
        out[g["key"]] = {
            "cpu_floor": _num(g.get("cpu_floor")), "cpu_ideal": _num(g.get("cpu_ideal")),
            "ram_min": _num(g.get("ram_min")), "ram_ideal": _num(g.get("ram_ideal")),
            "w_cpu": _num(g.get("w_cpu")), "w_ram": _num(g.get("w_ram")),
            "w_storage": _num(g.get("w_storage")), "w_battery": _num(g.get("w_battery")),
        }
    return out


def _group_label(row, wg_labels):
    wg = row.get("work_group")
    if wg == "other" and (row.get("work_group_other") or "").strip():
        return row["work_group_other"].strip()
    return wg_labels.get(wg, wg or "-")


def _component_points(row, prm):
    """Poin tiap komponen (cpu/ram/storage/battery) via scoring.score_spec."""
    profile = {"cpu_ideal": prm["cpu_ideal"], "ram_ideal": prm["ram_ideal"],
               "cpu_floor": prm["cpu_floor"], "ram_min": prm["ram_min"]}
    weights = {"cpu": prm["w_cpu"], "ram": prm["w_ram"],
               "storage": prm["w_storage"], "battery": prm["w_battery"]}
    try:
        _spec, comp = scoring.score_spec(row, profile, weights)
    except Exception:
        return {"cpu": None, "ram": None, "storage": None, "battery": None}
    return {"cpu": comp.get("cpu_pts"), "ram": comp.get("ram_pts"),
            "storage": comp.get("storage_pts"), "battery": comp.get("battery_pts")}


# ---------------------------------------------------------------------------
# Sheet 1 — Parameter (acuan; mendokumentasikan angka skoring)
# ---------------------------------------------------------------------------
_GROUP_COLS = [
    ("label", "Kelompok"), ("profile_label", "Profil"),
    ("cpu_floor", "CPU min (PassMark)"), ("cpu_ideal", "CPU ideal (PassMark)"),
    ("ram_min", "RAM min (GB)"), ("ram_ideal", "RAM ideal (GB)"),
    ("w_cpu", "Bobot CPU"), ("w_ram", "Bobot RAM"),
    ("w_storage", "Bobot Storage"), ("w_battery", "Bobot Baterai"),
]


def _build_parameter(wb, groups, settings):
    ws = wb.active
    ws.title = "Parameter"
    ws.cell(row=1, column=1, value="PARAMETER SKORING (acuan perhitungan)").font = _TITLE_FONT
    ws.cell(row=2, column=1, value=(
        "Angka di bawah dipakai untuk menghitung skor di sheet 'Data & Perhitungan'. "
        "Sumber kebenaran ada di aplikasi (/admin/skoring).")).font = Font(italic=True, color="64748B")

    hdr = 4
    for ci, (_f, label) in enumerate(_GROUP_COLS, 1):
        c = ws.cell(row=hdr, column=ci, value=label)
        c.font = _HEADER_FONT
        c.fill = _HEADER_FILL
        c.alignment = Alignment(wrap_text=True, vertical="center")
    r = hdr + 1
    for g in groups:
        for ci, (f, _l) in enumerate(_GROUP_COLS, 1):
            ws.cell(row=r, column=ci,
                    value=_sanitize(g.get(f)) if f in ("label", "profile_label") else _num(g.get(f)))
        r += 1

    # Pengaturan global di sebelah kanan.
    sc = len(_GROUP_COLS) + 2
    L, V = get_column_letter(sc), get_column_letter(sc + 1)
    ws.cell(row=hdr, column=sc, value="PENGATURAN GLOBAL").font = _HEADER_FONT

    def _set(rr, label, value):
        ws.cell(row=rr, column=sc, value=label).font = _LABEL_FONT
        ws.cell(row=rr, column=sc + 1, value=_num(value))

    _set(hdr + 1, "Ambang Layak (≥)", settings.get("status_eligible_min"))
    _set(hdr + 2, "Ambang Upgrade (≥)", settings.get("status_upgrade_min"))
    _set(hdr + 3, "Bobot Spek (blend)", settings.get("blend_spec"))
    _set(hdr + 4, "Bobot Beban (blend)", settings.get("blend_load"))
    _set(hdr + 5, "Masa Pakai (tahun)", settings.get("base_lifespan_years"))

    for ci in range(1, len(_GROUP_COLS) + 1):
        ws.column_dimensions[get_column_letter(ci)].width = 14
    ws.column_dimensions[L].width = 20
    ws.column_dimensions[V].width = 10
    ws.freeze_panes = f"A{hdr + 1}"


# ---------------------------------------------------------------------------
# Sheet 2 — Data & Perhitungan (SEMUA masukan + parameter + poin + skor, NILAI)
# ---------------------------------------------------------------------------
# (header, kunci). Kunci '_xxx' = turunan (dihitung di _data_value).
_DATA_COLS = [
    # Identitas pengisian & pemegang
    ("Waktu Pengisian", "submitted_at"), ("Sumber", "_source"),
    ("Nama Karyawan", "holder_name"), ("Jabatan", "holder_position"),
    ("Perusahaan", "holder_company"), ("Lokasi", "holder_location"),
    ("Kelompok (kode)", "work_group"), ("Kelompok", "_group_label"),
    ("Status Kepemilikan", "_ownership"),
    # Identitas aset
    ("Nomor Seri", "_serial"), ("No. Aset", "asset_no"),
    ("Merek", "device_brand"), ("Model", "device_model"),
    ("Hostname", "hostname"), ("MAC", "mac_address"),
    # CPU
    ("CPU / Prosesor", "cpu_model"), ("PassMark", "cpu_passmark"),
    ("Core", "cpu_cores"), ("Thread", "cpu_threads"),
    ("Arsitektur", "cpu_arch"), ("Kecepatan CPU (MHz)", "cpu_speed_mhz"),
    ("Pakai CPU (%)", "cpu_usage_pct"), ("GPU", "gpu"),
    # RAM
    ("RAM (GB)", "ram_gb"), ("Tipe RAM", "ram_type"),
    ("Kecepatan RAM (MHz)", "ram_speed_mhz"), ("Pakai RAM (%)", "ram_usage_pct"),
    ("RAM Terpakai (GB)", "ram_usage_gb"), ("Motherboard", "motherboard"),
    ("Slot Terisi", "ram_slots_used"), ("Slot Total", "ram_slots_total"),
    ("RAM Maks (GB)", "ram_max_gb"),
    # Penyimpanan & OS
    ("SSD (GB)", "ssd_gb"), ("Tipe SSD", "ssd_type"), ("HDD (GB)", "hdd_gb"),
    ("Sehat Disk (%)", "disk_health_pct"), ("Status Disk", "disk_health_raw"),
    ("Disk OS Total (GB)", "os_total_gb"), ("Disk OS Sisa (GB)", "os_free_gb"),
    ("Sistem Operasi", "os_name"),
    # Keamanan & Windows 11
    ("TPM", "tpm_version"), ("Secure Boot", "_secure_boot"),
    ("Siap Windows 11", "_win11"), ("Kendala Win11", "win11_blockers"),
    # Baterai
    ("Daya saat cek (%)", "battery_pct"), ("Sehat Baterai (%)", "_battery_health"),
    ("Baterai Penuh (Wh)", "battery_wh_full"), ("Baterai Desain (Wh)", "battery_wh_design"),
    # Kondisi
    ("Kondisi Fisik", "_condition"), ("Kelengkapan", "accessories"),
    ("Tahun Pembelian", "purchase_year"), ("Keluhan", "issues"),
    # Parameter yang dipakai
    ("Param CPU min", "_p_cpu_floor"), ("Param CPU ideal", "_p_cpu_ideal"),
    ("Param RAM min", "_p_ram_min"), ("Param RAM ideal", "_p_ram_ideal"),
    ("Bobot CPU", "_p_w_cpu"), ("Bobot RAM", "_p_w_ram"),
    ("Bobot Storage", "_p_w_storage"), ("Bobot Baterai", "_p_w_battery"),
    # Poin komponen
    ("Poin CPU", "_pt_cpu"), ("Poin RAM", "_pt_ram"),
    ("Poin Storage", "_pt_storage"), ("Poin Baterai", "_pt_battery"),
    # Skor akhir
    ("SKOR SPEK", "score_spec"), ("SKOR BEBAN", "score_load"),
    ("SKOR TOTAL", "score_total"), ("STATUS", "_status"),
    ("Est. Pensiun", "eol_year"), ("Alasan Status", "_reasons"),
]
_DATA_NUM = {
    "cpu_passmark", "cpu_cores", "cpu_threads", "cpu_speed_mhz", "cpu_usage_pct",
    "ram_gb", "ram_speed_mhz", "ram_usage_pct", "ram_usage_gb", "ram_slots_used",
    "ram_slots_total", "ram_max_gb", "ssd_gb", "hdd_gb", "disk_health_pct",
    "os_total_gb", "os_free_gb", "battery_pct", "battery_wh_full", "battery_wh_design",
    "purchase_year", "score_spec", "score_load", "score_total", "eol_year",
}
_SCORE_KEYS = {"score_spec", "score_load", "score_total", "_status"}


def _parse_reasons(raw):
    import json
    if not raw:
        return []
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else [str(v)]
    except (ValueError, TypeError):
        return [raw]


def _data_value(key, row, prm, pts, wg_labels):
    if key == "_source":
        return _SOURCE_LABEL.get(row.get("source"), row.get("source"))
    if key == "_group_label":
        return _group_label(row, wg_labels)
    if key == "_ownership":
        return _OWNERSHIP_LABEL.get(row.get("laptop_status"), row.get("laptop_status"))
    if key == "_serial":
        return row.get("serial_number") or row.get("device_serial")
    if key == "_secure_boot":
        return _yes_no(row.get("secure_boot"))
    if key == "_win11":
        return _yes_no(row.get("win11_ready"))
    if key == "_battery_health":
        return _battery_health(row)
    if key == "_condition":
        return _CONDITION_LABEL.get(row.get("physical_condition"), row.get("physical_condition"))
    if key == "_status":
        return _STATUS_LABEL.get(row.get("status"), row.get("status"))
    if key == "_reasons":
        return "; ".join(_parse_reasons(row.get("status_reasons")))
    if key.startswith("_p_"):
        return prm.get(key[3:])
    if key.startswith("_pt_"):
        return pts.get(key[4:])
    if key in _DATA_NUM:
        return _num(row.get(key))
    return row.get(key)


def _build_data(wb, rows, params, default_key, wg_labels):
    ws = wb.create_sheet("Data & Perhitungan")
    for ci, (header, _k) in enumerate(_DATA_COLS, 1):
        c = ws.cell(row=1, column=ci, value=header)
        c.font = _HEADER_FONT
        c.fill = _HEADER_FILL
        c.alignment = Alignment(wrap_text=True, vertical="center")

    for ri, row in enumerate(rows, 2):
        gk = row.get("work_group")
        prm = params.get(gk) or params.get(default_key) or {}
        pts = _component_points(row, prm) if prm else {}
        for ci, (_h, key) in enumerate(_DATA_COLS, 1):
            val = _data_value(key, row, prm, pts, wg_labels)
            cell = ws.cell(row=ri, column=ci,
                           value=val if isinstance(val, (int, float)) else _sanitize(val))
            if key in _SCORE_KEYS:
                cell.fill = _SCORE_FILL
                cell.font = Font(bold=True)

    for ci in range(1, len(_DATA_COLS) + 1):
        ws.column_dimensions[get_column_letter(ci)].width = 14
    ws.freeze_panes = "C2"


# ---------------------------------------------------------------------------
# Sheet 3 — Ringkasan (bahasa manusia)
# ---------------------------------------------------------------------------
_SUMMARY_COLS = [
    "Nama", "Laptop", "Serial", "Kelompok", "CPU", "PassMark", "RAM",
    "Penyimpanan", "Skor Spek", "Skor Beban", "Skor Total", "Status",
    "Est. Pensiun", "Kesimpulan", "Rekomendasi",
]


def _build_summary(wb, rows, wg_labels):
    ws = wb.create_sheet("Ringkasan")
    for ci, header in enumerate(_SUMMARY_COLS, 1):
        c = ws.cell(row=1, column=ci, value=header)
        c.font = _HEADER_FONT
        c.fill = _HEADER_FILL
    for ri, row in enumerate(rows, 2):
        try:
            insight = scoring.build_insights(row)
        except Exception:
            insight = {"verdict": "", "recommendations": []}
        vals = [
            row.get("holder_name"), _laptop_text(row),
            row.get("serial_number") or row.get("device_serial"),
            _group_label(row, wg_labels), row.get("cpu_model"),
            _num(row.get("cpu_passmark")), _num(row.get("ram_gb")),
            _storage_text(row), _num(row.get("score_spec")), _num(row.get("score_load")),
            _num(row.get("score_total")),
            _STATUS_LABEL.get(row.get("status"), row.get("status")),
            _num(row.get("eol_year")), insight.get("verdict"),
            " | ".join(insight.get("recommendations") or []),
        ]
        for ci, v in enumerate(vals, 1):
            ws.cell(row=ri, column=ci, value=v if isinstance(v, (int, float)) else _sanitize(v))
    widths = [22, 26, 16, 16, 26, 10, 9, 22, 10, 10, 10, 12, 12, 40, 50]
    for ci, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(ci)].width = w
    ws.freeze_panes = "A2"


# ---------------------------------------------------------------------------
# Sheet 4 — Per Karyawan
# ---------------------------------------------------------------------------
_EMPLOYEE_COLS = [
    ("Nama", "emp_full_name"), ("Perusahaan", "emp_company"),
    ("Jabatan", "emp_current_position"), ("Kelompok", "_group"),
    ("Laptop", "_laptop"), ("Serial", "device_serial"),
    ("Skor", "score_total"), ("Status", "_status"),
    ("Status Karyawan", "_emp_status"), ("Terakhir", "submitted_at"),
]


def _build_employees(wb, employees, wg_labels):
    ws = wb.create_sheet("Per Karyawan")
    for ci, (header, _f) in enumerate(_EMPLOYEE_COLS, 1):
        c = ws.cell(row=1, column=ci, value=header)
        c.font = _HEADER_FONT
        c.fill = _HEADER_FILL
    for ri, r in enumerate(employees, 2):
        for ci, (_header, field) in enumerate(_EMPLOYEE_COLS, 1):
            if field == "_group":
                wg = r.get("emp_current_work_group") or r.get("work_group")
                value = wg_labels.get(wg, wg or "-")
            elif field == "_laptop":
                value = _laptop_text(r) or "-"
            elif field == "_status":
                value = _STATUS_LABEL.get(r.get("status"), r.get("status"))
            elif field == "_emp_status":
                value = "Aktif" if (r.get("emp_status") or "active") == "active" else "Resign"
            elif field == "score_total":
                value = _num(r.get("score_total"))
            else:
                value = r.get(field)
            ws.cell(row=ri, column=ci,
                    value=value if isinstance(value, (int, float)) else _sanitize(value))
    for ci, (header, _f) in enumerate(_EMPLOYEE_COLS, 1):
        ws.column_dimensions[get_column_letter(ci)].width = max(12, len(header) + 2)
    ws.freeze_panes = "A2"


# ---------------------------------------------------------------------------
# API utama
# ---------------------------------------------------------------------------
def build_workbook(rows, groups, settings, employees, wg_labels, status_label=None):
    """Rakit Workbook 4 sheet. Nilai dihitung di Python (selalu tampil di app apa pun)."""
    params = _params_by_group(groups)
    default_key = scoring_config.DEFAULT_PROFILE_KEY  # 'admin'
    wb = Workbook()
    _build_parameter(wb, groups, settings)
    _build_data(wb, rows, params, default_key, wg_labels)
    _build_summary(wb, rows, wg_labels)
    _build_employees(wb, employees, wg_labels)
    return wb
