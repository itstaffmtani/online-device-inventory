# pdf_export.py — helper ekspor PDF laporan (fpdf2 2.8.x, font core Helvetica).
#
# Catatan: kode ini ditulis dengan gaya API klasik PyFPDF (parameter posisional
# `ln=`, `multi_cell(w,h,txt)`, `output(dest="S")`). fpdf2 2.8 menghapus parameter
# itu (diganti `new_x`/`new_y`, `text=`). Agar pemanggil lama tetap jalan tanpa
# diubah, kelas `_Report` memasang SHIM `cell()`/`multi_cell()` yang menerjemahkan
# `ln` (0/1/2) -> `new_x`/`new_y`. Hanya font inti Helvetica (latin-1), sehingga
# semua teks DISANITASI dulu ke ASCII aman (mis. "–","—","•","✓" -> padanan ASCII).
#
# Dua entri publik:
#   laptop_pdf(device, submissions, latest, insights)   -> bytes
#   employee_pdf(employee, submissions, latest, insights) -> bytes

from datetime import datetime

from fpdf import FPDF
from fpdf.enums import XPos, YPos

# Label tampilan (selaras dengan routes_admin.py).
_STATUS_LABEL = {"eligible": "Layak", "upgrade": "Upgrade", "replace": "Ganti"}
_LAPTOP_STATUS_LABEL = {"office_inventory": "Inventaris Kantor", "personal": "Milik Pribadi"}
_PHYSICAL_CONDITION_LABEL = {"good": "Baik", "fair": "Cukup", "poor": "Kurang"}
_SOURCE_LABEL = {
    "windows_script": "Script Windows", "mac_script": "Script Mac",
    "linux_script": "Script Linux", "manual": "Manual",
}
_WORK_GROUP_LABEL = {
    "field": "Lapangan", "admin": "Administrasi", "finance": "Keuangan",
    "data_processing": "Pengolahan Data", "management": "Manajemen", "it": "IT",
    "other": "Lainnya",
}

# Peta karakter unicode bermasalah -> ASCII aman.
_UNICODE_MAP = {
    "–": "-", "—": "-",            # en/em dash
    "‘": "'", "’": "'",            # kutip tunggal
    "“": '"', "”": '"',            # kutip ganda
    "•": "-", "▸": ">",            # bullet, segitiga
    "→": "->", "←": "<-",           # panah
    "✓": "[v]", "✗": "[x]", "✕": "[x]",  # centang / silang
    "…": "...",                              # ellipsis
    "·": "-",                                # middle dot
    "×": "x",                                # multiplication
    "≥": ">=", "≤": "<=",           # >= <=
    " ": " ",                                # non-breaking space
}


def _safe(val):
    """Ubah nilai apa pun ke string ASCII aman untuk font core latin-1."""
    if val is None:
        return "-"
    s = str(val)
    for bad, good in _UNICODE_MAP.items():
        s = s.replace(bad, good)
    # Fallback: buang karakter yang masih tak terwakili latin-1.
    return s.encode("latin-1", "replace").decode("latin-1")


def _fmt_dt(val):
    """Format timestamp ISO -> 'dd/mm/YYYY HH:MM' (best-effort)."""
    if not val:
        return "-"
    s = str(val)
    try:
        dt = datetime.fromisoformat(s.replace("Z", "").split(".")[0])
        return dt.strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError):
        return s


def _wg_label(row):
    wg = row.get("work_group")
    if wg == "other" and (row.get("work_group_other") or "").strip():
        return row["work_group_other"].strip()
    return _WORK_GROUP_LABEL.get(wg, wg or "-")


