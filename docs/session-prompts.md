# Prompt siap-tempel per sesi

Tiap blok di bawah = 1 prompt untuk 1 sesi/agen. Patuhi urutan gelombang:
**G1: Sesi 1 → G2: Sesi 2 ∥ 3 → G3: Sesi 4 ∥ 5 → G4: Sesi 6.**
Detail lengkap tiap sesi ada di `docs/workflow-tasks.md`.

---

## Sesi 1 — FONDASI  (Gelombang 1, jalankan sendiri dulu)
```
Kamu mengerjakan proyek online-device-inventory (Flask + SQLite). Baca dulu:
CLAUDE.md, docs/architecture.md, docs/schema.dbml, docs/workflow-tasks.md (bagian "SESI 1").

Kerjakan SESI 1 — FONDASI. Patuhi "KONTRAK antar-modul" di workflow-tasks.md.
File yang KAMU buat/miliki: db.py, config.py, app.py (rombak jadi app-factory +
register blueprint), routes_public.py (stub), routes_admin.py (stub),
requirements.txt, folder data/.
- db.py: skema SQLite persis docs/schema.dbml + semua fungsi di KONTRAK
  (pencocokan device: serial → asset_no → mac → buat baru).
- config.py: baca env (ADMIN_PASSWORD, SUBMIT_TOKEN, DB_PATH, FLASK_SECRET_KEY,
  SERVER_BASE_URL) dengan default dev.
- app.py: create_app() factory, init_db() saat start, register public_bp & admin_bp.
  HAPUS /api/diagnostik dan semua kode Google Apps Script lama.
- routes_public.py & routes_admin.py: definisikan blueprint + route KOSONG (placeholder).
JANGAN sentuh: templates/, scoring.py, collector.
Definition of done: `python app.py` jalan; GET /form & GET /admin balas placeholder;
file DB ter-create dengan tabel benar. Bahasa Indonesia untuk UI & komentar.
```

---

## Sesi 2 — SCORING  (Gelombang 2, paralel dengan Sesi 3)
```
Proyek online-device-inventory. Baca dulu: CLAUDE.md, docs/scoring.md,
docs/schema.dbml, docs/workflow-tasks.md (bagian "SESI 2"). Asumsikan Sesi 1 (db.py,
skema) sudah selesai.

Kerjakan SESI 2 — SCORING. File yang KAMU miliki: scoring.py, seed_cpu.py
(atau data/cpu_seed.csv + loader).
- Implement score_submission(sub, current_year) & cpu_passmark(cpu_model) PERSIS
  rumus docs/scoring.md (skor spek/beban/total, status + aturan paksa, EOL,
  fallback CPU tak dikenal). Tanda tangan ikuti KONTRAK di workflow-tasks.md.
- Seed cpu_benchmarks: minimal semua CPU acuan PDF (scoring.md §1) — cari angka
  PassMark multi-thread asli dari cpubenchmark.net, catat sumber + tanggal.
- Sertakan tes mandiri yang mencocokkan contoh scoring.md §7 (skor 81/Layak/2027).
JANGAN sentuh: app.py, routes_*, templates/, collector.
Definition of done: tes lulus (angka cocok contoh §7); seed CPU masuk DB.
```

---

## Sesi 3 — COLLECTOR  (Gelombang 2, paralel dengan Sesi 2)
```
Proyek online-device-inventory. Baca dulu: CLAUDE.md, hardware_service.py,
docs/architecture.md (bagian "Kontrak collector → form"), docs/workflow-tasks.md
(bagian "SESI 3").

Kerjakan SESI 3 — COLLECTOR. File yang KAMU miliki: windows/cek-laptop.ps1,
windows/Cek-Laptop.bat, mac-linux/cek-laptop.sh.
- Port logika hardware_service.py ke PowerShell & bash: CPU, RAM (+tipe+speed),
  disk SSD/HDD (+tipe), GPU, baterai (wh full & design), serial, MAC, hostname,
  OS, partisi OS, PLUS snapshot ram_usage_pct & ram_usage_gb.
- Susun URL SERVER_BASE_URL/form?... sesuai tabel kontrak di architecture.md
  (URL-encode tiap nilai), lalu buka browser default.
- Cek-Laptop.bat = wrapper: powershell -ExecutionPolicy Bypass -File cek-laptop.ps1
  (agar bisa double-click).
JANGAN sentuh: file Python/templates.
Definition of done: dijalankan di mesin nyata → browser terbuka, param spek benar terisi.
```

