# Brief Aturan Penilaian Kelayakan (Scoring)

Dokumen ini adalah **sumber kebenaran untuk manusia** (rumus & makna).

> ✅ **REVISI "STANDAR FRUGAL" SUDAH DITERAPKAN (2026-06).** Angka di dokumen ini
> sudah final & mencerminkan kode. Ringkasan keputusan yang diterapkan:
> (1) profil **Standar Frugal** (CPU ideal turun, mis. admin 18.000→12.000;
> **Lapangan = Administrasi**) + **bobot per kelompok**; (2) ambang **Ganti**
> menyempit (`status_upgrade_min` 45→**35**); (3) tekanan pemakaian → **linier**
> (buang piecewise); (4) EOL → **rata 5 tahun** (buang ±1); (5) penalti OS storage
> berbasis **rasio < 15%** (−10 Skor Beban); (6) logika **kepemilikan personal** &
> **proteksi rotasi Manajemen**. Data CPU dibangun ulang dari PassMark resmi
> (`data/passmark_single_cpu_intel_amd.csv`). Latar/keputusan lengkap diarsipkan di
> [scoring-revisi-2026-06.md](scoring-revisi-2026-06.md).

> **PENTING (perubahan):** angka parameter (profil per kelompok, bobot komponen,
> ambang status, masa pakai EOL, blend total) kini **DATA-DRIVEN**: tersimpan di
> DB (`work_groups` + `scoring_settings`), bukan lagi konstanta mati. Admin
> mengubahnya lewat **UI `/admin/skoring`**. Nilai **DEFAULT/seed** (identik
> dengan konstanta lama di tabel di bawah) ada di `scoring_config.py`. `scoring.py`
> membaca dari DB dan otomatis fallback ke default bila tabel belum ada.
> Setelah mengubah parameter, jalankan **"Hitung ulang semua"** agar skor lama
> ikut diperbarui.

Dasar acuan beban kerja per kelompok = PDF *"Rekomendasi Spesifikasi Laptop
Berdasarkan Kelompok Karyawan"* (Tim IT MTani, Juni 2026).

---

## 0. Keluaran yang dihasilkan
Untuk tiap laptop (submission terbaru):
- **Skor Spek** (0-100) — kualitas hardware terhadap kebutuhan perannya.
- **Skor Beban** (0-100) — ketahanan terhadap beban kerja nyata (tekanan RAM + CPU terpakai).
- **Skor Total** (0-100) — headline = `round(0.7 * Skor Spek + 0.3 * Skor Beban)`.
- **Status** — `Layak` / `Upgrade` / `Ganti` (+ daftar alasan).
- **Estimasi Tahun Pensiun** (EOL year).

---

## 1. Profil kebutuhan per kelompok kerja
`CPU floor/ideal` = skor **PassMark multi-thread**. `RAM` dalam GB.
Angka PassMark di bawah adalah **anchor perkiraan** dari CPU acuan PDF —
**verifikasi & seed dari cpubenchmark.net** saat mengisi tabel `cpu_benchmarks`.

**Standar Frugal (2026-06).** Target operasional umum = setara Intel Core i3 Gen
12 / Ryzen 3 (PassMark ≈ 12.000); divisi teknis berat (IT/Keuangan/Data) ≥ 16.000.

| Kelompok | CPU floor | CPU ideal | RAM min | RAM ideal |
|---|---:|---:|---:|---:|
| `field` | 6.000 | 12.000 | 8 | 16 |
| `admin` | 6.000 | 12.000 | 8 | 16 |
| `marketing` | 6.000 | 12.000 | 8 | 16 |
| `hr` | 6.000 | 12.000 | 8 | 16 |
| `management` | 8.000 | 14.000 | 8 | 16 |
| `finance` | 10.000 | 16.000 | 8 | 16 |
| `data_processing` | 10.000 | 16.000 | 8 | 16 |
| `design` | 10.000 | 16.000 | 8 | 16 |
| `it` | 14.000 | 22.000 | 16 | 32 |

> Catatan: **Lapangan = Administrasi** (profil & bobot identik). `finance` &
> `data_processing` dasarnya sama (Excel/data berat), tetap dipisah agar laporan
> bisa membedakan. Hanya `it` yang menuntut RAM 16/32; sisanya 8/16 (efisiensi
> budget). `other` memakai profil `admin`. Bobot komponen per kelompok di §2e.

---