# ---------------------------------------------------------------------------
# Kelas PDF dasar dengan helper layout (API PyFPDF klasik).
# ---------------------------------------------------------------------------
class _Report(FPDF):
    # --- Shim API klasik PyFPDF -> fpdf2 2.8 (ln/txt posisional) ---------------
    def cell(self, w=0, h=0, txt="", border=0, ln=0, align="", fill=False,
             *args, **kwargs):
        if ln == 1:
            kwargs.setdefault("new_x", XPos.LMARGIN)
            kwargs.setdefault("new_y", YPos.NEXT)
        elif ln == 2:
            kwargs.setdefault("new_x", XPos.LEFT)
            kwargs.setdefault("new_y", YPos.NEXT)
        # ln == 0 -> default fpdf2 (XPos.RIGHT, YPos.TOP) = tetap di baris yang sama
        return super().cell(w, h, text=txt, border=border, align=(align or "L"),
                            fill=fill, *args, **kwargs)

    def multi_cell(self, w=0, h=0, txt="", border=0, align="J", fill=False,
                   *args, **kwargs):
        # multi_cell klasik selalu pindah ke baris berikut di margin kiri.
        kwargs.setdefault("new_x", XPos.LMARGIN)
        kwargs.setdefault("new_y", YPos.NEXT)
        return super().multi_cell(w, h, text=txt, border=border,
                                  align=(align or "L"), fill=fill, *args, **kwargs)

    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(120, 120, 120)
        self.cell(0, 6, _safe("Inventaris Laptop MTani"), 0, 0, "L")
        self.cell(0, 6, _safe("Dicetak: " + datetime.now().strftime("%d/%m/%Y %H:%M")),
                  0, 1, "R")
        self.set_draw_color(220, 220, 220)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(3)
        self.set_text_color(0, 0, 0)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(150, 150, 150)
        self.cell(0, 6, _safe("Halaman %s" % self.page_no()), 0, 0, "C")

    def title_block(self, title, subtitle=None):
        self.set_font("Helvetica", "B", 15)
        self.set_text_color(20, 20, 20)
        self.multi_cell(0, 8, _safe(title))
        if subtitle:
            self.set_font("Helvetica", "", 9)
            self.set_text_color(110, 110, 110)
            self.multi_cell(0, 5, _safe(subtitle))
        self.ln(2)
        self.set_text_color(0, 0, 0)

    def section(self, label):
        self.ln(2)
        self.set_font("Helvetica", "B", 10)
        self.set_fill_color(238, 240, 248)
        self.set_text_color(60, 60, 90)
        self.cell(0, 7, _safe(label), 0, 1, "L", True)
        self.ln(1)
        self.set_text_color(0, 0, 0)

    def kv(self, key, value):
        """Baris label : nilai."""
        self.set_font("Helvetica", "", 9)
        self.set_text_color(110, 110, 110)
        self.cell(55, 6, _safe(key), 0, 0)
        self.set_text_color(20, 20, 20)
        self.set_font("Helvetica", "", 9)
        self.multi_cell(0, 6, _safe(value))

    def bullet(self, text, prefix="-"):
        self.set_font("Helvetica", "", 9)
        self.set_text_color(40, 40, 40)
        x = self.get_x()
        self.cell(5, 5, _safe(prefix), 0, 0)
        self.set_x(x + 5)
        self.multi_cell(self.w - self.r_margin - x - 5, 5, _safe(text))


def _score_line(latest):
    if not latest:
        return "Belum ada penilaian."
    total = latest.get("score_total")
    total = "-" if total is None else total
    status = _STATUS_LABEL.get(latest.get("status"), latest.get("status") or "-")
    eol = latest.get("eol_year") or "-"
    return "Skor total %s | Status %s | Estimasi pensiun %s" % (total, status, eol)


def _spec_rows(s):
    """Daftar (label, nilai) spesifikasi lengkap termasuk field baru."""
    if not s:
        return []
    return [
        ("CPU / Prosesor", s.get("cpu_model")),
        ("Skor CPU (PassMark)", s.get("cpu_passmark")),
        ("Core / Thread", "%s / %s" % (s.get("cpu_cores") or "-", s.get("cpu_threads") or "-")),
        ("Arsitektur CPU", s.get("cpu_arch")),
        ("GPU", s.get("gpu")),
        ("RAM", ("%s GB" % (s.get("ram_gb") or "-"))
                + ((" %s" % s.get("ram_type")) if s.get("ram_type") else "")),
        ("Slot RAM", _ram_slots_text(s)),
        ("RAM Maksimum", ("%s GB" % s.get("ram_max_gb")) if s.get("ram_max_gb") else "-"),
        ("Motherboard", s.get("motherboard")),
        ("SSD", ("%s GB" % s.get("ssd_gb")) if s.get("ssd_gb") else "-"),
        ("HDD", ("%s GB" % s.get("hdd_gb")) if s.get("hdd_gb") else "-"),
        ("Kesehatan Disk", _disk_health_text(s)),
        ("Sistem Operasi", s.get("os_name")),
        ("TPM", s.get("tpm_version")),
        ("Secure Boot", _secure_boot_text(s)),
        ("Siap Windows 11", _win11_text(s)),
        ("Kesehatan Baterai", _battery_text(s)),
    ]


def _ram_slots_text(s):
    used, total = s.get("ram_slots_used"), s.get("ram_slots_total")
    if used is None and total is None:
        return "-"
    return "%s / %s terisi" % (used if used is not None else "-",
                               total if total is not None else "-")


def _disk_health_text(s):
    pct = s.get("disk_health_pct")
    raw = s.get("disk_health_raw")
    if pct is None and not raw:
        return "-"
    parts = []
    if pct is not None:
        parts.append("%s%%" % round(pct))
    if raw:
        parts.append(str(raw))
    return " - ".join(parts)


