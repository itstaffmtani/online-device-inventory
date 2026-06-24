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
- **Frontend:** HTML + Tailwind (CDN) + vanilla JS + ikon Heroicons (inline SVG); form 1 halaman di `templates/index.html`, landing di `templates/landing.html`
- **Collector:** 1 file `.bat` self-contained / polyglot batch+PowerShell (Windows), `bash .sh` (Mac/Linux) — **tanpa install**
- **Export:** XLSX (`openpyxl`)

## Struktur (saat ini → target)
```
app.py                 # server Flask (akan dirombak: hapus /api/diagnostik & Apps Script)
hardware_service.py    # deteksi hardware (REFERENSI untuk port ke collector)
templates/index.html   # form publik 1 halaman (Tailwind + Heroicons)
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
- **Kelompok kerja:** field, admin, finance, data_processing, management, it, **other** (Lainnya — teks bebas disimpan di `work_group_other`).
- **Skor:** 0-100 (spek + beban + total) + status (Layak/Upgrade/Ganti) + EOL.
  CPU dinilai via tabel offline PassMark (`cpu_benchmarks`). Lihat scoring.md.
- **Admin:** 1 password bersama (env `ADMIN_PASSWORD`), belum ada tabel user.
- **Cakupan:** Windows + Mac/Linux. HP/tablet ditunda.

## Konvensi
- **Bahasa Indonesia** untuk UI, label, pesan, dan komentar (ikuti gaya kode lama).
- Nama field ikuti **[docs/schema.dbml](docs/schema.dbml)** & kontrak URL di architecture.md.
- Angka/ambang scoring HANYA dari **[docs/scoring.md](docs/scoring.md)** (jangan sebar magic number di kode).
- Sanitasi input sebelum simpan/ekspor (anti CSV/Excel formula injection).
- Jangan hardcode tahun untuk EOL — ambil tahun dari server saat scoring.

## Status & langkah berikut
Ikuti **[docs/roadmap.md](docs/roadmap.md)**. Mulai dari Fase 1 (fondasi data + server).

## Catatan
- Proyek referensi (konsep mirip, basis script→Sheets): `C:\Users\nargy\Downloads\laptop-inventory`.
- Ditunda: sync SharePoint (belum ada admin M365), code-signing, HP/tablet, akun per-user.