---

## Sesi 4 — FORM PUBLIK  (Gelombang 3, paralel dengan Sesi 5)
```
Proyek online-device-inventory. Baca dulu: CLAUDE.md, docs/architecture.md,
docs/schema.dbml, docs/workflow-tasks.md (bagian "SESI 4"). Asumsikan Sesi 1 & 2 selesai.

Kerjakan SESI 4 — FORM PUBLIK. File yang KAMU miliki: templates/index.html (rombak),
routes_public.py (isi stub). Pakai fungsi db.py & scoring.py via KONTRAK.
- Wizard: tambah Step 0 "Konteks" (pengantar tujuan pendataan).
- Step Diagnostik → auto-prefill dari URL query + field di-disable bila terisi;
  yang kosong tetap bisa manual (badge auto/manual seperti project lama Downloads).
- Tambah dropdown kelompok kerja 6 pilihan (field, admin, finance,
  data_processing, management, it) di Step Data Diri.
- Submit → POST /api/submit (+ SUBMIT_TOKEN yang disisipkan saat render /form).
- routes_public.py: GET /form (render + inject token), POST /api/submit (validasi
  token → find_or_create_device → score_submission → insert_submission), GET /dl/<os>,
  halaman Terima kasih.
JANGAN sentuh: routes_admin.py, scoring.py, db.py, templates/admin/.
Definition of done: buka /form?serial=X&cpu=...&ram_gb=16 → terisi+disabled → submit
→ 1 device + 1 submission + skor tersimpan. Bahasa Indonesia, Tailwind (ikuti gaya yang ada).
```

---

## Sesi 5 — ADMIN  (Gelombang 3, paralel dengan Sesi 4)
```
Proyek online-device-inventory. Baca dulu: CLAUDE.md, docs/schema.dbml,
docs/architecture.md, docs/workflow-tasks.md (bagian "SESI 5"). Asumsikan Sesi 1 selesai.

Kerjakan SESI 5 — ADMIN. File yang KAMU miliki: routes_admin.py (isi stub),
templates/admin/*.html. Pakai fungsi db.py via KONTRAK.
- Login 1 password (env ADMIN_PASSWORD) + Flask session + dekorator login_required.
- Dashboard: ringkasan (total laptop, jumlah per status/kelompok/perusahaan).
- List laptop (latest_per_device): sortir & cari (nama, serial, brand, status,
  skor, kelompok) — server-side sederhana.
- Detail /admin/device/<id> (device_with_history): spek + skor + alasan + riwayat
  (perubahan & pergantian pemegang).
- /admin/export.xlsx via openpyxl (data terbaru per laptop) + sanitasi anti
  formula-injection (prefix ' bila value diawali = + - @).
JANGAN sentuh: routes_public.py, templates/index.html, scoring.py, db.py.
Definition of done: dgn data dummy → login, filter/sortir, buka detail+riwayat,
unduh XLSX rapi. Bahasa Indonesia, Tailwind.
```

---

## Sesi 6 — INTEGRASI & QA  (Gelombang 4, terakhir)
```
Proyek online-device-inventory. Baca CLAUDE.md + semua docs/. Semua sesi 1-5 sudah digabung.

Kerjakan SESI 6 — INTEGRASI & QA.
- Jalankan alur penuh: collector → /form → submit → DB → dashboard → export XLSX.
- Perbaiki ketidakcocokan nama field antar modul (acuan tunggal: docs/schema.dbml).
- Finalkan requirements.txt (Flask, openpyxl; psutil/py-cpuinfo TIDAK perlu di server;
  fpdf hanya bila tetap mau export PDF).
- Update README.md (cara setup & jalankan) + centang docs/roadmap.md.
Definition of done: satu siklus data nyata berhasil dari klik collector sampai
muncul di dashboard & XLSX, tanpa error.
```