def _secure_boot_text(s):
    v = s.get("secure_boot")
    if v in (1, "1"):
        return "Aktif"
    if v in (0, "0"):
        return "Tidak aktif"
    return "-"


def _win11_text(s):
    v = s.get("win11_ready")
    if v in (1, "1"):
        return "Siap (indikasi)"
    if v in (0, "0"):
        blk = (s.get("win11_blockers") or "").strip()
        return "Belum siap" + ((": %s" % blk) if blk else "")
    return "-"


def _battery_text(s):
    h = s.get("battery_health_pct")
    if h is not None:
        return "%s%%" % round(h)
    full, design = s.get("battery_wh_full"), s.get("battery_wh_design")
    if full and design and design > 0:
        return "%s%%" % round(full / design * 100)
    return "-"


def _insight_block(pdf, insights):
    if not insights:
        return
    pdf.section("Kesimpulan & Insight")
    pdf.set_font("Helvetica", "B", 9)
    pdf.multi_cell(0, 6, _safe(insights.get("verdict") or "-"))
    pdf.ln(1)
    for c in insights.get("components", []):
        pdf.bullet("%s: %s" % (c.get("label"), c.get("text")))
    recs = insights.get("recommendations") or []
    if recs:
        pdf.ln(1)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(60, 60, 90)
        pdf.cell(0, 6, _safe("Rekomendasi:"), 0, 1)
        pdf.set_text_color(0, 0, 0)
        for r in recs:
            pdf.bullet(r, prefix=">")
    if insights.get("eol_text"):
        pdf.ln(1)
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(110, 110, 110)
        pdf.multi_cell(0, 5, _safe(insights["eol_text"]))
        pdf.set_text_color(0, 0, 0)


def _parse_reasons(latest):
    import json
    raw = (latest or {}).get("status_reasons")
    if not raw:
        return []
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else [str(val)]
    except (ValueError, TypeError):
        return [raw]


# ---------------------------------------------------------------------------
# Laporan per LAPTOP
# ---------------------------------------------------------------------------
def laptop_pdf(device, submissions, latest, insights) -> bytes:
    pdf = _Report(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    device = device or {}
    brand = device.get("brand") or "Laptop"
    model = device.get("model") or ""
    pdf.title_block(
        ("Laporan Laptop: %s %s" % (brand, model)).strip(),
        "SN: %s  |  Aset: %s  |  MAC: %s" % (
            device.get("serial_number") or "-",
            device.get("asset_no") or "-",
            device.get("primary_mac") or "-"),
    )

    # Identitas pemegang terkini.
    pdf.section("Pemegang Terkini")
    if latest:
        pdf.kv("Nama Karyawan", latest.get("holder_name"))
        pdf.kv("Jabatan", latest.get("holder_position"))
        pdf.kv("Perusahaan", latest.get("holder_company"))
        pdf.kv("Lokasi Penempatan", latest.get("holder_location"))
        pdf.kv("Kelompok Kerja", _wg_label(latest))
        pdf.kv("Status Kepemilikan",
               _LAPTOP_STATUS_LABEL.get(latest.get("laptop_status"), "-"))
        pdf.kv("Kondisi Fisik",
               _PHYSICAL_CONDITION_LABEL.get(latest.get("physical_condition"), "-"))
        pdf.kv("Sumber Data", _SOURCE_LABEL.get(latest.get("source"), "-"))
        pdf.kv("Waktu Cek", _fmt_dt(latest.get("submitted_at")))
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(0, 6, _safe("Belum ada pengisian."), 0, 1)

    # Penilaian.
    pdf.section("Penilaian Kelayakan")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, _safe(_score_line(latest)), 0, 1)
    if latest:
        pdf.set_font("Helvetica", "", 9)
        pdf.kv("Skor Spek", latest.get("score_spec"))
        pdf.kv("Skor Beban", latest.get("score_load"))
    reasons = _parse_reasons(latest)
    if reasons:
        pdf.ln(1)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 6, _safe("Alasan Status:"), 0, 1)
        for r in reasons:
            pdf.bullet(r)

    # Spesifikasi lengkap.
    pdf.section("Spesifikasi Lengkap")
    for label, value in _spec_rows(latest):
        pdf.kv(label, value)

    # Insight.
    _insight_block(pdf, insights)

    # Riwayat ringkas.
    _history_table(pdf, submissions, mode="laptop")

    return _output_bytes(pdf)


