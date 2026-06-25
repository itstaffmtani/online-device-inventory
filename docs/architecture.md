# Arsitektur Sistem — online-device-inventory

## Tujuan
Mendata & menguji kelayakan laptop 100+ karyawan MTani (semua status: tetap,
kontrak, magang, lapangan) untuk membantu keputusan pengelolaan & prioritas
pengadaan. Lihat juga [scoring.md](scoring.md) dan [schema.dbml](schema.dbml).

## Alur data (end-to-end)

```
┌───────────────────────────────────────────────────────────────────────┐
│ LAPTOP KARYAWAN                                                         │
│                                                                         │
│  1. Karyawan klik 1 file collector:                                    │
│       • Windows  → Check-Laptop.bat (1 file polyglot batch+PowerShell) │
│       • Mac/Linux → check-laptop.sh  (bash)                            │
│                                                                         │
│  2. Collector deteksi spek + SNAPSHOT beban (RAM usage saat itu)        │
│                                                                         │
│  3. Collector buka browser ke FORM di server, spek dibawa di URL:       │
│       https://SERVER/form?serial=...&cpu=...&ram_gb=...&ram_usage_pct=. │
└───────────────────────────────────────────────────────────────────────┘
                                  │  (browser)
                                  ▼
┌───────────────────────────────────────────────────────────────────────┐
│ SERVER FLASK (internet-facing, HTTPS)                                   │
│                                                                         │
│  4. /form  → wizard 4 langkah. Field spek auto-terisi dari URL & di-    │
│              disable (yang tak terdeteksi tetap bisa diisi manual).     │
│              Karyawan isi: Nama, kelompok kerja, kondisi, kelengkapan.  │
│                                                                         │
│  5. POST /api/submit (+ token)  → server:                              │
│        a. cocokkan/buat device (by serial → asset_no → mac)            │
│        b. hitung skor kelayakan (scoring.py)                           │
│        c. simpan submission (riwayat) ke SQLite                        │
│                                                                         │
│  6. /admin (login 1 password)  → dashboard, list sortir/cari,          │
│        detail+riwayat laptop, export XLSX.                             │
└───────────────────────────────────────────────────────────────────────┘
```

**Kenapa spek lewat URL, bukan `/api/diagnostik`?**
Form lama memakai `fetch('/api/diagnostik')` yang membaca hardware **mesin tempat
Flask jalan**. Begitu Flask jadi server pusat, itu akan membaca spek *server*,
bukan laptop karyawan. Maka deteksi WAJIB dilakukan oleh collector di laptop
karyawan, lalu dibawa ke form. Endpoint `/api/diagnostik` lama dihapus.

## Komponen & teknologi
| Bagian | Teknologi |
|---|---|
| Server | Python 3 + Flask |
| Database | SQLite (file tunggal, sumber kebenaran) |
| Frontend | HTML + Tailwind (CDN) + vanilla JS (wizard sudah ada) |
| Collector Windows | 1 file `.bat` self-contained / polyglot batch+PowerShell (tanpa install) |
| Collector Mac/Linux | `bash .sh` (tanpa install) |
| Scoring | Python (`scoring.py`) + tabel referензi `cpu_benchmarks` |
| Export | XLSX via `openpyxl` |

## Kontrak collector → form (URL query params)
Collector membuka `https://SERVER/form?` dengan parameter berikut (semua opsional;
yang kosong = field dibiarkan manual). Nama param = nama field form.

| Param | Contoh | Sumber (lihat hardware_service.py) |
|---|---|---|
| `hostname` | `LAPTOP-AB12` | socket.gethostname |
| `mac` | `AA:BB:CC:DD:EE:FF` | uuid.getnode |
| `serial` | `PF0ABCDE` | BIOS serial (wmic/dmi) |
| `brand` | `Lenovo` | manufacturer |
| `model` | `ThinkPad E14` | model |
| `cpu` | `AMD Ryzen 5 7530U` | cpuinfo brand_raw |
| `cpu_cores` | `6` | core fisik |
| `cpu_threads` | `12` | thread |
| `cpu_arch` | `x64` | arsitektur |
| `cpu_speed_mhz` | `2000` | freq max |
| `gpu` | `AMD Radeon Graphics` | video controller |
| `ram_gb` | `16` | total RAM |
| `ram_type` | `LPDDR5` | (Windows: Win32_PhysicalMemory) |
| `ram_speed_mhz` | `6400` | speed |
| `ram_usage_pct` | `52` | **snapshot** beban |
| `ram_usage_gb` | `8.3` | **snapshot** beban |
| `ssd_gb` | `512` | disk fisik SSD |
| `ssd_type` | `NVMe` | MediaType+BusType |
| `hdd_gb` | `0` | disk fisik HDD |
| `os` | `Windows 11 Home` | platform |
| `os_total_gb` | `476` | partisi OS |
| `os_free_gb` | `120` | partisi OS |
| `battery_pct` | `78` | psutil |
| `battery_wh_full` | `41.2` | BatteryFullChargedCapacity |
| `battery_wh_design` | `57.0` | BatteryStaticData DesignedCapacity |
| `motherboard` | `LENOVO LNVNB161216` | Win32_BaseBoard (vendor + produk) |
| `ram_slots_total` | `2` | Win32_PhysicalMemoryArray.MemoryDevices |
| `ram_slots_used` | `1` | jumlah Win32_PhysicalMemory |
| `ram_max_gb` | `32` | Win32_PhysicalMemoryArray.MaxCapacity → GB |
| `disk_health_pct` | `96` | StorageReliabilityCounter Wear / HealthStatus (disk sistem) |
| `disk_health_raw` | `Wear 4%` | teks mentah kesehatan disk |
| `tpm_version` | `2.0` | Win32_Tpm.SpecVersion (angka pertama) |
| `secure_boot` | `1` | Confirm-SecureBootUEFI (1/0) |
| `win11_ready` | `1` | indikasi siap Win11 (TPM 2.0 + Secure Boot + RAM≥4 + disk≥64) |
| `win11_blockers` | `TPM bukan 2.0` | alasan belum siap Win11 (bila ada) |