## 2. Komponen Skor Spek (0-100)
Tiap komponen dihitung 0-100, lalu dijumlah berbobot.

### 2a. CPU points
```
ratio = cpu_passmark / profil.cpu_ideal
cpu_points = clamp(round(100 * ratio), 0, 100)
```
(Di skor ideal → 100; setengahnya → ~50.) Bila CPU tak ada di tabel → lihat §6 fallback.

### 2b. RAM points
```
ratio = ram_gb / profil.ram_ideal
ram_points = clamp(round(100 * ratio), 0, 100)
```

### 2c. Storage points (ambil yang terbaik terpasang)
| Kondisi | Poin |
|---|---:|
| Ada SSD NVMe | 100 |
| Ada SSD SATA/M.2 | 85 |
| HDD saja (tanpa SSD) | 25 |
| Tidak terdeteksi | 50 (netral) |

**Faktor kesehatan disk (`disk_health_pct`).** Bila kesehatan disk diketahui,
poin storage dikali faktor kesehatan agar disk yang sudah aus tidak dinilai
sebagai penyimpanan prima:
```
faktor = clamp(disk_health_pct / 100, 0.5, 1.0)
storage_points = round(storage_points * faktor)
```
- Bila `disk_health_pct` **tidak diketahui (None)** → faktor 1.0 (netral, poin
  tak berubah). Karena itu contoh §7 (NVMe, tanpa data kesehatan) tetap 100.
- Faktor dibatasi minimal 0.5 supaya satu sinyal kesehatan tidak menjatuhkan
  skor terlalu drastis (disk masih bisa dipakai sambil dijadwalkan ganti).

### 2d. Battery points
```
health = battery_wh_full / battery_wh_design * 100   (bila data ada)
battery_points = clamp(round(health), 0, 100)
```
- Bila tak ada baterai (PC desktop) atau data kosong → **netral**, komponen ini
  dikeluarkan dari rata-rata berbobot (bobotnya dibagikan ke komponen lain).

### 2e. Bobot komponen (per kelompok, Standar Frugal 2026-06)
Tiap baris berjumlah 1.0.

| Kelompok | W_CPU | W_RAM | W_Storage | W_Battery |
|---|---:|---:|---:|---:|
| `field` `admin` `marketing` `hr` `other` | 0.30 | 0.30 | 0.20 | 0.20 |
| `management` | 0.30 | 0.25 | 0.20 | 0.25 |
| `finance` | 0.30 | 0.40 | 0.10 | 0.20 |
| `data_processing` | 0.30 | 0.40 | 0.15 | 0.15 |
| `design` | 0.35 | 0.35 | 0.15 | 0.15 |
| `it` | 0.40 | 0.35 | 0.15 | 0.10 |

```
Skor Spek = Σ(poin_komponen * bobot) / Σ(bobot komponen yang dipakai)
```

---

## 3. Skor Beban (0-100) — "layak secara load"
Mengukur apakah laptop sanggup menahan beban kerja nyata. Dua faktor: **tekanan
pemakaian nyata** (RAM + CPU terpakai) dan **kecukupan RAM** terhadap peran.

### 3a. Tekanan pemakaian (snapshot `ram_usage_pct` + `cpu_usage_pct`)
**Standar Frugal 2026-06: 1 ramp LINIER** (menggantikan piecewise per-tier lama —
lebih mudah dijelaskan). Ambil **rata-rata** dari sinyal beban yang ADA datanya
(RAM dan/atau CPU), lalu petakan:

| rata-rata pemakaian | Poin tekanan |
|---|---:|
| ≤ 60% | 100 |
| 60–100% | 100 → 0 (linier) |
| 100% | 0 |

```
avg_pct      = rata-rata dari (ram_usage_pct, cpu_usage_pct) yang tersedia
poin_tekanan = 100                       , bila avg_pct ≤ 60
             = 100 * (100 - avg_pct) / 40, bila 60 < avg_pct < 100
             = 0                          , bila avg_pct ≥ 100
```
Bila RAM **dan** CPU kosong → netral 100. Bila hanya salah satu → pakai yang ada
(submission lama tanpa `cpu_usage_pct` tetap memakai tekanan RAM saja).

### 3b. Kecukupan RAM terhadap peran
```
ram_adequacy = clamp(round(100 * ram_gb / profil.ram_min), 0, 100)
```
(Di bawah RAM minimum kelompok → turun tajam.)

```
Skor Beban = round(0.5 * poin_tekanan + 0.5 * ram_adequacy)
```

