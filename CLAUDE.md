# CLAUDE.md — online-device-inventory

Panduan untuk Claude Code (dan dev) saat bekerja di repo ini. Baca ini dulu.

## Apa ini
Sistem pendataan & **uji kelayakan laptop** untuk 100+ karyawan MTani (semua
status: tetap, kontrak, magang, lapangan). Karyawan menjalankan 1 file collector
→ spek laptop terdeteksi otomatis → mereka melengkapi data diri di form web →
data masuk database terpusat → tim IT melihat dashboard, skor kelayakan, dan
laporan untuk membantu keputusan pengelolaan & prioritas pengadaan laptop.

## Arsitektur singkat
```
Landing (/) konteks + unduh collector
   → Collector (PowerShell/bash, tanpa install) → buka form web dgn spek di URL
   → Form Flask (1 halaman: data diri·spesifikasi·aset & kondisi) → POST /api/submit → SQLite (riwayat)
   → scoring kelayakan → Dashboard admin + Export XLSX
```
Detail lengkap: **[docs/architecture.md](docs/architecture.md)**.

## Stack
- **Backend:** Python 3 + Flask · **DB:** SQLite (file tunggal)
- **Frontend:** Jinja terwariskan (`templates/base.html` + `base_public.html`) + Tailwind (CDN) + Alpine.js (CDN, tanpa build) + vanilla JS. Ikon Heroicons via registry tunggal `icons.py` → global Jinja `{{ icon('nama','w-5 h-5') }}` (bukan SVG inline lagi). Komponen macro di `templates/components/`. Form 1 halaman di `templates/index.html`, landing di `templates/landing.html`
- **Migrasi DB:** yoyo-migrations (`migrations/*.sql` + wrapper `migrate.py`). Perubahan skema baru = file migrasi bernomor, bukan ALTER hardcoded di `db.py`. Lihat `migrations/README.md`
- **Collector:** 1 file `.bat` self-contained / polyglot batch+PowerShell (Windows), `bash .sh` (Mac/Linux) — **tanpa install**
- **Export:** XLSX (`openpyxl`)

## Struktur (saat ini → target)
```
app.py                 # server Flask (akan dirombak: hapus /api/diagnostik & Apps Script)
hardware_service.py    # deteksi hardware (REFERENSI untuk port ke collector)
icons.py               # registry ikon Heroicons -> global Jinja icon()
migrate.py             # CLI migrasi DB (yoyo): apply/list/rollback/mark
migrations/            # file migrasi skema bernomor (.sql) + README
migrate_*_2026_06.py   # skrip migrasi data one-off (mis. revisi kelompok/profil), idempoten
routes_admin.py        # dashboard, /admin/skoring, /admin/report, export XLSX/PDF
routes_public.py       # landing + form publik + /api/submit
scoring_config.py      # profil kebutuhan & kelompok kerja (DB: scoring_profiles + work_groups)
templates/base.html    # kerangka HTML bersama (head, Tailwind, Alpine, blocks)
templates/components/  # macro UI (status_badge, pill)
templates/index.html   # form publik 1 halaman (extends base_public.html)
templates/landing.html # halaman utama: konteks + unduh collector
docs/
  architecture.md      # alur data, kontrak collector, endpoint, keamanan
  schema.dbml          # skema database (SQLite)
  scoring.md           # ATURAN penilaian kelayakan (sumber kebenaran)
  roadmap.md           # rencana bertahap + checklist
  workflow-tasks.md    # pembagian 6 sesi (untuk dijalankan paralel via workflow)
  session-prompts.md   # 6 prompt siap-tempel per sesi
# target tambahan:
  db.py                # skema + koneksi SQLite
  scoring.py           # implementasi scoring.md
  windows/Check-Laptop.bat   # 1 file polyglot batch+PowerShell (tanpa .ps1 terpisah)
  mac-linux/check-laptop.sh
  data/inventory.db    # SQLite (jangan commit; lihat .gitignore)
```

## Cara menjalankan (dev, di Laragon)
```bash
python -m venv venv
venv\Scripts\activate            # Windows
pip install -r requirements.txt
# set env minimal (lihat docs/architecture.md): ADMIN_PASSWORD, SUBMIT_TOKEN, FLASK_SECRET_KEY
python app.py                    # default http://127.0.0.1:8080
```

## Keputusan kunci (JANGAN ubah tanpa alasan kuat)
- **Identitas laptop = Serial Number** (fallback: No.Asset → MAC). Pemegang
  menempel ke submission, bukan ke laptop → pergantian tangan = riwayat.
- **Deteksi spek dilakukan collector di laptop karyawan**, dibawa ke form lewat
  **URL query param**. JANGAN pakai `/api/diagnostik` (itu baca spek server).
- **Riwayat disimpan**; dashboard tampilkan submission terbaru per device.
- **Kelompok kerja (data-driven, tabel `work_groups`):** field, admin, finance,
  data_processing, management, it, rpo, mandor, design, hr, **other** (Lainnya —
  teks bebas di `work_group_other`). Tiap kelompok **menunjuk satu profil kebutuhan**
  (tabel `scoring_profiles`); banyak kelompok boleh berbagi profil → admin edit profil
  SEKALI, semua anggota ikut. Kelola via **`/admin/skoring`**. Detail: scoring.md §11.
- **Skor:** 0-100 (spek + beban + total) + status (Layak/Upgrade/Ganti) + EOL.
  CPU dinilai via tabel offline PassMark (`cpu_benchmarks`). Parameter skoring
  (profil/bobot/ambang) DATA-DRIVEN di DB, bukan magic number. Lihat scoring.md.
  Laporan ringkas siap-tempel-ke-Word di **`/admin/report`**.
- **Admin:** 1 password bersama (env `ADMIN_PASSWORD`), belum ada tabel user.
- **Cakupan:** Windows + Mac/Linux. HP/tablet ditunda.

## Konvensi
- **Identifier kode** (route/fungsi/nama file) **Inggris** (mis. `/admin/report`, bukan
  `/admin/laporan`); **Bahasa Indonesia** hanya untuk teks yang dilihat user (UI, label,
  pesan) & komentar. Route lama yang sudah terlanjur Indonesia (`/admin/skoring`,
  `/admin/karyawan`) dibiarkan kecuali diminta.
- Nama field ikuti **[docs/schema.dbml](docs/schema.dbml)** & kontrak URL di architecture.md.
- Angka/ambang scoring HANYA dari **[docs/scoring.md](docs/scoring.md)** (jangan sebar magic number di kode).
- Sanitasi input sebelum simpan/ekspor (anti CSV/Excel formula injection).
- Jangan hardcode tahun untuk EOL — ambil tahun dari server saat scoring.

## Status & langkah berikut
Ikuti **[docs/roadmap.md](docs/roadmap.md)**. Mulai dari Fase 1 (fondasi data + server).

## Catatan
- Proyek referensi (konsep mirip, basis script→Sheets): `C:\Users\nargy\Downloads\laptop-inventory`.
- Ditunda: sync SharePoint (belum ada admin M365), code-signing, HP/tablet, akun per-user.
