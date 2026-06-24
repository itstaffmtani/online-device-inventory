# Roadmap & Pembagian Tugas (solo dev)

Urutan dibuat agar tiap fase menghasilkan sesuatu yang bisa dites sendiri.
Centang saat selesai.

> **Status (Sesi 6 — Integrasi & QA, selesai):** siklus penuh sudah berjalan
> end-to-end — collector → `/form` (prefill) → `POST /api/submit` → SQLite
> (device + riwayat) → scoring → dashboard admin → export XLSX. Diverifikasi via
> curl: submit (token valid → tersimpan + skor, token salam → 403), pencocokan
> device by serial (handover terekam sebagai riwayat, bukan device baru), login
> admin + dashboard + detail + XLSX (sanitasi formula-injection OK), dan
> `python scoring.py` cocok dengan contoh §7. Sisa item lihat tanda `[ ]`.

## Fase 1 — Fondasi data & server
- [x] Buat skema SQLite sesuai [schema.dbml](schema.dbml) (`db.py` + init).
- [x] Modul koneksi DB + helper (cari/buat device by serial→asset→mac).
- [x] Endpoint `POST /api/submit`: validasi token, cocokkan device, simpan submission.
- [x] Hapus `/api/diagnostik` (model lokal) & ketergantungan Google Apps Script.
- [x] Config via env (`ADMIN_PASSWORD`, `SUBMIT_TOKEN`, `DB_PATH`, dll).
- **Tes:** kirim JSON dummy via curl → muncul 1 device + 1 submission di DB. ✅

## Fase 2 — Form publik (wizard)
- [x] Tambah **Step 0: Konteks** (teks pengantar tujuan pendataan).
- [x] Ubah Step "Diagnostik" → **auto-prefill dari URL query** + field di-disable
      bila terisi; yang kosong tetap bisa diisi manual (badge auto/manual).
- [x] Tambah **dropdown kelompok kerja** (6 pilihan) di Step Data Diri.
- [x] Arahkan submit → `POST /api/submit` (+ token), bukan Apps Script.
- [x] Halaman "Terima kasih".
- **Tes:** buka `/form?serial=X&cpu=...&ram_gb=16` → field terisi & disabled → submit masuk DB. ✅

## Fase 3 — Collector (port dari hardware_service.py)
- [x] `windows/cek-laptop.ps1` + `Cek-Laptop.bat` (wrapper) — deteksi spek +
      snapshot `ram_usage_pct/gb`, lalu buka browser ke `/form?...`.
- [x] `mac-linux/cek-laptop.sh` — idem untuk bash.
- [x] Endpoint unduh `/dl/windows`, `/dl/mac`.
- [x] Panduan singkat "Run anyway" (teks; GIF menyusul) — Execution-Policy Bypass per
      panggilan di `.bat`/`.ps1` + catatan di README/architecture.
- **Tes:** jalankan di mesin sendiri → browser terbuka, spek benar terisi (23 field). ✅

## Fase 4 — Mesin kelayakan (scoring)
- [x] Tabel `cpu_benchmarks` + seed (`data/cpu_seed.csv` + `seed_cpu.py`).
- [x] `scoring.py` implement [scoring.md](scoring.md): skor spek, beban, total,
      status + alasan, EOL. Plus fallback CPU tak dikenal (estimasi via thread).
- [x] Panggil scoring saat submit (simpan hasil ke submission).
- [ ] Script re-score semua submission terbaru (untuk kalibrasi ulang). *(belum)*
- **Tes:** cocokkan contoh §7 scoring.md → angka sama (`python scoring.py`). ✅

## Fase 5 — Admin (dashboard)
- [x] Login 1 password + session.
- [x] Dashboard ringkasan: total laptop, jumlah per status, per kelompok, per perusahaan.
- [x] List laptop: **sortir & cari** (by nama/serial/brand/status/skor/kelompok).
- [x] Detail laptop: spek terbaru + skor + alasan + **riwayat** (perubahan & pergantian pemegang).
- **Tes:** data dummy → filter, sortir, buka detail, lihat riwayat. ✅

## Fase 6 — Export & polmakan
- [x] Export `/admin/export.xlsx` (data terbaru per laptop) via openpyxl.
- [x] Sanitasi anti formula-injection saat ekspor (prefix `'` bila diawali `= + - @`).
- [ ] (Opsional) export PDF per laptop. *(ditunda — XLSX dipakai)*
- **Tes:** buka XLSX di Excel → kolom rapi, tidak ada formula nyasar. ✅

## Ditunda (backlog)
- [ ] Sync SharePoint (rclone / Power Automate akun biasa) saat akses M365 siap.
- [ ] Code-signing collector.
- [ ] Form input manual untuk HP/tablet.
- [ ] Akun admin per-user + audit log.

## Dependensi server (requirements.txt — target)
```
Flask
openpyxl        # export XLSX
# psutil, py-cpuinfo TIDAK lagi dibutuhkan server (deteksi pindah ke collector)
# fpdf hanya bila tetap mau export PDF
```