> Catatan kejujuran: snapshot sekali itu sinyal lemah. Ia menurunkan skor bila
> jelas mepet, tapi tidak dijadikan satu-satunya penentu. Penentu utama tetap
> spek vs kebutuhan peran. `cpu_usage_pct` diisi collector versi baru; submission
> lama **tidak perlu diisi ulang** — bagian CPU dibiarkan netral.

### 3c. Vonis 2 sumbu — Skor Spek × Skor Beban
Profil kebutuhan per peran (§1) hanyalah **perkiraan**. Beban nyata bisa
membongkar perkiraan yang meleset. Karena itu kedua skor dibaca sebagai **dua
sumbu** (`two_axis_verdict()` di `scoring.py`), ambang biner = `status_eligible_min`:

| | Beban ringan (Skor Beban ≥ ambang) | Beban berat (Skor Beban < ambang) |
|---|---|---|
| **Spek layak** | ✅ `fit` — memadai & santai | ⚠️ `overloaded` — di atas kertas layak tapi nyatanya berat → tugas lebih berat dari perkiraan peran, pertimbangkan **upgrade** |
| **Spek kurang** | 🟡 `oversized` — di bawah standar tapi nyatanya ringan → **penggantian tidak mendesak** | ❌ `poor` — kurang & kewalahan → prioritas ganti |

- Vonis ini **tidak** menghitung ulang skor. Beban nyata sudah ikut menarik Skor
  Total lewat Skor Beban (blend §0), dan untuk kuadran `overloaded`/`oversized`
  ditambahkan **alasan** ke `status_reasons` (menyebut CPU%/RAM% saat dicek).
- Tampil di detail laptop & karyawan, halaman publik, dan kolom **"Spek vs Beban
  Nyata"** pada export XLSX.

---

## 4. Status (Layak / Upgrade / Ganti)
Tentukan dari **Skor Total**, lalu terapkan **aturan paksa** yang bisa menurunkan
status (override) beserta alasannya.

### 4a. Dari skor (Standar Frugal 2026-06: pita Ganti menyempit)
| Skor Total | Status |
|---|---|
| 70–100 | `Layak` |
| 35–69 | `Upgrade` |
| 0–34 | `Ganti` |

### 4b. Aturan paksa (override + alasan ditambahkan ke `status_reasons`)
- `ram_gb < profil.ram_min` → minimal `Upgrade`, alasan: *"RAM {x}GB di bawah minimum {min}GB untuk kelompok {grup} — tambah RAM"*.
- HDD saja (tidak ada SSD) → minimal `Upgrade`, alasan: *"Belum SSD — ganti ke SSD"*.
- `cpu_passmark < profil.cpu_floor` → minimal `Upgrade`; bila `< 0.6 * cpu_floor` → `Ganti`, alasan: *"CPU di bawah batas bawah kelompok"*.
- **Penyimpanan OS (rasio, Standar Frugal 2026-06):** `os_free_gb / os_total_gb < 0.15` → **Skor Beban −10** (§3) + alasan: *"Sisa penyimpanan < 15%, performa sistem menurun drastis. Segera bersihkan ruang penyimpanan."* (menggantikan aturan absolut `< 20 GB` lama).

### 4c. Catatan komponen (bukan status laptop, tapi flag terpisah)
- `battery_health < 60%` → flag *"Baterai sehat <60% — pertimbangkan ganti baterai"*.
  (Ganti baterai ≠ ganti laptop, jadi tidak otomatis bikin status `Ganti`.)
- `physical_condition = poor` atau ada `issues` → tampilkan sebagai catatan
  perawatan, terpisah dari skor kelayakan teknis.

---

## 5. Estimasi Tahun Pensiun (EOL)
Masa pakai **rata 5 tahun** sejak pembelian (Standar Frugal 2026-06: penyesuaian
±1 by Skor Spek **dibuang** — fitur minor, low-stakes; estimasi planning saja, tak
memengaruhi skor/status):
```
eol_year = purchase_year + 5
```
- Bila `purchase_year` kosong → EOL tidak dihitung (tampilkan "—", minta lengkapi).
- **Laptop personal** (`laptop_status = personal`) → `eol_year = NULL` (aset pribadi
  tak disusutkan perusahaan).
- Bila `status = Ganti` atau `eol_year <= tahun_sekarang` → tampilkan
  **"Sudah waktunya diganti"**.
