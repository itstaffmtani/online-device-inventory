# Pembagian Tugas untuk Workflow (6 sesi / 4 gelombang)

Tujuan: memecah build jadi tugas-tugas **self-contained** yang aman dijalankan
paralel. Aturan utama: **satu file hanya dimiliki satu sesi** agar tidak tabrakan.

Semua sesi WAJIB membaca dulu: `CLAUDE.md`, `docs/architecture.md`,
`docs/schema.dbml`, `docs/scoring.md`.

## Peta dependensi
```
Sesi 1 (Fondasi)  ──►  Sesi 2 (Scoring)  ─┐
                  ──►  Sesi 3 (Collector) │
                                          ├─►  Sesi 4 (Form publik)  ─┐
                       (Sesi 2 dipakai) ──┴─►  Sesi 5 (Admin)        ─┴─► Sesi 6 (QA)
```
- **Gelombang 1:** Sesi 1 sendiri (blokir semua).
- **Gelombang 2:** Sesi 2 ∥ Sesi 3 (paralel).
- **Gelombang 3:** Sesi 4 ∥ Sesi 5 (paralel; butuh Sesi 1 & 2 selesai).
- **Gelombang 4:** Sesi 6 (setelah semua).

## KONTRAK antar-modul (ditetapkan Sesi 1, dipakai semua)
Agar paralel aman, semua sesi mengikuti tanda tangan fungsi ini:

```python
# db.py
def init_db() -> None
def get_db() -> Connection                       # koneksi SQLite per-request
def find_or_create_device(serial, asset_no, mac, brand, model, os_family) -> int
def insert_submission(data: dict) -> int         # data = semua kolom submissions
def latest_per_device() -> list[dict]            # 1 submission terbaru per device
def device_with_history(device_id: int) -> dict  # {device, submissions[]}

# scoring.py
def score_submission(sub: dict, current_year: int) -> dict
#   -> {score_spec, score_load, score_total, status, status_reasons: list[str], eol_year}
def cpu_passmark(cpu_model: str) -> tuple[int, bool]   # (skor, diperkirakan?)

# blueprint (Flask)
public_bp   # GET /form, POST /api/submit, GET /dl/<os>
admin_bp    # GET /admin, /admin/device/<id>, /admin/export.xlsx, POST /admin/login,logout
```

---

## SESI 1 — FONDASI (gelombang 1, solo)
**Tujuan:** kerangka server + database + kontrak, supaya sesi lain tinggal mengisi.
**Memiliki file:** `db.py`, `config.py`, `app.py` (rombak jadi app-factory +
register blueprint), `routes_public.py` (STUB), `routes_admin.py` (STUB),
`requirements.txt`, buat folder `data/`.
**Kerjakan:**
- `db.py`: buat skema SQLite persis `docs/schema.dbml` (devices, submissions,
  cpu_benchmarks + enum sbg TEXT/CHECK). Implement semua fungsi di KONTRAK.
  Pencocokan device: serial → asset_no → mac → buat baru.
- `config.py`: baca env (ADMIN_PASSWORD, SUBMIT_TOKEN, DB_PATH, FLASK_SECRET_KEY,
  SERVER_BASE_URL) dengan default dev.
- `app.py`: `create_app()` factory, `init_db()` saat start, register `public_bp`
  & `admin_bp`. HAPUS `/api/diagnostik` dan semua kode Google Apps Script lama.
- `routes_public.py` & `routes_admin.py`: definisikan blueprint + route KOSONG
  (return placeholder) agar sesi lain mengisinya tanpa menyentuh app.py.
**Definition of done:** `python app.py` jalan; `GET /form` & `GET /admin`
mengembalikan placeholder; file DB ter-create dengan tabel benar.
**JANGAN sentuh:** `templates/`, `scoring.py`, collector.

---

## SESI 2 — SCORING (gelombang 2, paralel)
**Tujuan:** mesin penilaian kelayakan sesuai `docs/scoring.md`.
**Memiliki file:** `scoring.py`, `seed_cpu.py` (atau `data/cpu_seed.csv` + loader).
**Kerjakan:**
- Implement `score_submission()` & `cpu_passmark()` persis rumus scoring.md
  (skor spek/beban/total, status + override, EOL, fallback CPU tak dikenal).
- Seed `cpu_benchmarks`: minimal semua CPU acuan PDF (§1 scoring.md) — cari
  angka PassMark multi-thread asli dari cpubenchmark.net, tandai sumber+tanggal.
- Sertakan tes mandiri yang mencocokkan **contoh §7 scoring.md** (skor 81/Layak/2027).
**Definition of done:** jalankan tes → angka cocok dengan contoh; seed CPU masuk DB.
**Tergantung:** Sesi 1 (skema). **JANGAN sentuh:** app.py, routes, templates, collector.

