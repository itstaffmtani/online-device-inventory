# online-device-inventory — Pendataan & Uji Kelayakan Laptop MTani

Sistem pendataan dan **uji kelayakan laptop** untuk 100+ karyawan MTani. Karyawan
menjalankan satu file *collector* → spek laptop terdeteksi otomatis → mereka
melengkapi data diri di form web → data masuk database terpusat → Tim IT melihat
dashboard, skor kelayakan, dan laporan untuk membantu keputusan pengelolaan &
prioritas pengadaan laptop.

> Dokumentasi lengkap ada di **[CLAUDE.md](CLAUDE.md)** dan folder **[docs/](docs/)**
> (arsitektur, skema DB, aturan scoring, roadmap).

## Alur data

```
Landing (/) konteks + unduh collector
   → Collector (PowerShell / bash, tanpa install)
   → buka form web dengan spek di URL query param
   → Form Flask (1 halaman: data diri · spesifikasi · aset & kondisi) → POST /api/submit (token)
   → SQLite (devices + riwayat submissions) → scoring kelayakan
   → Dashboard admin + Export XLSX
```

Detail: [docs/architecture.md](docs/architecture.md).

## Stack

- **Backend:** Python 3 + Flask · **DB:** SQLite (file tunggal)
- **Frontend:** HTML + Tailwind (CDN) + vanilla JS
- **Collector:** 1 file `.bat` self-contained / polyglot batch+PowerShell (Windows), `bash .sh` (Mac/Linux) — tanpa install
- **Export:** XLSX (`openpyxl`)
- **Scoring:** tabel PassMark offline (`cpu_benchmarks`, di-seed dari `data/cpu_seed.csv`)

## Struktur proyek

```
app.py                 # entry point Flask (app-factory): init DB, seed, register blueprint
config.py              # konfigurasi dari environment variable (+ default dev)
db.py                  # skema SQLite + akses data (devices, submissions, cpu_benchmarks)
scoring.py             # mesin penilaian kelayakan (implementasi docs/scoring.md)
seed_cpu.py            # pengisian tabel cpu_benchmarks dari data/cpu_seed.csv
routes_public.py       # /form (prefill dari URL), POST /api/submit, /dl/<os>
routes_admin.py        # /admin login, dashboard, detail+riwayat, export.xlsx
templates/
  landing.html         # halaman utama: konteks + unduh collector
  index.html           # form publik 1 halaman (data diri · spesifikasi · aset & kondisi)
  thank_you.html       # halaman konfirmasi
  admin/               # login.html, dashboard.html, detail.html
windows/               # Check-Laptop.bat (1 file polyglot batch+PowerShell)
mac-linux/             # check-laptop.sh (collector macOS/Linux)
data/                  # cpu_seed.csv (di-commit) + inventory.db (TIDAK di-commit)
docs/                  # architecture, schema.dbml, scoring.md, roadmap, dll
hardware_service.py    # REFERENSI logika deteksi (basis port ke collector)
```

## Setup & menjalankan (dev, di Laragon)

```bash
python -m venv venv
venv\Scripts\activate            # Windows  (Linux/macOS: source venv/bin/activate)
pip install -r requirements.txt  # Flask + openpyxl

python app.py                    # http://127.0.0.1:8080
```

Saat start, `app.py` otomatis membuat `data/inventory.db` (tabel + seed CPU bila kosong).

### Konfigurasi (environment variable)

Semua punya default dev sehingga `python app.py` langsung jalan. **Untuk produksi
WAJIB di-set ulang.**

| Var | Guna | Default dev |
|---|---|---|
| `ADMIN_PASSWORD` | Password halaman `/admin` | `admin-dev` |
| `SUBMIT_TOKEN` | Token form → `/api/submit` | `dev-submit-token` |
| `SERVER_BASE_URL` | URL publik (link unduh & URL form collector) | `http://127.0.0.1:8080` |
| `DB_PATH` | Lokasi file SQLite | `data/inventory.db` |
| `FLASK_SECRET_KEY` | Secret session Flask | `dev-secret-key-...` |

## Cara pakai

### Karyawan
1. Unduh & jalankan collector (`/dl/windows` atau `/dl/mac`), atau jalankan
   `windows\Check-Laptop.bat` / `bash mac-linux/check-laptop.sh`.
2. Browser otomatis terbuka ke `/form` dengan spek sudah terisi (field auto = readonly,
   yang kosong bisa diisi manual).
3. Lengkapi nama, **kelompok kerja**, kondisi & kelengkapan → **Kirim**.
4. Skor kelayakan langsung tampil.

> Tanpa collector? Buka `/form` langsung dan isi manual.

### Tim IT (admin)
- Buka `/admin`, login dengan `ADMIN_PASSWORD`.
- Dashboard: ringkasan (total, per status/kelompok), list laptop dengan **cari & sortir**.
- Detail laptop: spek + skor + alasan + **riwayat** pemegang.
- **Export XLSX** (data terbaru per laptop, sudah disanitasi anti formula-injection).

## Endpoint

| Method | Path | Guna | Auth |
|---|---|---|---|
| GET | `/` | Landing: konteks + unduh collector | — |
| GET | `/form` | Form pengisian 1 halaman (auto-prefill dari URL) | — |
| POST | `/api/submit` | Terima data, cocokkan device, hitung skor, simpan | token |
| GET | `/dl/<windows\|mac>` | Unduh collector | — |
| GET | `/admin` | Dashboard + list | password |
| GET | `/admin/device/<id>` | Detail + riwayat 1 laptop | password |
| GET | `/admin/export.xlsx` | Export data terbaru ke Excel | password |
| GET/POST | `/admin/login`, `/admin/logout` | Sesi admin | — |

## Penilaian kelayakan

Skor 0-100 (Spek 70% + Beban 30%) → status **Layak / Upgrade / Ganti** + alasan +
estimasi tahun pensiun. CPU dinilai via PassMark multi-thread dari tabel
`cpu_benchmarks`. Semua ambang ada di **[docs/scoring.md](docs/scoring.md)** (sumber
kebenaran). Uji cepat rumus scoring: `python scoring.py`.

## Catatan keamanan
- Server internet-facing **WAJIB HTTPS** (reverse proxy + Let's Encrypt).
- `/api/submit` dijaga shared token; `/admin` 1 password bersama + Flask session.
- Input disanitasi sebelum diekspor (cegah CSV/Excel formula injection).

## Ditunda (backlog)
Sync SharePoint, code-signing collector, input manual HP/tablet, akun admin per-user.
Lihat [docs/roadmap.md](docs/roadmap.md).