- `tahun_sekarang` diambil dari server saat scoring (jangan hardcode).

---

## 6. Fallback bila CPU tak ada di tabel benchmark
1. Normalisasi & fuzzy match dulu (lowercase, buang "(R)", "(TM)", "CPU @", spasi ganda).
2. Bila tetap gagal:
   - Tebak kasar dari `cpu_cores`/`cpu_threads` → estimasi PassMark kasar
     (mis. `passmark ≈ threads * 1800`), beri flag `cpu_estimasi=true`.
   - Tandai di `status_reasons`: *"Skor CPU diperkirakan (model tak dikenali) —
     verifikasi manual"*.
3. Catat model yang gagal ke log agar tabel `cpu_benchmarks` bisa dilengkapi.

---

## 7. Contoh perhitungan (ilustrasi — Standar Frugal 2026-06)
**Laptop admin, Ryzen 5 7530U (PassMark ~16.000), RAM 8GB, SSD NVMe, baterai
health 70%, RAM usage 75%, beli 2022.**
Profil `admin` (frugal): cpu_ideal 12.000, ram_ideal 16, ram_min 8.
Bobot `admin`: CPU .30 · RAM .30 · Storage .20 · Battery .20.

- CPU points = clamp(100*16000/12000) = clamp(133) = **100**
- RAM points = 100*8/16 = **50**
- Storage = **100** (NVMe)
- Battery = **70**
- Skor Spek = 100*.30 + 50*.30 + 100*.20 + 70*.20 = 30+15+20+14 = **79**
- Tekanan (linier, RAM 75%) = 100*(100-75)/40 = **62.5**
- RAM adequacy = 100*8/8 = **100**
- Skor Beban = round(.5*62.5 + .5*100) = **81**
- Skor Total = round(.7*79 + .3*81) = round(55.3+24.3) = **80 → Layak**
- Override: ram_gb(8) == ram_min(8) → tidak kena. SSD ada → aman.
- EOL: rata 5 tahun → 2022+5 = **2027**.

Hasil: **Skor 80 · Layak · pensiun ~2027**, catatan baterai 70% (masih wajar).

---

## 8. Yang harus dikalibrasi setelah data nyata masuk
- Anchor PassMark per kelompok (§1) — sesuaikan dgn distribusi CPU yang benar-benar dipakai.
- Bobot komponen (§2e) — bila ternyata RAM lebih krusial dari perkiraan.
- Ambang status (§4a) — agar proporsi Layak/Upgrade/Ganti masuk akal.
- Masa pakai dasar EOL (§5) — sesuai kebijakan aset perusahaan.

---

## 9. Sinyal tambahan (flag, bukan pengubah skor)
Sinyal berikut **tidak** mengubah Skor Total maupun memaksa status `Ganti`.
Mereka muncul sebagai **alasan/flag** di `status_reasons` dan sebagai komponen
insight (`build_insights`). Alasannya: ambang status (§4a) dikalibrasi terhadap
rumus berbobot inti (CPU/RAM/Storage/Battery). Bila sinyal-sinyal ini ikut
menggeser skor/status, kalibrasi ambang jadi tidak stabil — sebagian sinyal
bersifat *perawatan* (ganti disk/baterai) atau *kebijakan migrasi* (OS), bukan
ukuran kelayakan hardware terhadap peran. Karena itu mereka dipisah sebagai flag
actionable. (Pengecualian terkendali: **kesehatan disk** ikut mengali poin
storage di §2c, tetapi tetap netral bila datanya tidak ada.)

### 9a. Kesehatan disk (`disk_health_pct`)
- Ikut mengali poin storage (§2c) — netral bila None.
- Bila diketahui dan `< 50%` → flag: *"Kesehatan disk {x}% — cadangkan data &
  pertimbangkan ganti disk"*. Tidak memaksa status `Ganti`.
- Insight komponen **Kesehatan Disk**: `>= 70` good · `40–69` warn · `< 40` bad ·
  None neutral.

### 9b. Dukungan OS (`os_name`)
- Helper `os_supported(os_name) -> True/False/None`:
  - **False** → Windows 10/8.1/8/7 (dan lebih lama). Windows 10 **EOL Okt 2025**.
  - **True** → Windows 11 atau macOS/Linux/ChromeOS modern.
  - **None** → tak jelas / tak terdeteksi.
- Bila False → flag: *"Windows 10 sudah habis dukungan (Okt 2025) — rencanakan
  migrasi/ganti ke Windows 11"*.