# ---------------------------------------------------------------------------
# Laporan per KARYAWAN
# ---------------------------------------------------------------------------
def employee_pdf(employee, submissions, latest, insights) -> bytes:
    pdf = _Report(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    employee = employee or {}
    status = employee.get("status") or "active"
    status_id = "Aktif" if status == "active" else "Resign"
    pdf.title_block(
        "Laporan Karyawan: %s" % (employee.get("full_name") or "-"),
        "%s  |  %s  |  Status: %s" % (
            employee.get("current_position") or "-",
            employee.get("company") or "-", status_id),
    )

    pdf.section("Identitas Karyawan")
    pdf.kv("Nama Lengkap", employee.get("full_name"))
    pdf.kv("Perusahaan", employee.get("company"))
    pdf.kv("Jabatan Terkini", employee.get("current_position"))
    pdf.kv("Kelompok Terkini", _WORK_GROUP_LABEL.get(
        employee.get("current_work_group"), employee.get("current_work_group") or "-"))
    pdf.kv("Status", status_id)
    if employee.get("employee_code"):
        pdf.kv("Kode/NIK", employee.get("employee_code"))
    if employee.get("notes"):
        pdf.kv("Catatan Admin", employee.get("notes"))
    pdf.kv("Pertama Tercatat", _fmt_dt(employee.get("first_seen_at")))
    pdf.kv("Terakhir Terlihat", _fmt_dt(employee.get("last_seen_at")))

    # Penilaian laptop terbaru.
    pdf.section("Laptop Terkini & Penilaian")
    if latest:
        pdf.kv("Laptop", ("%s %s" % (latest.get("device_brand") or "-",
                                     latest.get("device_model") or "")).strip())
        pdf.kv("Serial", latest.get("device_serial"))
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, _safe(_score_line(latest)), 0, 1)
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(0, 6, _safe("Belum ada laptop tercatat."), 0, 1)

    # Insight.
    _insight_block(pdf, insights)

    # Riwayat laptop yang pernah dipegang.
    _history_table(pdf, submissions, mode="employee")

    return _output_bytes(pdf)


def _history_table(pdf, submissions, mode):
    submissions = submissions or []
    pdf.section("Riwayat (%s)" % len(submissions))
    if not submissions:
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(0, 6, _safe("Tidak ada riwayat."), 0, 1)
        return

    # Lebar kolom berbeda per mode (mm). (label, lebar[, align])
    if mode == "laptop":
        cols = [("Waktu", 32), ("Nama", 45), ("Jabatan", 40), ("Kelompok", 28),
                ("Total", 17, "C"), ("Status", 23, "C")]
    else:  # employee
        cols = [("Waktu", 32), ("Laptop", 50), ("Jabatan", 38), ("Kelompok", 25),
                ("Total", 17, "C"), ("Status", 23, "C")]

    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(238, 240, 248)
    pdf.set_text_color(60, 60, 90)
    for col in cols:
        pdf.cell(col[1], 6, _safe(col[0]), 1, 0, "C", True)
    pdf.ln()
    pdf.set_text_color(20, 20, 20)

    prev_device = None
    prev_position = None
    for s in submissions:
        total = s.get("score_total")
        total = "-" if total is None else str(total)
        status = _STATUS_LABEL.get(s.get("status"), s.get("status") or "-")
        if mode == "laptop":
            cells = [
                _fmt_dt(s.get("submitted_at")),
                s.get("holder_name") or "-",
                s.get("holder_position") or "-",
                _wg_label(s),
                total,
                status,
            ]
        else:
            laptop = ("%s %s" % (s.get("device_brand") or "-",
                                 s.get("device_model") or "")).strip()
            mark = ""
            dev_id = s.get("device_id")
            if prev_device is not None and dev_id != prev_device:
                mark += " [ganti laptop]"
            if prev_position is not None and (s.get("holder_position") or "") != (prev_position or ""):
                mark += " [ganti jabatan]"
            cells = [
                _fmt_dt(s.get("submitted_at")),
                laptop,
                (s.get("holder_position") or "-") + mark,
                _wg_label(s),
                total,
                status,
            ]
            prev_device = dev_id
            prev_position = s.get("holder_position")

        _row(pdf, cols, cells)


def _row(pdf, cols, cells):
    """Cetak satu baris tabel dengan tinggi seragam (truncate teks panjang)."""
    line_h = 5
    pdf.set_font("Helvetica", "", 8)
    for col, text in zip(cols, cells):
        w = col[1]
        align = col[2] if len(col) > 2 else "L"
        original = _safe(text)
        txt = original
        # Potong agar tidak meluber lebar sel.
        while pdf.get_string_width(txt) > w - 1 and len(txt) > 3:
            txt = txt[:-2]
        if txt != original:
            txt = txt[:-1] + "."
        pdf.cell(w, line_h, txt, 1, 0, align)
    pdf.ln()


def _output_bytes(pdf) -> bytes:
    # fpdf2 2.8: output() tanpa argumen mengembalikan bytearray.
    return bytes(pdf.output())