---

## SESI 3 — COLLECTOR (gelombang 2, paralel)
**Tujuan:** script deteksi spek tanpa install, buka form dengan spek di URL.
**Memiliki file:** `windows/cek-laptop.ps1`, `windows/Cek-Laptop.bat`,
`mac-linux/cek-laptop.sh`.
**Kerjakan:**
- Port logika `hardware_service.py` ke PowerShell & bash (CPU, RAM+tipe+speed,
  disk SSD/HDD+tipe, GPU, baterai wh full/design, serial, MAC, hostname, OS,
  partisi OS) + **snapshot `ram_usage_pct`/`ram_usage_gb`**.
- Susun URL `SERVER_BASE_URL/form?...` sesuai tabel kontrak di architecture.md
  (URL-encode), lalu buka browser default.
- `.bat` = wrapper `powershell -ExecutionPolicy Bypass -File ...` agar bisa double-click.
**Definition of done:** dijalankan di mesin nyata → browser terbuka, param spek benar terisi.
**Tergantung:** hanya kontrak URL (architecture.md). **JANGAN sentuh:** file Python/templates.

---

## SESI 4 — FORM PUBLIK (gelombang 3, paralel)
**Tujuan:** wizard pengisian + endpoint simpan.
**Memiliki file:** `templates/index.html` (rombak), `routes_public.py` (isi stub).
**Kerjakan:**
- Tambah **Step 0: Konteks** (pengantar tujuan pendataan).
- Ubah step Diagnostik → **auto-prefill dari URL query** + field di-disable bila
  terisi; yang kosong tetap bisa manual (badge auto/manual seperti project lama).
- Tambah **dropdown kelompok kerja** (6: field, admin, finance,
  data_processing, management, it) di Step Data Diri.
- Submit → `POST /api/submit` (+ SUBMIT_TOKEN yang disisipkan saat render `/form`).
- `routes_public.py`: GET `/form` (render + inject token), POST `/api/submit`
  (validasi token → `find_or_create_device` → `score_submission` → `insert_submission`),
  GET `/dl/<os>` (kirim file collector), halaman "Terima kasih".
**Definition of done:** buka `/form?serial=X&cpu=...&ram_gb=16` → terisi+disabled →
submit → 1 device + 1 submission + skor tersimpan.
**Tergantung:** Sesi 1 + Sesi 2. **JANGAN sentuh:** routes_admin.py, scoring.py, db.py.

---

## SESI 5 — ADMIN (gelombang 3, paralel)
**Tujuan:** dashboard, list, detail+riwayat, export.
**Memiliki file:** `routes_admin.py` (isi stub), `templates/admin/*.html`.
**Kerjakan:**
- Login 1 password (env ADMIN_PASSWORD) + Flask session; `login_required`.
- Dashboard: ringkasan (total laptop, jumlah per status/kelompok/perusahaan).
- List laptop (`latest_per_device`): **sortir & cari** (nama, serial, brand,
  status, skor, kelompok). Server-side sederhana cukup.
- Detail `/admin/device/<id>` (`device_with_history`): spek+skor+alasan + riwayat
  (perubahan & pergantian pemegang).
- `/admin/export.xlsx` via openpyxl (data terbaru per laptop) + sanitasi anti
  formula-injection.
**Definition of done:** dgn data dummy → login, filter/sortir, buka detail+riwayat,
unduh XLSX rapi.
**Tergantung:** Sesi 1 (+ data dari Sesi 4 untuk uji). **JANGAN sentuh:**
routes_public.py, templates/index.html, scoring.py.

---

## SESI 6 — INTEGRASI & QA (gelombang 4, solo)
**Tujuan:** pastikan semua nyambung.
**Kerjakan:**
- Jalankan alur penuh: collector → /form → submit → DB → dashboard → export.
- Perbaiki ketidakcocokan nama field antar sesi (acuan: schema.dbml).
- Cek requirements.txt final (Flask, openpyxl; psutil/py-cpuinfo TIDAK perlu di server).
- Update README.md + centang `docs/roadmap.md`.
**Definition of done:** satu siklus data nyata berhasil dari klik collector sampai muncul di dashboard & XLSX.

---

## Catatan untuk eksekusi workflow
- Beri tiap sesi **akses baca semua docs/** + sebut file yang ia MILIKI & yang
  DILARANG disentuh (sudah tertulis di atas) untuk cegah konflik.
- Bila pakai isolasi worktree per agen paralel, gabungkan hasil setelah tiap gelombang.
- Urutan barrier: tunggu Gelombang 1 selesai sebelum 2; tunggu 2 sebelum 3.