- Insight komponen **Dukungan OS**: True good · False bad · None neutral.

### 9c. Kesiapan Windows 11 (`win11_ready`, `win11_blockers`)
- Indikasi dari collector (TPM 2.0, Secure Boot, RAM, storage). **Bukan** cek
  penuh allowlist CPU Microsoft.
- Bila `win11_ready == 0` → flag: *"Belum memenuhi syarat Windows 11 (indikasi):
  {win11_blockers}"*. Tidak memaksa status.
- Insight komponen **Windows 11**: `1` good ("Memenuhi syarat (indikasi)") ·
  `0` warn + blockers · None neutral (disembunyikan untuk OS yang jelas
  non-Windows).

### 9d. Headroom RAM (`ram_slots_total`, `ram_slots_used`, `ram_max_gb`)
- Insight komponen **Headroom RAM**: good bila ada slot kosong **dan**
  `ram_gb < ram_max_gb` ("Masih bisa tambah RAM: {used}/{total} slot, maks
  {max}GB"); neutral bila slot penuh / sudah mentok.
- Rekomendasi actionable bila RAM di bawah ideal peran **dan** ada headroom:
  *"Tambah RAM hingga {ideal}GB — tersedia slot kosong"*.

### 9e. Koreksi false-negative Windows 11
Collector berjalan **tanpa hak Administrator** (cukup klik 2×), sehingga dulu
deteksi TPM & Secure Boot gagal → semua laptop salah dikira "belum siap Win11".
Diperbaiki:
- **Secure Boot** dibaca dari registry `HKLM:\…\SecureBoot\State`
  `UEFISecureBootEnabled` (bisa tanpa admin).
- **TPM** bila tak terbaca (akses ditolak) → dibiarkan **tidak diketahui** (None),
  bukan "Tidak ada". Bila TPM tak diketahui → `win11_ready` dibiarkan kosong
  (tampil **netral**, bukan "belum memenuhi syarat").
- App: bila `os_name` **sudah Windows 11**, flag/insight kesiapan Win11
  disembunyikan (tak relevan) di scoring, insight, dashboard, dan tab Pengadaan.

---

## 10. Saran Penempatan Ulang (rightsizing)
`suggest_placement(sub)` menilai spek laptop terhadap **semua** kelompok kerja,
lalu menyarankan kelompok yang paling pas — *"laptop ini kurang untuk Keuangan,
tetapi cocok untuk Administrasi"*.
- Untuk tiap kelompok (kecuali `other`), hitung Skor Total laptop memakai profil
  kelompok itu; kumpulkan yang berstatus **Layak** (`eligible`).
- Diurut dari kebutuhan **terberat** yang masih layak (utilisasi terbaik).
- `suggestion` = kelompok layak terberat yang **bukan** kelompok sekarang.
- Teks: bila kelompok sekarang sudah layak → tak ada saran; bila kurang tapi ada
  kelompok lain yang cocok → sarankan pindah; bila tak layak di mana pun →
  *"kandidat peremajaan/penggantian"*.
- **Kepemilikan personal (Standar Frugal 2026-06):** `laptop_status = personal`
  **dikecualikan** dari rotasi (tak ditukar-silang antar karyawan; `suggestion`
  selalu None). Bila kurang untuk perannya → saran khusus: *"Performa aset pribadi
  menghambat produktivitas. Sediakan inventaris kantor (Rekomendasi teknis:
  [Tambah RAM/SSD])."*
- **Proteksi rotasi Manajemen (VIP):** kelompok `management` dikunci dari rotasi ke
  bawah — laptop GM **tak pernah** disarankan ditarik untuk staf (`suggestion`
  None).
- Tampil di: detail laptop & karyawan (admin), kolom indikator dashboard, dan
  kolom **"Saran Penempatan"** pada export XLSX.

---

## 11. Catatan kelompok kerja (data-driven)
Kelompok disimpan di tabel `work_groups` (seed di `scoring_config.py`): 6 kelompok
asli + **marketing**, **design**, **hr** (Standar Frugal 2026-06: kini **aktif**
dengan profil pasti, bukan lagi placeholder) + `other`. Admin dapat
menambah/menonaktifkan kelompok & mengubah profil lewat `/admin/skoring`.
Submission baru otomatis pakai parameter terbaru; data lama diperbarui via tombol
**"Hitung ulang semua"** (atau skrip `migrate_frugal_2026_06.py` untuk seed paksa).