> Param baru `tpm_version`, `secure_boot`, `win11_ready`, `win11_blockers` khusus
> Windows; di Mac/Linux dikosongkan (best-effort). Nama param = nama kolom DB.

> Collector hanya **mengisi form**, tidak mengirim langsung. Pengiriman ke server
> tetap lewat tombol "Kirim" di form (POST `/api/submit`), supaya karyawan sempat
> melengkapi data diri & kondisi, dan agar 1 alur kirim saja.

## Endpoint server
| Method | Path | Guna | Auth |
|---|---|---|---|
| GET | `/` | Landing: konteks + unduh collector | — |
| GET | `/form` | Form pengisian 1 halaman (auto-prefill dari URL) | — |
| POST | `/api/submit` | Terima data, cocokkan device + karyawan, hitung skor, simpan | token |
| GET | `/laptop/<id>` | Laporan publik 1 laptop (read-only, untuk dibagikan) | — |
| GET | `/dl/windows`, `/dl/mac` | Unduh file collector | — |
| GET | `/admin` | Dashboard (tab Laptop / Karyawan / Pengadaan) | password |
| GET | `/admin/laptop/<id>` | Detail + riwayat 1 laptop | password |
| GET | `/admin/device/<id>` | Redirect 302 ke `/admin/laptop/<id>` (back-compat) | password |
| GET | `/admin/karyawan/<id>` | Detail + riwayat 1 karyawan | password |
| GET | `/admin/laptop/<id>/export.pdf` | Laporan PDF 1 laptop (fpdf2) | password |
| GET | `/admin/karyawan/<id>/export.pdf` | Laporan PDF 1 karyawan (fpdf2) | password |
| GET | `/admin/export.xlsx` | Export seluruh data terbaru ke Excel (+ sheet Per Karyawan) | password |
| POST | `/admin/login` / `/admin/logout` | Sesi admin | — |

## Keamanan (sederhana, cukup untuk tahap ini)
- **Server internet-facing → WAJIB HTTPS** (mis. reverse proxy + Let's Encrypt).
- **`/api/submit` pakai shared token** (`SUBMIT_TOKEN` di env), disisipkan ke form
  saat `/form` dirender. Mencegah spam asal-asalan. (Bukan keamanan kuat, hanya
  pagar; data ini bukan rahasia tinggi.)
- **`/admin` pakai 1 password bersama** (`ADMIN_PASSWORD` di env) + Flask session.
  Tidak ada tabel user. Bisa di-upgrade ke akun per-user nanti.
- Sanitasi input sebelum simpan/ekspor (cegah CSV/Excel formula injection —
  prefix `'` bila value diawali `= + - @`, sudah ada polanya di app.py lama).
- Rate-limit ringan pada `/api/submit` (opsional).

## Konfigurasi (environment variables)
| Var | Guna |
|---|---|
| `ADMIN_PASSWORD` | Password halaman admin |
| `SUBMIT_TOKEN` | Token form → /api/submit |
| `SERVER_BASE_URL` | URL publik (untuk link unduh collector & redirect form) |
| `DB_PATH` | Lokasi file SQLite (default `data/inventory.db`) |
| `FLASK_SECRET_KEY` | Secret session Flask |

## Ditunda (bukan sekarang)
- **Sync SharePoint realtime** — user belum punya akses admin M365. Sementara
  pakai export XLSX manual; nanti sync via rclone / Power Automate akun biasa.
- **Code-signing certificate** collector — pakai panduan "Run anyway" dulu.
- **HP & tablet** — tak bisa auto-detect; nanti via form input manual.
- **Akun admin per-user**.
